"""How good is this rule? (SRS §22.1)

Five dimensions, scored from what the rule has actually done rather than from how it is worded. A
rule younger than the provisional window scores `None` — two alerts is not a signal rate, and a
confident number computed from nothing is worse than no number.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.engine.custodian import PolicyError, load_policies, resource_id, run_filters
from app.inventory.store import Snapshot

PROVISIONAL_DAYS = 14

# Weights sum to 100. Specificity leads: a rule that matches everything is the most common failure.
MAXIMA = {'specificity': 25, 'verifiability': 20, 'actionability': 20, 'signalRate': 20, 'stability': 15}


@dataclass
class Dimension:
    score: int
    max: int
    note: str

    def as_dict(self) -> dict:
        return {'score': self.score, 'max': self.max, 'note': self.note}


def score(rule, snapshot: Snapshot, region: str, now: datetime | None = None) -> dict | None:
    """The five dimensions, or None while the rule is still provisional."""
    now = now or datetime.now(timezone.utc)
    age_days = (now - rule.created_at).days
    if age_days < PROVISIONAL_DAYS:
        return None

    recent = [a for a in rule.alerts if a.created_at >= now - timedelta(days=30)]
    acted = [a for a in recent if a.resolved_at and a.resolved_at - a.created_at <= timedelta(hours=2)]

    dimensions = {
        'specificity': _specificity(rule, snapshot, region),
        'verifiability': _verifiability(rule),
        'actionability': _actionability(rule),
        'signalRate': _signal_rate(recent, acted),
        'stability': _stability(recent, now),
    }
    total = sum(d.score for d in dimensions.values())
    return {
        'quality': total,
        'breakdown': {name: d.as_dict() for name, d in dimensions.items()},
        'improvementTip': _tip(dimensions),
    }


def _specificity(rule, snapshot: Snapshot, region: str) -> Dimension:
    """A rule that matches half the account is a broadcast, not a guardrail."""
    try:
        policies = load_policies(rule.policy_yaml, region)
    except PolicyError:
        return Dimension(0, MAXIMA['specificity'], 'Policy no longer parses.')

    matched, population = set(), 0
    for policy in policies:
        rtype = policy.resource_type
        resources = snapshot.of_type(rtype)
        population += len(resources)
        hits, _ = run_filters(policy, resources)
        matched.update(resource_id(rtype, r) for r in hits)

    if not population:
        return Dimension(12, MAXIMA['specificity'], 'No resources of this type to judge against.')

    share = len(matched) / population
    if share == 0:
        return Dimension(14, MAXIMA['specificity'], f'Matches none of your {population} resources right now.')
    if share <= 0.15:
        return Dimension(23, MAXIMA['specificity'], f'Matches {len(matched)} of {population} resources — tightly scoped.')
    if share <= 0.4:
        return Dimension(18, MAXIMA['specificity'], f'Matches {len(matched)} of {population} resources.')
    return Dimension(10, MAXIMA['specificity'], f'Matches {len(matched)} of {population} resources — too broad to act on.')


def _verifiability(rule) -> Dimension:
    if not rule.verified:
        return Dimension(6, MAXIMA['verifiability'], 'Stored without passing the verifier.')
    return Dimension(20, MAXIMA['verifiability'], 'Passed every generated fixture, including the edge case.')


def _actionability(rule) -> Dimension:
    """Can the person receiving the alert tell what to do about it?"""
    intent = rule.intent or {}
    kind = intent.get('kind', '')
    if kind == 'ec2-runtime':
        return Dimension(18, MAXIMA['actionability'], f'Names a threshold ({intent.get("hours")}h) and a clear action: stop it.')
    if kind in ('rds-public', 'sg-open-port'):
        return Dimension(19, MAXIMA['actionability'], 'One specific setting to change, with a known command.')
    if kind == 'ebs-unattached':
        return Dimension(16, MAXIMA['actionability'], 'Clear action, but deletion needs a human to confirm the data is dead.')
    if kind == 'require-tag':
        return Dimension(12, MAXIMA['actionability'], 'Says what is missing but not who should own it.')
    return Dimension(13, MAXIMA['actionability'], 'Actionable, but the fix is not stated in the alert.')


def _signal_rate(recent: list, acted: list) -> Dimension:
    """The honest one: how often did anyone do something about it?"""
    if not recent:
        return Dimension(12, MAXIMA['signalRate'], 'Has not fired in 30 days — nothing to judge yet.')
    rate = len(acted) / len(recent)
    note = f'{len(acted)} of {len(recent)} alerts acted on ({rate * 100:.0f}%).'
    if rate >= 0.8:
        return Dimension(20, MAXIMA['signalRate'], note)
    if rate >= 0.5:
        return Dimension(16, MAXIMA['signalRate'], note)
    if rate >= 0.25:
        return Dimension(9, MAXIMA['signalRate'], note + ' Mostly ignored.')
    return Dimension(4, MAXIMA['signalRate'], note + ' This rule is training people to ignore Ward.')


def _stability(recent: list, now: datetime) -> Dimension:
    """A rule that fires in bursts is harder to live with than one that fires steadily."""
    if not recent:
        return Dimension(11, MAXIMA['stability'], 'Quiet for 30 days.')
    per_week = len(recent) / 4.3
    if per_week <= 3:
        return Dimension(15, MAXIMA['stability'], f'About {per_week:.1f} alerts a week — comfortable.')
    if per_week <= 8:
        return Dimension(10, MAXIMA['stability'], f'About {per_week:.1f} alerts a week.')
    return Dimension(5, MAXIMA['stability'], f'About {per_week:.1f} alerts a week — loud enough to be tuned out.')


def _tip(dimensions: dict[str, Dimension]) -> str:
    """Name the one change that would help most, with what it is worth."""
    name, weakest = min(dimensions.items(), key=lambda kv: kv[1].score / kv[1].max)
    gain = weakest.max - weakest.score
    advice = {
        'specificity': 'Narrow the filters — add a state, tag or instance-family condition',
        'verifiability': 'Re-run the verifier and fix the fixtures it fails',
        'actionability': 'Name the fix in the alert text so it is one click to resolve',
        'signalRate': 'Either raise the threshold so it fires less, or archive it — unacted alerts train people to ignore Ward',
        'stability': 'Add a cooldown or raise the threshold so it fires in fewer bursts',
    }[name]
    return f'{advice} (+{gain}).'
