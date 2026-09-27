"""One watcher sweep: every active rule against the latest inventory, driving the state machine (SRS §4.2)."""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.custodian import PolicyError, load_policies, resource_id, run_filters
from app.inventory.store import Snapshot
from app.models import Alert, Notification, Rule, Watch
from app.notify.channels import Channel
from app.simulator.dryrun import summarise
from app.simulator.timetravel import rebase
from app.watcher.state import NOTIFY, Event, Observation, State, step
from app.watcher.warnings import warning_variant


@dataclass
class Transition:
    rule_id: str
    resource_id: str
    from_state: str | None
    to_state: str
    event: str | None


@dataclass
class SweepResult:
    at: datetime
    rules: int
    evaluated: int
    transitions: list[Transition] = field(default_factory=list)
    notifications: int = 0
    errors: list[str] = field(default_factory=list)


def sweep(session: Session, snapshot: Snapshot, channel: Channel, now: datetime, region: str) -> SweepResult:
    rules = session.scalars(select(Rule).where(Rule.status == 'active')).all()
    result = SweepResult(at=now, rules=len(rules), evaluated=0)

    for rule in rules:
        try:
            policies = load_policies(rule.policy_yaml, region)
            warn_yaml = warning_variant(rule.policy_yaml)
            warn_policies = load_policies(warn_yaml, region) if warn_yaml else []
        except PolicyError as e:
            result.errors.append(f'{rule.id}: {e}')
            continue

        breached, approaching, population = defaultdict(set), defaultdict(set), {}
        for policy in policies + warn_policies:
            rtype = policy.resource_type
            if rtype not in population:
                # Custodian compares ages with the real clock, so shift the snapshot to read as if taken right now.
                population[rtype] = rebase(snapshot.of_type(rtype), datetime.now(timezone.utc) - snapshot.taken_at)
            matched, _ = run_filters(policy, population[rtype])
            target = approaching if policy in warn_policies else breached
            target[rtype].update(resource_id(rtype, r) for r in matched)

        watches = {w.resource_id: w for w in rule.watches}
        seen = set()
        for rtype, resources in population.items():
            for resource in resources:
                rid = resource_id(rtype, resource)
                seen.add(rid)
                result.evaluated += 1
                observation = Observation(breached=rid in breached[rtype], approaching=rid in approaching[rtype])
                _apply(session, rule, rtype, rid, resource, watches, observation, now, channel, result)

        # A resource that disappeared (terminated, deleted) can't still be breaking the rule.
        for rid, watch in watches.items():
            if rid not in seen and watch.state in (State.WARNING, State.ALERT, State.SNOOZED):
                _record(result, rule, rid, State(watch.state), State.RESOLVED, Event.RESOLVED)
                watch.state, watch.since, watch.snoozed_until = State.RESOLVED, now, None
                _resolve_alerts(session, rule.id, rid, now)

    session.commit()
    return result


def _apply(session, rule, rtype, rid, resource, watches, observation, now, channel, result):
    watch = watches.get(rid)
    current = State(watch.state) if watch else None
    new_state, event = step(current, observation, now, watch.snoozed_until if watch else None)

    if watch is None:
        watch = Watch(resource_id=rid, resource_type=rtype, state=new_state, since=now, last_seen=now)
        # Appended through the relationship, not session.add(rule_id=...): that keeps rule.watches
        # in step, so a second sweep on the same session sees this watch instead of re-inserting it.
        rule.watches.append(watch)
        watches[rid] = watch
    elif new_state != current:
        watch.state, watch.since = new_state, now
    watch.last_seen = now
    if new_state is not State.SNOOZED:
        watch.snoozed_until = None

    if current != new_state or event:
        _record(result, rule, rid, current, new_state, event)

    if event is Event.RESOLVED:
        _resolve_alerts(session, rule.id, rid, now)
    elif event in NOTIFY:
        alert = _open_alert(session, rule, rtype, rid, resource, event, now)
        delivery = channel.send(alert.message)
        session.add(Notification(alert_id=alert.id, channel=delivery.channel, text=alert.message,
                                 delivered=delivery.delivered, error=delivery.error, sent_at=now))
        result.notifications += 1


def _open_alert(session, rule, rtype, rid, resource, event, now) -> Alert:
    level = 'alert' if event is Event.ALERT else 'warning'
    summary = summarise(rtype, resource, datetime.now(timezone.utc))  # resource was rebased to the real clock
    existing = session.scalars(
        select(Alert).where(Alert.rule_id == rule.id, Alert.resource_id == rid, Alert.status.in_(('open', 'snoozed')))
    ).all()
    for old in existing:
        if old.level == level:  # a snooze expired and the problem is still there
            old.status, old.snoozed_until, old.message = 'open', None, _message(rule, summary, level, again=True)
            return old
        old.status, old.resolved_at = 'resolved', now  # warning escalated to alert

    alert = Alert(rule_id=rule.id, resource_id=rid, resource_type=rtype, resource_name=summary.name, level=level,
                  message=_message(rule, summary, level), cost_per_day=summary.cost_per_day, created_at=now)
    session.add(alert)
    session.flush()
    return alert


def _resolve_alerts(session, rule_id, rid, now):
    for alert in session.scalars(select(Alert).where(Alert.rule_id == rule_id, Alert.resource_id == rid, Alert.status.in_(('open', 'snoozed')))):
        alert.status, alert.resolved_at, alert.snoozed_until = 'resolved', now, None


def _message(rule, summary, level, again=False) -> str:
    who = summary.name or summary.id
    what = f' ({summary.detail})' if summary.detail else ''
    running = f', running {summary.running_hours:g}h' if summary.running_hours else ''
    cost = f' It costs ₹{summary.cost_per_day:,.0f}/day.' if summary.cost_per_day else ''
    if level == 'alert':
        lead = 'Still breaking' if again else 'Broke'
        return f'🚨 {who}{what}{running}. {lead} your rule “{rule.english}”.{cost}'
    return f'⚠️ {who}{what}{running} is getting close to your rule “{rule.english}”.{cost}'


def _record(result, rule, rid, before, after, event):
    result.transitions.append(Transition(rule.id, rid, before.value if before else None, after.value, event.value if event else None))


def snooze(session: Session, alert: Alert, hours: float, now: datetime) -> Alert:
    until = now + timedelta(hours=hours)
    alert.status, alert.snoozed_until = 'snoozed', until
    watch = session.scalars(select(Watch).where(Watch.rule_id == alert.rule_id, Watch.resource_id == alert.resource_id)).first()
    if watch:
        watch.state, watch.since, watch.snoozed_until = State.SNOOZED, now, until
    session.commit()
    return alert
