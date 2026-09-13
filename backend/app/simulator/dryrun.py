"""Dry-run a policy against inventory before it is activated (SRS §16.1–§16.2). Read-only, no AWS calls."""
from datetime import datetime, timezone

from app.engine.custodian import LABELS, load_policies, resource_id, run_filters
from app.inventory.pricing import hourly_cost
from app.inventory.store import Snapshot
from app.simulator.models import FunnelStepOut, MatchedResource, PolicySimulation
from app.simulator.timetravel import rebase

BROAD_SHARE = 0.5
BROAD_MIN_POPULATION = 4


def simulate_now(policy_yaml: str, snapshot: Snapshot, region: str) -> list[PolicySimulation]:
    return [simulate_policy(p, snapshot) for p in load_policies(policy_yaml, region)]


def simulate_policy(policy, snapshot: Snapshot) -> PolicySimulation:
    rtype = policy.resource_type
    label = LABELS[rtype]
    # Evaluate as of the snapshot, even if it was taken a while ago.
    population = rebase(snapshot.of_type(rtype), datetime.now(timezone.utc) - snapshot.taken_at)
    matched, funnel = run_filters(policy, population)

    breadth = 'none'
    if matched:
        broad = len(population) >= BROAD_MIN_POPULATION and len(matched) / len(population) > BROAD_SHARE
        breadth = 'broad' if broad else 'normal'

    summaries = [summarise(rtype, r, datetime.now(timezone.utc)) for r in matched]  # matched resources are rebased to now
    return PolicySimulation(
        policy=policy.name,
        resource_type=rtype,
        resource_label=label,
        population=len(population),
        matched=summaries,
        funnel=[FunnelStepOut(filter=s.filter, remaining=s.remaining) for s in funnel],
        breadth=breadth,
        zero_reason=None if matched else explain_zero(label, len(population), funnel),
        cost_per_day=round(sum(m.cost_per_day or 0 for m in summaries), 2),
    )


def explain_zero(label: str, population: int, funnel) -> str:
    """'You have none' and 'you have 12 and the rule matched none' look identical as empty lists but mean opposite things."""
    if population == 0:
        return f'You have no {label}, so there is nothing to flag.'
    previous = population
    for step in funnel:
        if step.remaining == 0:
            return f'{population} {label} exist; {previous} reached the filter “{step.filter}” and none passed it.'
        previous = step.remaining
    return f'{population} {label} exist and none currently match.'


def summarise(rtype: str, r: dict, as_of: datetime) -> MatchedResource:
    tags = {t['Key']: t['Value'] for t in r.get('Tags', [])}
    hourly = hourly_cost(rtype, r)
    running_hours = None
    if rtype == 'aws.ec2' and r.get('State', {}).get('Name') == 'running':
        running_hours = round((as_of - r['LaunchTime']).total_seconds() / 3600, 1)
    detail = r.get('InstanceType') or r.get('DBInstanceClass') or (f"{r['Size']} GB {r.get('VolumeType', '')}".strip() if 'Size' in r else None)
    region = r.get('Placement', {}).get('AvailabilityZone', '')[:-1] or r.get('AvailabilityZone', '')[:-1] or None
    return MatchedResource(
        id=resource_id(rtype, r),
        name=tags.get('Name') or r.get('GroupName') or r.get('DBInstanceIdentifier'),
        detail=detail,
        region=region,
        running_hours=running_hours,
        cost_per_day=None if hourly is None else round(hourly * 24, 2),
    )
