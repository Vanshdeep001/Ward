"""The demo account: the same resources the frontend mock shows, as boto3-shaped dicts, with 30 days of history.

All times hang off one anchor (when the sample was built), so a resource's launch time is identical in every
snapshot and each snapshot shows exactly what existed and was running at that moment.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.inventory import shapes
from app.inventory.store import Snapshot, SnapshotHistory


@dataclass(frozen=True)
class GpuSession:
    instance_id: str
    started_hours_ago: float
    runtime_hours: float | None  # None: still running


# Mirrors gpuSessions in frontend/src/api/mock/data.js.
GPU_SESSIONS = (
    GpuSession('i-0a1f2', 31, None),
    GpuSession('i-0b3d4', 9, None),
    GpuSession('i-0c7e1', 2, None),
    GpuSession('i-0a1f2', 3 * 24, 14),
    GpuSession('i-0a1f2', 5 * 24, 11),
    GpuSession('i-0b3d4', 9 * 24, 7.5),
    GpuSession('i-0c7e1', 12 * 24, 4),
    GpuSession('i-0b3d4', 15 * 24, 10),
    GpuSession('i-0a1f2', 18 * 24, 8),
    GpuSession('i-0c7e1', 21 * 24, 5.5),
    GpuSession('i-0a1f2', 24 * 24, 13),
    GpuSession('i-0b3d4', 27 * 24, 3),
)

GPU_INSTANCES = {
    'i-0a1f2': ('g5.xlarge', {'Name': 'ml-training'}),
    'i-0b3d4': ('g4dn.xlarge', {'Name': 'riya-notebook', 'Owner': 'riya'}),
    'i-0c7e1': ('g4dn.xlarge', {'Name': 'arjun-finetune', 'Owner': 'arjun'}),
}

# (id, type, running for N hours at the anchor or None if stopped, tags, region)
CPU_INSTANCES = (
    ('i-0d2a9', 't3.small', 120, {'Name': 'attendance-api', 'Owner': 'team', 'Environment': 'production'}, 'ap-south-1'),
    ('i-0e5b3', 't3.micro', 300, {'Name': 'bastion', 'Owner': 'team'}, 'ap-south-1'),
    ('i-0f8c4', 't3.medium', None, {'Name': 'old-jenkins', 'Owner': 'team'}, 'ap-south-1'),
    ('i-01a2b', 't3.micro', 50, {'Name': 'test-server'}, 'ap-south-1'),
    ('i-02c3d', 't2.micro', None, {'Name': 'vansh-lab', 'Owner': 'vansh'}, 'ap-south-1'),
    ('i-03e4f', 't3.small', 20, {'Name': 'vansh-api', 'Owner': 'vansh'}, 'ap-south-1'),
    ('i-04g5h', 't3.micro', 4, {'Name': 'scratch'}, 'ap-south-1'),
    ('i-05i6j', 't3.micro', None, {'Name': 'demo-box'}, 'ap-south-1'),
    ('i-06k7l', 't3.small', 70, {'Name': 'worker', 'Owner': 'team'}, 'ap-south-1'),
    ('i-07m8n', 't3.micro', 8, {'Name': 'riya-dev', 'Owner': 'riya'}, 'ap-south-1'),
    ('i-08o9p', 't3.large', 15, {'Name': 'forgotten-us'}, 'us-east-1'),
)


def build_snapshot(anchor: datetime, at: datetime) -> Snapshot:
    """The account as it looked at `at`, for a sample whose "now" is `anchor`."""
    ago = lambda hours: anchor - timedelta(hours=hours)
    exists = lambda created: created <= at

    instances = []
    for instance_id, (itype, tags) in GPU_INSTANCES.items():
        sessions = [s for s in GPU_SESSIONS if s.instance_id == instance_id and ago(s.started_hours_ago) <= at]
        if not sessions:
            continue
        last = max(sessions, key=lambda s: ago(s.started_hours_ago))
        start = ago(last.started_hours_ago)
        running = last.runtime_hours is None or at < start + timedelta(hours=last.runtime_hours)
        instances.append(shapes.ec2(instance_id, itype, launched=start, running=running, tags=tags))

    for instance_id, itype, running_hours, tags, region in CPU_INSTANCES:
        launched = ago(running_hours if running_hours is not None else 24 * 40)
        if exists(launched):
            instances.append(shapes.ec2(instance_id, itype, launched=launched, running=running_hours is not None, tags=tags, region=region))

    volumes = [
        *(shapes.ebs(v, created=ago(24 * 9), tags={'Name': v}) for v in ('vol-01', 'vol-02', 'vol-03')),
        shapes.ebs('vol-04', created=ago(24 * 40), attached_to='i-0d2a9', tags={'Name': 'vol-04', 'Owner': 'team'}),
    ]
    databases = [
        shapes.rds('attendance-db', 'db.t3.micro', created=ago(24 * 40), tags={'Owner': 'team'}),
        shapes.rds('hackathon-db', 'db.t3.medium', created=ago(24 * 12), public=True),
    ]
    nats = [shapes.nat_gateway('nat-0c5', created=ago(24 * 8), tags={'Name': 'nat-0c5 (vpc-dev-2)'})]

    return Snapshot(taken_at=at, resources={
        'aws.ec2': instances,
        'aws.ebs': [v for v in volumes if exists(v['CreateTime'])],
        'aws.rds': [d for d in databases if exists(d['InstanceCreateTime'])],
        'aws.nat-gateway': [n for n in nats if exists(n['CreateTime'])],
        'aws.security-group': [
            shapes.security_group('sg-0ssh', 'launch-wizard-1', rules=[shapes.ingress(22, ipv4=('0.0.0.0/0',))]),
            shapes.security_group('sg-0web', 'attendance-web', rules=[shapes.ingress(443, ipv4=('0.0.0.0/0',))], tags={'Owner': 'team'}),
        ],
    })


class SampleInventory:
    # Hourly, so a session only minutes past a limit still appears in some snapshot (the real watcher polls every 15 min).
    def __init__(self, days: int = 30, every_hours: int = 1, anchor: datetime | None = None):
        self.anchor = anchor or datetime.now(timezone.utc)
        self._history = SnapshotHistory()
        for i in range(days * 24 // every_hours, -1, -1):
            self._history.append(build_snapshot(self.anchor, self.anchor - timedelta(hours=i * every_hours)))

    def latest(self) -> Snapshot:
        return self._history.latest()

    def history(self, days: int) -> list[Snapshot]:
        return self._history.since(self.latest().taken_at - timedelta(days=days))
