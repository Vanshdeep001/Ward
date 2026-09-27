"""Why the bill moved (SRS §15).

Every tool can say spend went up. The Detective says *which resources* moved it, by differencing two
windows of snapshots per resource and ranking the deltas — then names the rule that would have caught
the biggest one, so an explanation turns into a guardrail.
"""
from datetime import datetime, timedelta, timezone

from app.engine.custodian import resource_id
from app.inventory.pricing import hourly_cost
from app.inventory.store import InventoryStore, Snapshot
from app.simulator.dryrun import summarise


def _cost_by_resource(snapshots: list[Snapshot]) -> dict[str, dict]:
    """Mean hourly cost per resource across a window, carrying the last shape seen of each."""
    totals: dict[str, dict] = {}
    for snap in snapshots:
        for rtype, resources in snap.resources.items():
            for r in resources:
                rid = resource_id(rtype, r)
                entry = totals.setdefault(rid, {'type': rtype, 'resource': r, 'rates': []})
                entry['resource'] = r
                entry['rates'].append(hourly_cost(rtype, r) or 0.0)
    for entry in totals.values():
        entry['mean_hourly'] = sum(entry['rates']) / len(entry['rates'])
    return totals


SERVICE_LABELS = {
    'aws.ec2': 'EC2',
    'aws.rds': 'RDS',
    'aws.ebs': 'EBS',
    'aws.nat-gateway': 'NAT Gateway',
    'aws.s3': 'S3',
    'aws.security-group': 'Security groups',
}
GPU_FAMILIES = ('p2', 'p3', 'p4', 'g4', 'g4dn', 'g5', 'inf1')


def _service_of(rtype: str, resource: dict) -> str:
    label = SERVICE_LABELS.get(rtype, rtype)
    if rtype == 'aws.ec2' and str(resource.get('InstanceType', '')).split('.')[0] in GPU_FAMILIES:
        return 'EC2 — GPU'
    return label


def investigate(inventory: InventoryStore, window_days: int = 7, now: datetime | None = None,
                alerts: list | None = None) -> dict:
    """Compare the last `window_days` against the `window_days` before them.

    Grouped by service for the headline, but every cause names the single resource that moved it —
    "EC2 went up" is not an explanation, "ml-training ran 43 hours longer" is.
    """
    now = now or datetime.now(timezone.utc)
    history = inventory.history(window_days * 2)
    split = now - timedelta(days=window_days)

    current = [s for s in history if s.taken_at >= split]
    previous = [s for s in history if s.taken_at < split]

    # With nothing to compare against, every resource would read as "new" — which is false, not an
    # explanation. A freshly connected account says so until it has a full window behind it.
    if not previous:
        watched = (now - history[0].taken_at) if history else timedelta(0)
        return {
            'from': {'total': 0.0, 'label': f'the {window_days} days before'},
            'to': {'total': 0.0, 'label': f'the last {window_days} days'},
            'delta': 0.0,
            'causes': [],
            'unattributed': 0.0,
            'changes': [],
            'suggestedRule': None,
            'insufficientHistory': True,
            'note': f'Ward has watched this account for {_span(watched)}. The Detective compares two '
                    f'{window_days}-day windows, so it can explain a change once it has {window_days * 2} days of history.',
        }

    now_costs = _cost_by_resource(current)
    then_costs = _cost_by_resource(previous)

    changes = []
    for rid in set(now_costs) | set(then_costs):
        after = now_costs.get(rid, {}).get('mean_hourly', 0.0) * 24
        before = then_costs.get(rid, {}).get('mean_hourly', 0.0) * 24
        delta = after - before
        if abs(delta) < 0.5:  # noise: a few rupees a day is not an explanation
            continue
        entry = now_costs.get(rid) or then_costs[rid]
        summary = summarise(entry['type'], entry['resource'], now)
        changes.append({
            'id': rid,
            'name': summary.name,
            'detail': summary.detail,
            'type': entry['type'],
            'before': round(before, 2),
            'after': round(after, 2),
            'delta': round(delta, 2),
            'reason': _reason(rid, now_costs, then_costs, delta),
        })

    changes.sort(key=lambda c: c['delta'], reverse=True)
    total_before = round(sum(e['mean_hourly'] for e in then_costs.values()) * 24 * window_days, 2)
    total_after = round(sum(e['mean_hourly'] for e in now_costs.values()) * 24 * window_days, 2)
    coverage = _rule_coverage(alerts or [])

    causes = _causes(changes, now_costs, then_costs, coverage, window_days)
    attributed = sum(c['delta'] for c in causes)

    return {
        'from': {'total': total_before, 'label': f'the {window_days} days before'},
        'to': {'total': total_after, 'label': f'the last {window_days} days'},
        'delta': round(total_after - total_before, 2),
        'causes': causes,
        'unattributed': round(total_after - total_before - attributed, 2),
        'changes': changes[:10],  # per-resource detail, for anything that wants the raw deltas
        'suggestedRule': _suggest(changes),
    }


def _causes(changes: list[dict], now_costs: dict, then_costs: dict, coverage: dict, window_days: int) -> list[dict]:
    """One cause per service that got more expensive, led by the resource that moved it most."""
    by_service: dict[str, list[dict]] = {}
    for change in changes:
        if change['delta'] <= 0:
            continue
        entry = now_costs.get(change['id']) or then_costs[change['id']]
        service = _service_of(entry['type'], entry['resource'])
        by_service.setdefault(service, []).append(change)

    causes = []
    for service, members in by_service.items():
        members.sort(key=lambda c: c['delta'], reverse=True)
        lead = members[0]
        delta_window = round(sum(m['delta'] for m in members) * window_days, 2)
        name = lead['name'] or lead['id']
        detail = f' ({lead["detail"]})' if lead['detail'] else ''
        others = f' Plus {len(members) - 1} more in {service}.' if len(members) > 1 else ''
        causes.append({
            'id': f'cause-{lead["id"]}',
            'service': service,
            'delta': delta_window,
            'resourceId': lead['id'],
            'headline': f'{name}{detail} went from ₹{lead["before"]:,.0f} to ₹{lead["after"]:,.0f} per day.',
            'detail': f'{lead["reason"]} Over {window_days} days that is ₹{lead["delta"] * window_days:,.0f}.{others}',
            'ruleLink': coverage.get(lead['id'], {'status': 'missing', 'text': 'No rule covers this resource yet.'}),
            'suggestedRule': (_suggest([lead]) or {}).get('english'),
        })

    causes.sort(key=lambda c: c['delta'], reverse=True)
    return causes


def _rule_coverage(alerts: list) -> dict[str, dict]:
    """Did a rule already catch this, and did anyone act on it? (SRS §15.3)

    Three states worth telling apart: no rule watches it, a rule fired and was acted on, and a rule
    fired and was ignored — the last being the uncomfortable one.
    """
    from datetime import timedelta

    by_resource: dict[str, dict] = {}
    for alert in alerts:
        entry = by_resource.setdefault(alert.resource_id, {'fired': 0, 'acted': 0, 'english': None})
        entry['fired'] += 1
        if alert.resolved_at and alert.resolved_at - alert.created_at <= timedelta(hours=2):
            entry['acted'] += 1
        rule = getattr(alert, 'rule', None)
        entry['english'] = entry['english'] or (rule.english if rule else None)

    out = {}
    for rid, entry in by_resource.items():
        quoted = f'“{entry["english"]}”' if entry['english'] else 'A rule'
        if entry['acted']:
            out[rid] = {'status': 'working',
                        'text': f'{quoted} fired {entry["fired"]}× and was acted on {entry["acted"]}×.'}
        else:
            out[rid] = {'status': 'working-but-ignored',
                        'text': f'{quoted} fired {entry["fired"]}× — no alert was acted on.'}
    return out


def _span(delta: timedelta) -> str:
    hours = delta.total_seconds() / 3600
    return f'{hours:.0f} hours' if hours < 48 else f'{hours / 24:.0f} days'


def _reason(rid: str, now_costs: dict, then_costs: dict, delta: float) -> str:
    if rid not in then_costs:
        return 'New — it did not exist in the earlier window.'
    if rid not in now_costs:
        return 'Gone — it was removed during this window.'
    if delta > 0:
        return 'Ran for more hours, or moved to a larger size.'
    return 'Ran for fewer hours, or was stopped.'


def _suggest(changes: list[dict]) -> dict | None:
    """Turn the biggest increase into a rule the user can accept in one click (SRS §15.4)."""
    biggest = next((c for c in changes if c['delta'] > 0), None)
    if biggest is None:
        return None
    if biggest['type'] == 'aws.ec2':
        return {
            'english': 'No GPU instance runs more than 6 hours' if _is_gpu(biggest['detail'])
            else 'Nothing runs longer than 6 hours unattended',
            'because': f"{biggest['name'] or biggest['id']} added ₹{biggest['delta']:,.0f}/day by running longer.",
        }
    if biggest['type'] == 'aws.ebs':
        return {'english': 'Flag EBS volumes unattached for more than 7 days',
                'because': f"{biggest['name'] or biggest['id']} is billing while attached to nothing."}
    return None


def _is_gpu(detail: str | None) -> bool:
    return bool(detail) and detail.split('.')[0] in ('p2', 'p3', 'p4', 'g4', 'g4dn', 'g5', 'inf1')
