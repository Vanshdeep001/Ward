"""The prompt the compiler model is trained on — and therefore the only prompt it should be asked with.

A fine-tuned model learns the *shape* of its input as much as its content. Every training example was

    system: <SYSTEM>
    user:   RULE: <sentence>

            REFERENCE:
            <one schema chunk>

            <one filter chunk>

and a model asked with anything else — a bare sentence, no system message — is being tested on a
distribution it never saw. This module is the single definition of that shape, used by
04_build_dataset.py to write the training data and by try_model.py to ask the trained model.
"""
import re

SYSTEM = (
    'You write Cloud Custodian policies. Given a rule in English and reference documentation, '
    'output only valid YAML. No explanation, no markdown fences.'
)

# Stand-in for Phase 3 retrieval: one chunk per resource type, one per filter type.
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


def reference_for(pair: dict) -> str:
    """The REFERENCE block for a training pair, chosen from the verified answer (oracle retrieval)."""
    resource = resource_of(pair['policy_yaml'])
    chunks = [SCHEMA.get(resource, ''), FILTERS.get(pair['family'], '')]
    return '\n\n'.join(c for c in chunks if c)


def resource_of(policy_yaml: str) -> str:
    for line in policy_yaml.splitlines():
        if 'resource:' in line:
            return line.split('resource:', 1)[1].strip()
    return ''


# ─── Retrieval at inference time ─────────────────────────────────────────────
# Training chose the REFERENCE from the correct answer. At inference there is no answer yet, so the
# chunks are chosen from the sentence instead. This keyword scorer is a stand-in for the Phase 3
# BM25 + vector retriever: same output shape, cruder choice. When it picks the right family the model
# sees exactly what it was trained on; when it doesn't, that is a retrieval miss worth measuring.

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


# What a guardrail is *about*. The model was trained only on rules, so it answers every input with a
# policy — "hello" becomes a policy named require-greeting. It must never see a sentence that names
# nothing Ward watches.
_SUBJECT = re.compile(
    r'\b(instances?|ec2|vms?|servers?|machines?|compute|boxe?s?|nodes?|workloads?|gpus?|accelerators?|'
    r'notebooks?|training jobs?|experiments?|volumes?|ebs|disks?|storage|snapshots?|databases?|dbs?|rds|'
    r'postgres\w*|mysql|mongo\w*|redis|elasticsearch|security groups?|firewall|ports?|ssh|rdp|ftp|telnet|'
    r'ingress|inbound|remote desktop|unattached|detached|orphan\w*|0\.0\.0\.0/0|regions?|tags?|tagged|untagged|owner|costcentre|resources?|account|'
    r'mumbai|hyderabad|singapore|ireland|london|frankfurt|virginia|oregon)\b'
    r'|\b[a-z]\d[a-z]{0,3}\.(nano|micro|small|medium|\d*x?large)\b'  # t3.micro, g4dn.xlarge
    r'|\b[a-z]{2}(-[a-z]+)+-\d\b'                                    # ap-south-1
    r'|\b[gp]\d\w*\b'                                                # g5, p3 — GPU families
)
# "Nothing runs longer than 12 hours", "Kill anything running over 90 minutes": the subject is implied
# by a catch-all running for a duration. The catch-all is required — "the movie runs for two hours"
# names no subject and is not a rule.
_NUM = r'(\d+(\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)'
_RUNS_FOR = re.compile(r'\b(nothing|anything|everything|whatever)\b.*\b(run\w*|up|on|alive|left)\b.*'
                       r'(\b' + _NUM + r'\s*(h|hrs?|hours?|minutes?|mins?|days?)\b|\b(a day|a week|half a day|overnight)\b)')


def looks_like_rule(rule: str) -> bool:
    """Whether a sentence is about something a guardrail can watch. Checked before any model is asked."""
    text = rule.lower().strip()
    if len(text.split()) < 3:
        return False
    return bool(_SUBJECT.search(text) or _RUNS_FOR.search(text))


def retrieve(rule: str) -> tuple[str | None, str]:
    """Guess the rule family from the sentence and return (family, REFERENCE text)."""
    text = rule.lower()
    scores = {family: len(re.findall(pattern, text)) for family, pattern in _KEYWORDS.items()}
    # Some words are strong signals that override a weak one: a tag rule mentions a tag, a port rule a port.
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
