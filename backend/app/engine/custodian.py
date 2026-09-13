"""Cloud Custodian, used entirely in memory: parse and validate policy YAML, then filter resource dicts.

Nothing here calls AWS. Resources must match boto3's describe-* shapes exactly (real datetime objects,
BlockDeviceMappings on instances, OwnerId on security groups), because Custodian's filters read those fields.
"""
import copy
import re
from dataclasses import dataclass
from functools import lru_cache

import yaml
from c7n.config import Config
from c7n.exceptions import PolicyValidationError
from c7n.loader import PolicyLoader
from c7n.resources import load_resources

SUPPORTED_RESOURCES = ('aws.ec2', 'aws.ebs', 'aws.rds', 'aws.security-group', 'aws.nat-gateway')

ID_KEYS = {
    'aws.ec2': 'InstanceId',
    'aws.ebs': 'VolumeId',
    'aws.rds': 'DBInstanceIdentifier',
    'aws.security-group': 'GroupId',
    'aws.nat-gateway': 'NatGatewayId',
}

LABELS = {
    'aws.ec2': 'EC2 instances',
    'aws.ebs': 'EBS volumes',
    'aws.rds': 'RDS databases',
    'aws.security-group': 'security groups',
    'aws.nat-gateway': 'NAT Gateways',
}

_ACCOUNT_ID = '000000000000'


class PolicyError(ValueError):
    """The policy text is not valid YAML, not a Custodian policy, or fails Custodian's schema."""


@dataclass
class FunnelStep:
    filter: str
    remaining: int


@lru_cache(maxsize=4)
def _loader(region: str) -> PolicyLoader:
    load_resources(SUPPORTED_RESOURCES)
    return PolicyLoader(Config.empty(region=region, account_id=_ACCOUNT_ID))


def warm_up(region: str) -> None:
    """Importing Custodian's resource registry takes seconds; do it at startup, not on the first request."""
    _loader(region)


def load_policies(policy_yaml: str, region: str):
    try:
        data = yaml.safe_load(policy_yaml)
    except yaml.YAMLError as e:
        raise PolicyError(f'Not valid YAML: {e}') from e

    if not isinstance(data, dict) or not isinstance(data.get('policies'), list) or not data['policies']:
        raise PolicyError("Expected a YAML mapping with a non-empty 'policies' list.")

    for p in data['policies']:
        if not isinstance(p, dict):
            raise PolicyError('Each entry under policies must be a mapping.')
        resource = str(p.get('resource', ''))
        if resource and '.' not in resource:
            resource = p['resource'] = f'aws.{resource}'
        if resource not in SUPPORTED_RESOURCES:
            raise PolicyError(f"Resource '{p.get('resource')}' is not supported yet. Supported: {', '.join(SUPPORTED_RESOURCES)}.")

    try:
        collection = _loader(region).load_data(data, file_uri='memory://ward', validate=True)
    except PolicyValidationError as e:
        raise PolicyError(_tidy(str(e))) from e
    return list(collection)


def run_filters(policy, resources: list[dict]) -> tuple[list[dict], list[FunnelStep]]:
    """Apply a policy's filters in order, recording how many resources survive each one.

    Mirrors ResourceManager.filter_resources, which applies filters sequentially and stops once nothing is left.
    Resources are deep-copied because Custodian annotates the dicts it matches.
    """
    current = copy.deepcopy(resources)
    steps = []
    for f in policy.resource_manager.filters:
        if current:
            current = f.process(current, None)
        steps.append(FunnelStep(filter=describe_filter(f.data), remaining=len(current)))
    return current, steps


def resource_id(resource_type: str, resource: dict) -> str:
    return resource[ID_KEYS[resource_type]]


def describe_filter(data) -> str:
    """A short human label for a filter block, used in funnels and zero-match explanations."""
    if not isinstance(data, dict):
        return str(data)
    if len(data) == 1 and next(iter(data)) in ('or', 'and', 'not'):
        op, children = next(iter(data.items()))
        return f' {op} '.join(describe_filter(c) for c in children) if op != 'not' else f"not ({describe_filter(children)})"
    if 'type' not in data:
        return ', '.join(f'{k}: {v}' for k, v in data.items())
    kind = data['type']
    if kind == 'value':
        return f"{data.get('key')} {data.get('op', 'equals')} {data.get('value')}"
    if kind == 'instance-age':
        unit = 'hours' if 'hours' in data else 'days'
        return f"running {data.get('op', 'greater-than')} {data.get(unit)} {unit}"
    detail = ', '.join(f'{k}={v}' for k, v in data.items() if k != 'type')
    return f'{kind} ({detail})' if detail else kind


def _tidy(message: str) -> str:
    return re.sub(r'\s+', ' ', message).strip()
