"""Read-only inventory sweep with boto3 (SRS §4.2). Uses only Describe* calls from the IAM policy in SRS §7."""
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from app.inventory.store import Snapshot, SnapshotHistory

ClientFactory = Callable[[str], object]


def poll(client: ClientFactory) -> Snapshot:
    """Take one snapshot. `client(service)` returns a boto3 client, injected so tests can stub it."""
    ec2 = client('ec2')
    instances = [
        instance
        for page in ec2.get_paginator('describe_instances').paginate()
        for reservation in page['Reservations']
        for instance in reservation['Instances']
        if instance['State']['Name'] != 'terminated'
    ]
    volumes = [v for page in ec2.get_paginator('describe_volumes').paginate() for v in page['Volumes']]
    groups = [g for page in ec2.get_paginator('describe_security_groups').paginate() for g in page['SecurityGroups']]
    nats = [
        n for page in ec2.get_paginator('describe_nat_gateways').paginate() for n in page['NatGateways']
        if n['State'] not in ('deleted', 'deleting')
    ]
    databases = []
    for page in client('rds').get_paginator('describe_db_instances').paginate():
        for db in page['DBInstances']:
            db = dict(db)
            db['Tags'] = db.pop('TagList', [])  # the rename Custodian's RDS augment step performs
            databases.append(db)

    return Snapshot(taken_at=datetime.now(timezone.utc), resources={
        'aws.ec2': instances,
        'aws.ebs': volumes,
        'aws.security-group': groups,
        'aws.nat-gateway': nats,
        'aws.rds': databases,
    })


class LiveInventory:
    """Polls on demand, at most once per `min_interval`, keeping every sweep for time-travel simulation."""

    def __init__(self, region: str, min_interval: timedelta = timedelta(minutes=15)):
        import boto3

        session = boto3.Session(region_name=region)
        self._client = lambda service: session.client(service)
        self._history = SnapshotHistory()
        self._min_interval = min_interval

    def latest(self) -> Snapshot:
        last = self._history.latest()
        if last is None or datetime.now(timezone.utc) - last.taken_at >= self._min_interval:
            self._history.append(poll(self._client))
        return self._history.latest()

    def history(self, days: int) -> list[Snapshot]:
        latest = self.latest()
        return self._history.since(latest.taken_at - timedelta(days=days))
