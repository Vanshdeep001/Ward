"""Replay a policy over stored snapshots: how often would it have fired? (SRS §16.3)

Custodian's age filters compare against the wall clock, so each snapshot is rebased — every timestamp shifted
forward by (now - snapshot time) — which makes ages read exactly as they did when the snapshot was taken.
"""
from datetime import datetime, timedelta, timezone

from app.engine.custodian import resource_id, run_filters
from app.inventory.store import Snapshot
from app.simulator.models import FireEvent, History

WALL_CLOCK_FILTERS = {'offhour', 'onhour'}


def replay(policies, snapshots: list[Snapshot], days: int, now: datetime | None = None) -> History:
    now = now or datetime.now(timezone.utc)
    snapshots = sorted(snapshots, key=lambda s: s.taken_at)
    events: list[FireEvent] = []

    for policy in policies:
        previously_matched: set[str] = set()
        for snap in snapshots:
            resources = rebase(snap.of_type(policy.resource_type), now - snap.taken_at)
            matched, _ = run_filters(policy, resources)
            ids = {resource_id(policy.resource_type, r) for r in matched}
            # The watcher only notifies on transitions (SRS §4.3), so a resource that stays matched fires once.
            for r in matched:
                rid = resource_id(policy.resource_type, r)
                if rid not in previously_matched:
                    name = next((t['Value'] for t in r.get('Tags', []) if t['Key'] == 'Name'), None)
                    events.append(FireEvent(at=snap.taken_at, resource_id=rid, name=name, policy=policy.name))
            previously_matched = ids

    events.sort(key=lambda e: e.at, reverse=True)
    fire_days = {e.at.date() for e in events}
    caveats = []
    if any(f.type in WALL_CLOCK_FILTERS for p in policies for f in p.resource_manager.filters):
        caveats.append('offhour/onhour filters use the current time, so their history is approximate.')
    if snapshots and snapshots[0].taken_at > now - timedelta(days=days) + timedelta(hours=12):
        caveats.append(f'Only {(now - snapshots[0].taken_at).days} days of inventory history are available.')

    return History(
        days=days,
        snapshots=len(snapshots),
        fires=len(events),
        events=events,
        quiet_days=max(days - len(fire_days), 0),
        alerts_per_week=round(len(events) / days * 7, 1) if days else 0.0,
        caveats=caveats,
    )


def rebase(resources: list[dict], shift: timedelta) -> list[dict]:
    def move(value):
        if isinstance(value, datetime):
            return value + shift
        if isinstance(value, dict):
            return {k: move(v) for k, v in value.items()}
        if isinstance(value, list):
            return [move(v) for v in value]
        return value

    return [move(r) for r in resources] if shift else resources  # move() builds new containers, so inputs stay untouched
