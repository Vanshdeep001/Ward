"""Builders for resources in the exact shape boto3's describe-* calls return.

Used by verifier fixtures and the sample account. Custodian reads specific fields — instance age comes from
the root volume's AttachTime, security-group filters need OwnerId — so shortcuts here cause false results.
"""
from datetime import datetime, timedelta

ACCOUNT_ID = '000000000000'


def _tags(tags: dict[str, str] | None) -> list[dict]:
    return [{'Key': k, 'Value': v} for k, v in (tags or {}).items()]


def ec2(instance_id: str, instance_type: str, *, launched: datetime, running: bool = True,
        tags: dict[str, str] | None = None, region: str = 'ap-south-1') -> dict:
    return {
        'InstanceId': instance_id,
        'InstanceType': instance_type,
        'State': {'Code': 16 if running else 80, 'Name': 'running' if running else 'stopped'},
        'LaunchTime': launched,
        'Placement': {'AvailabilityZone': f'{region}a'},
        'BlockDeviceMappings': [
            {'DeviceName': '/dev/xvda', 'Ebs': {'AttachTime': launched, 'DeleteOnTermination': True, 'Status': 'attached', 'VolumeId': f'vol-root-{instance_id[2:]}'}},
        ],
        'Tags': _tags(tags),
    }


def ebs(volume_id: str, *, created: datetime, size_gb: int = 20, attached_to: str | None = None,
        tags: dict[str, str] | None = None, region: str = 'ap-south-1') -> dict:
    attachments = [{'InstanceId': attached_to, 'State': 'attached', 'VolumeId': volume_id, 'AttachTime': created}] if attached_to else []
    return {
        'VolumeId': volume_id,
        'Size': size_gb,
        'VolumeType': 'gp3',
        'State': 'in-use' if attached_to else 'available',
        'CreateTime': created,
        'AvailabilityZone': f'{region}a',
        'Attachments': attachments,
        'Tags': _tags(tags),
    }


def rds(identifier: str, instance_class: str, *, created: datetime, public: bool = False, status: str = 'available',
        tags: dict[str, str] | None = None) -> dict:
    # boto3 returns TagList; Custodian's RDS augment step renames it to Tags. We store the post-augment shape.
    return {
        'DBInstanceIdentifier': identifier,
        'DBInstanceClass': instance_class,
        'DBInstanceStatus': status,
        'Engine': 'postgres',
        'PubliclyAccessible': public,
        'InstanceCreateTime': created,
        'Tags': _tags(tags),
    }


def ingress(port_from: int | None, port_to: int | None = None, *, ipv4: tuple[str, ...] = (), ipv6: tuple[str, ...] = (),
            protocol: str = 'tcp') -> dict:
    rule = {
        'IpProtocol': protocol,
        'IpRanges': [{'CidrIp': c} for c in ipv4],
        'Ipv6Ranges': [{'CidrIpv6': c} for c in ipv6],
        'UserIdGroupPairs': [],
        'PrefixListIds': [],
    }
    if port_from is not None:
        rule['FromPort'] = port_from
        rule['ToPort'] = port_to if port_to is not None else port_from
    return rule


def security_group(group_id: str, name: str, *, rules: list[dict], tags: dict[str, str] | None = None) -> dict:
    return {
        'GroupId': group_id,
        'GroupName': name,
        'OwnerId': ACCOUNT_ID,
        'VpcId': 'vpc-0dev',
        'IpPermissions': rules,
        'IpPermissionsEgress': [],
        'Tags': _tags(tags),
    }


def nat_gateway(nat_id: str, *, created: datetime, vpc: str = 'vpc-dev-2', tags: dict[str, str] | None = None) -> dict:
    return {'NatGatewayId': nat_id, 'State': 'available', 'VpcId': vpc, 'CreateTime': created, 'Tags': _tags(tags)}


def hours_ago(now: datetime, hours: float) -> datetime:
    return now - timedelta(hours=hours)
