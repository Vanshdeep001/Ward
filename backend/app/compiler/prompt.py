"""The prompt the fine-tuned compiler was trained on — the only prompt it should be asked with.

A fine-tuned model learns the *shape* of its input as much as its content, so the backend must ask it
exactly as finetune/scripts/prompting.py built the training data. This is a copy of that definition,
not an import: the backend is deployed without the finetune/ folder. tests/test_llm_compiler.py fails
if the two ever differ, which is the point — change them together or not at all.
"""
import re

SYSTEM = (
    'You write Cloud Custodian policies. Given a rule in English and reference documentation, '
    'output only valid YAML. No explanation, no markdown fences.'
)

SCHEMA = {
    'aws.ec2': 'resource: aws.ec2 — EC2 instances. Fields: InstanceId, InstanceType, State.Name '
               '(running|stopped), LaunchTime, Placement.AvailabilityZone, Tags. Instance age is read '
               'from the root volume attach time, not LaunchTime.',
    'aws.ebs': 'resource: aws.ebs — EBS volumes. Fields: VolumeId, Size, State (in-use|available), '
               'CreateTime, Attachments (empty list means attached to nothing), Tags.',
    'aws.rds': 'resource: aws.rds — RDS instances. Fields: DBInstanceIdentifier, DBInstanceClass, '
               'PubliclyAccessible (bool), Engine, Tags.',
    'aws.security-group': 'resource: aws.security-group — security groups. Fields: GroupId, GroupName, '
                          'IpPermissions[].FromPort/ToPort, IpRanges[].CidrIp, Ipv6Ranges[].CidrIpv6.',
}
FILTERS = {
    'ec2-runtime': 'filter instance-age — matches on how long an instance has been running. Takes op '
                   '(greater-than|less-than) and hours or days. Pair it with State.Name: running.',
    'require-tag': 'filter "tag:<Key>": absent — matches resources missing that tag key. Tag keys are '
                   'case-sensitive.',
    'ebs-unattached': 'filter Attachments: [] — matches volumes attached to nothing. Combine with a '
                      'value filter on CreateTime with value_type: age for a minimum age.',
    'rds-public': 'filter PubliclyAccessible: true — matches databases reachable from the internet.',
    'sg-open-port': 'filter type: ingress — takes Ports, Cidr (IPv4) and CidrV6. 0.0.0.0/0 is the whole '
                    'internet over IPv4; ::/0 is the whole internet over IPv6.',
    'instance-type': 'filter type: value with key InstanceType and op in/not-in — matches an allowlist '
                     'of instance types. The match is exact.',
    'region': 'filter type: value with key Placement.AvailabilityZone and op not-in — availability zones '
              'are the region plus a letter suffix.',
}

# Keyword retrieval — a stand-in for the Phase 3 BM25 + vector retriever. Same output shape.
_KEYWORDS = {
    'ec2-runtime': r'\b(run|runs|running|runtime|uptime|hours?|hrs?|minutes?|overnight|longer|stay up|up for|'
                   r'left on|still on|a day|a week)\b',
    'require-tag': r'\b(tag|tags|tagged|untagged|owner|label)\b',
    'ebs-unattached': r'\b(ebs|volumes?|disks?|storage|unattached|detached|orphan\w*|attached to nothing|free tier)\b',
    'rds-public': r'\b(rds|database|databases|db)\b',
    'sg-open-port': r'\b(port|ssh|rdp|security groups?|ingress|firewall|0\.0\.0\.0|expos\w*)\b',
    'instance-type': r'\b(only|allowed|permitted|restricted to|limited to|bigger than|other than)\b|'
                     r'\b[a-z]\d[a-z]{0,3}\.(nano|micro|small|medium|\d*x?large)\b',
    'region': r'\b[a-z]{2}(-[a-z]+)+-\d\b|\bregion\b',
}
_RESOURCE = {
    'ec2-runtime': 'aws.ec2', 'instance-type': 'aws.ec2', 'region': 'aws.ec2',
    'ebs-unattached': 'aws.ebs', 'rds-public': 'aws.rds', 'sg-open-port': 'aws.security-group',
}


def retrieve(rule: str) -> tuple[str | None, str]:
    """Guess the rule family from the sentence and return (family, REFERENCE text)."""
    text = rule.lower()
    scores = {family: len(re.findall(pattern, text)) for family, pattern in _KEYWORDS.items()}
    if scores['require-tag']:
        scores['require-tag'] += 2
    if re.search(r'\b(public\w*|internet|world)\b', text) and scores['rds-public']:
        scores['rds-public'] += 2
    family, best = max(scores.items(), key=lambda kv: kv[1])
    if best == 0:
        return None, ''

    resource = _RESOURCE.get(family)
    if family == 'require-tag':
        resource = 'aws.ebs' if re.search(r'\b(volumes?|ebs|disks?|storage)\b', text) else 'aws.ec2'
    chunks = [SCHEMA.get(resource, ''), FILTERS.get(family, '')]
    return family, '\n\n'.join(c for c in chunks if c)


def build_messages(rule: str, reference: str | None) -> list[dict]:
    """The chat input exactly as training presented it. `reference=None` omits the block."""
    user = f'RULE: {rule}'
    if reference:
        user += f'\n\nREFERENCE:\n{reference}'
    return [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user}]
