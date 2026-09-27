"""Things worth fixing that no rule was asked about (SRS §31).

The watcher answers "is anything breaking a rule you wrote". Guardian answers the harder question:
"what should you have written a rule about". Each finding carries the resources it is about, what it
costs, the exact command that fixes it, and the rule that would catch it next time — so a finding can
become a guardrail rather than a to-do.
"""
from datetime import datetime, timezone

from app.engine.custodian import resource_id
from app.inventory.pricing import hourly_cost
from app.inventory.store import Snapshot

# Ranked by impact × confidence × actionability, with urgent security bypassing the ranking (SRS §31.3).
SEVERITY_ORDER = {'urgent': 0, 'warning': 1, 'info': 2}


def _tags(r: dict) -> dict:
    return {t['Key']: t['Value'] for t in r.get('Tags', [])}


def _cost_per_month(rtype: str, r: dict) -> float:
    return round((hourly_cost(rtype, r) or 0.0) * 24 * 30, 2)


def find_all(snapshot: Snapshot, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    findings = [f for check in (_public_databases, _open_ssh, _unattached_volumes, _untagged, _long_running_gpu)
                for f in check(snapshot, now)]
    findings.sort(key=lambda f: (SEVERITY_ORDER[f['severity']], -(f['monthlyImpact'] or 0)))
    return findings


def _public_databases(snapshot: Snapshot, now: datetime) -> list[dict]:
    hits = [r for r in snapshot.of_type('aws.rds') if r.get('PubliclyAccessible')]
    if not hits:
        return []
    names = ', '.join(r['DBInstanceIdentifier'] for r in hits)
    return [{
        'id': 'f-rds-public',
        'family': 'security',
        'severity': 'urgent',
        'title': 'Your database is publicly accessible',
        'detail': f'{names} accepts connections from the internet. Anyone who finds the endpoint can attempt to log in.',
        'resourceIds': [resource_id('aws.rds', r) for r in hits],
        'monthlyImpact': None,
        'fix': f'aws rds modify-db-instance --db-instance-identifier {hits[0]["DBInstanceIdentifier"]} '
               f'--no-publicly-accessible --apply-immediately',
        'suggestedRule': 'No database may be publicly accessible',
        'source': 'c7n: rds · publicly-accessible',
    }]


def _open_ssh(snapshot: Snapshot, now: datetime) -> list[dict]:
    hits = []
    for sg in snapshot.of_type('aws.security-group'):
        for rule in sg.get('IpPermissions', []):
            ports = range(rule.get('FromPort', 0), rule.get('ToPort', 0) + 1)
            if 22 not in ports:
                continue
            public = any(r.get('CidrIp') == '0.0.0.0/0' for r in rule.get('IpRanges', [])) \
                or any(r.get('CidrIpv6') == '::/0' for r in rule.get('Ipv6Ranges', []))
            if public:
                hits.append(sg)
                break
    if not hits:
        return []
    return [{
        'id': 'f-ssh-open',
        'family': 'security',
        'severity': 'warning',
        'title': 'SSH is open to the entire internet',
        'detail': f'Security group {hits[0].get("GroupName")} allows port 22 from 0.0.0.0/0.',
        'resourceIds': [resource_id('aws.security-group', sg) for sg in hits],
        'monthlyImpact': None,
        'fix': f'aws ec2 revoke-security-group-ingress --group-id {hits[0]["GroupId"]} '
               f'--protocol tcp --port 22 --cidr 0.0.0.0/0',
        'suggestedRule': 'No security group may allow SSH from 0.0.0.0/0',
        'source': 'c7n: security-group · ingress',
    }]


def _unattached_volumes(snapshot: Snapshot, now: datetime) -> list[dict]:
    hits = [v for v in snapshot.of_type('aws.ebs') if not v.get('Attachments')]
    if not hits:
        return []
    impact = round(sum(_cost_per_month('aws.ebs', v) for v in hits), 2)
    oldest = min((now - v['CreateTime']).days for v in hits)
    return [{
        'id': 'f-ebs-unattached',
        'family': 'waste',
        'severity': 'warning',
        'title': f'{len(hits)} unattached EBS volume{"s" if len(hits) > 1 else ""}',
        'detail': f'Volumes bill every hour whether or not they are attached. These have been unattached '
                  f'for at least {oldest} days.',
        'resourceIds': [resource_id('aws.ebs', v) for v in hits],
        'monthlyImpact': impact,
        'fix': f'aws ec2 delete-volume --volume-id {hits[0]["VolumeId"]}',
        'suggestedRule': 'Flag EBS volumes unattached for more than 7 days',
        'source': 'c7n: ebs · Attachments: []',
    }]


def _untagged(snapshot: Snapshot, now: datetime) -> list[dict]:
    hits = [(rtype, r) for rtype in ('aws.ec2', 'aws.ebs', 'aws.rds')
            for r in snapshot.of_type(rtype) if 'Owner' not in _tags(r)]
    if not hits:
        return []
    return [{
        'id': 'f-untagged',
        'family': 'configuration',
        'severity': 'info',
        'title': f'{len(hits)} resources have no Owner tag',
        'detail': 'Without an owner, nobody gets the alert when these misbehave.',
        'resourceIds': [resource_id(rtype, r) for rtype, r in hits],
        'monthlyImpact': None,
        'fix': f'aws ec2 create-tags --resources {hits[0][1].get("InstanceId", "<id>")} --tags Key=Owner,Value=<name>',
        'suggestedRule': 'Flag any resource with no Owner tag',
        'source': 'c7n: tag:Owner absent',
    }]


def _long_running_gpu(snapshot: Snapshot, now: datetime) -> list[dict]:
    """A GPU that has been up far longer than a working day — the pattern the whole product exists for."""
    hits = [r for r in snapshot.of_type('aws.ec2')
            if r.get('State', {}).get('Name') == 'running'
            and str(r.get('InstanceType', '')).split('.')[0] in ('p2', 'p3', 'p4', 'g4', 'g4dn', 'g5', 'inf1')
            and (now - r['LaunchTime']).total_seconds() / 3600 > 12]
    if not hits:
        return []
    impact = round(sum(_cost_per_month('aws.ec2', r) for r in hits), 2)
    longest = max(hits, key=lambda r: now - r['LaunchTime'])
    hours = (now - longest['LaunchTime']).total_seconds() / 3600
    return [{
        'id': 'f-gpu-long-running',
        'family': 'behavioural',
        'severity': 'warning',
        'title': 'A GPU instance has been left running',
        'detail': f'{_tags(longest).get("Name", longest["InstanceId"])} ({longest["InstanceType"]}) has been up '
                  f'for {hours:.0f} hours — longer than any working session.',
        'resourceIds': [resource_id('aws.ec2', r) for r in hits],
        'monthlyImpact': impact,
        'fix': f'aws ec2 stop-instances --instance-ids {longest["InstanceId"]}',
        'suggestedRule': 'No GPU instance runs more than 6 hours',
        'source': 'pattern: long-running accelerator',
    }]
