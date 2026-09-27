"""The baseline compiler: English → policy by pattern, with no model in the loop (SRS Phase 2).

It exists to be beaten. Phase 3's RAG pipeline and Phase 6's fine-tuned model implement the same
`Compiler` protocol, and the evaluation compares their compile rates against this one. Because every
draft it produces still goes through the verifier, a wrong pattern here fails the same way a wrong
generation would.
"""
import re

from app.compiler.base import Draft
from app.config import settings
from app.verifier.intents import (
    Ec2RuntimeIntent, EbsUnattachedIntent, InstanceTypeIntent, OpenPortIntent, RdsPublicIntent, RegionIntent,
    RequireTagIntent,
)

GPU_FILTER = '''
      - type: value
        key: InstanceType
        op: regex
        value: "^(p|g|inf)[0-9].*"'''

# Words people use for the GPU family, and for a tag that must be present.
_GPU = r'\b(gpu|g[45]\w*|p[234]\w*|inf\d?|accelerat\w+|training)\b'
_HOURS = r'(\d+(?:\.\d+)?)\s*(hours?|hrs?|h)\b'
_DAYS = r'(\d+(?:\.\d+)?)\s*(days?|d)\b'
# People write durations in words as often as digits: "longer than an hour", "up for a day".
_WORD_DURATIONS = {'an hour': 1, 'a hour': 1, 'half a day': 12, 'a day': 24, 'a week': 168,
                   'a fortnight': 336, 'a working day': 8, 'a working week': 120}


_MINUTES = r'(\d+(?:\.\d+)?)\s*(minutes?|mins?)\b'


def _duration_hours(text: str) -> float | None:
    if match := re.search(_HOURS, text):
        return float(match.group(1))
    if match := re.search(_MINUTES, text):
        return float(match.group(1)) / 60
    if match := re.search(_DAYS, text):
        return float(match.group(1)) * 24
    for phrase, hours in _WORD_DURATIONS.items():
        if phrase in text:
            return float(hours)
    return None


class TemplateCompiler:
    name = 'templates-v1'

    def compile(self, english: str) -> Draft | None:
        text = english.lower().strip()
        # Storage and tagging are checked before runtime: "storage left unattached for 90 days" is
        # about volumes, and a looser runtime pattern would otherwise read "90 days" as an age limit.
        for rule in (_instance_type, _ebs_unattached, _require_tag, _rds_public, _open_port, _region, _runtime):
            try:
                draft = rule(text, english)
            except Exception:
                # A sentence whose numbers fall outside what an intent accepts is a miss, not a crash.
                continue
            if draft is not None:
                return draft
        return None


_TYPE = r'\b([a-z][0-9][a-z]{0,3}\.(?:nano|micro|small|medium|large|(?:[248]?x?large)|(?:\d+xlarge)))\b'


def _instance_type(text: str, english: str) -> Draft | None:
    """'Only t3.micro and t2.micro are allowed' — the allowlist that keeps a lab off large hardware."""
    if not re.search(r'\b(only|allow\w*|permitted|restricted to|limited to|no larger than|nothing bigger|'
                     r'nothing other than|other than|nothing but)\b', text):
        return None
    allowed = list(dict.fromkeys(re.findall(_TYPE, text)))
    if not allowed:
        return None

    intent = InstanceTypeIntent(allowed=allowed)
    listed = ', '.join(allowed)
    return Draft(
        english=english, kind='instance-type', params={'allowed': allowed}, intent=intent,
        policy_yaml=f'''policies:
  - name: allowed-instance-types
    resource: aws.ec2
    filters:
      - State.Name: running
      - type: value
        key: InstanceType
        op: not-in
        value: [{listed}]
''',
        explanation=f'Flags running instances whose type is not one of {listed}.',
        assumptions=[
            'The match is exact: t3.micro does not permit t3.2xlarge.',
            'Only running instances are flagged — a stopped one costs storage, not compute.',
        ],
    )


def _runtime(text: str, english: str) -> Draft | None:
    """'No GPU instance runs more than 6 hours' — the canonical cost rule."""
    if not re.search(r'\b(run|running|runs|runtime|uptime|left on|still on)\b|\bup for\b', text):
        return None
    if re.search(r'\b(volume|volumes|disk|disks|unattached|detached)\b', text):
        return None  # that is a storage rule, whatever it says about days
    hours = _duration_hours(text)
    if hours is None:
        return None
    gpu_only = bool(re.search(_GPU, text))
    exempt = 'Environment' if re.search(r'\b(except|exempt|other than|unless|outside|non-?production)\b'
                                        r'.*\bproduction\b|\bnon-?production\b', text) else None

    intent = Ec2RuntimeIntent(hours=hours, gpu_only=gpu_only, exempt_tag=exempt)
    what = 'GPU instances' if gpu_only else 'EC2 instances'
    exempt_yaml = f'''
      - "tag:{exempt}": absent''' if exempt else ''
    # Custodian policy names may not contain dots, and 1.5 hours would produce one.
    slug = f'{hours:g}'.replace('.', '-')
    yaml = f'''policies:
  - name: {"gpu" if gpu_only else "ec2"}-max-runtime-{slug}h
    resource: aws.ec2
    filters:
      - State.Name: running{GPU_FILTER if gpu_only else ''}{exempt_yaml}
      - type: instance-age
        op: greater-than
        hours: {hours:g}
'''
    assumptions = ['Only running instances count — a stopped instance bills storage, not compute.']
    if gpu_only:
        assumptions.append('“GPU” means the p, g and inf instance families.')
    if exempt:
        assumptions.append(f'Instances tagged {exempt} are exempt.')
    return Draft(
        english=english, kind='ec2-runtime', params={'hours': hours, 'gpu_only': gpu_only},
        policy_yaml=yaml, intent=intent,
        explanation=f'Flags {what} that have been running for more than {hours:g} hours.',
        assumptions=assumptions,
    )


def _require_tag(text: str, english: str) -> Draft | None:
    """'Flag any resource with no Owner tag', 'No GPU instance without an expiry tag'."""
    match = re.search(r'\b(?:no|without an?|missing|lacks?|lacking)\s+([\w-]+)\s+tag\b', text) \
        or re.search(r'\b(?:have|needs?|carry|carries|declare|state|with|require[sd]?)\s+an?\s+([\w-]+)\s+tag\b', text) \
        or re.search(r'\ban?\s+([\w-]+)\s+tag\s+is\s+(?:mandatory|required)\b', text) \
        or re.search(r'\btag[: ]+([\w-]+)\s+(?:is\s+)?(?:absent|missing)\b', text) \
        or (re.search(r'\buntagged\b', text) and re.match(r'.*', 'owner'))
    if not match:
        return None
    tag = 'Owner' if match is True or not hasattr(match, 'group') else match.group(1)
    # Tag keys are case-sensitive, so the user's own casing is authoritative — CostCentre must not
    # become Costcentre. Only a lower-cased word gets a canonical form.
    known = {'owner': 'Owner', 'expiry': 'expiry', 'environment': 'Environment', 'project': 'Project',
             'team': 'Team', 'purpose': 'Purpose', 'costcentre': 'CostCentre', 'costcenter': 'CostCenter'}
    tag = tag if not tag.islower() else known.get(tag.lower(), tag.capitalize())
    on_volumes = bool(re.search(r'\b(volumes?|ebs|disks?)\b', text))
    gpu_only = bool(re.search(_GPU, text))

    resource = 'ebs' if on_volumes else 'ec2'
    intent = RequireTagIntent(tag=tag, resource=resource, gpu_only=gpu_only)
    yaml = f'''policies:
  - name: require-{tag.lower()}-tag
    resource: aws.{'ebs' if on_volumes else 'ec2'}
    filters:{GPU_FILTER if gpu_only and not on_volumes else ''}
      - "tag:{tag}": absent
'''
    return Draft(
        english=english, kind='require-tag', params={'tag': tag, 'resource': resource},
        policy_yaml=yaml, intent=intent,
        explanation=f'Flags {"volumes" if on_volumes else "instances"} that have no {tag} tag.',
        assumptions=[f'Tag keys are case-sensitive: {tag} is not the same key as {tag.lower()}.'],
    )


def _ebs_unattached(text: str, english: str) -> Draft | None:
    """'Flag EBS volumes unattached for more than 7 days' — and the free-tier rule, which is mostly this."""
    volumes = re.search(r'\b(ebs|volumes?|disks?|storage)\b', text)
    unattached = re.search(r'\b(unattached|detached|orphan\w*|unused)\b|not attached to any|attached to nothing', text)
    free_tier = re.search(r'\bfree tier\b', text)
    if not (volumes and unattached) and not free_tier:
        return None

    # No stated duration means every unattached volume: "report volumes attached to nothing" is not
    # a rule about age. The starter rulebook's phrasing says "for more than 7 days" explicitly.
    days_match = re.search(_DAYS, text)
    days = int(float(days_match.group(1))) if days_match else 0
    intent = EbsUnattachedIntent(min_age_days=days)
    age = f'''
      - type: value
        key: CreateTime
        value_type: age
        op: greater-than
        value: {days}''' if days else ''
    yaml = f'''policies:
  - name: ebs-unattached{f"-{days}d" if days else ""}
    resource: aws.ebs
    filters:
      - Attachments: []{age}
'''
    return Draft(
        english=english, kind='ebs-unattached', params={'days': days},
        policy_yaml=yaml, intent=intent,
        explanation=f'Flags EBS volumes attached to nothing for more than {days} days.',
        assumptions=[
            'Volumes bill by the hour whether or not they are attached.',
            f'“Unattached” is measured from the volume’s creation time, over {days} days.',
        ] + (['Read as the volume half of the free tier: the 30 GB allowance is spent on volumes nothing uses.'] if free_tier else []),
    )


def _rds_public(text: str, english: str) -> Draft | None:
    if not re.search(r'\b(rds|database|databases|db)\b', text):
        return None
    if not re.search(r'\b(public|publicly|internet|exposed|open to the world)\b', text):
        return None
    return Draft(
        english=english, kind='rds-public', params={}, intent=RdsPublicIntent(),
        policy_yaml='''policies:
  - name: rds-not-public
    resource: aws.rds
    filters:
      - PubliclyAccessible: true
''',
        explanation='Flags RDS databases that accept connections from the internet.',
        assumptions=['Checks the database’s own PubliclyAccessible flag, not the security group in front of it.'],
    )


def _open_port(text: str, english: str) -> Draft | None:
    if not re.search(r'\b(security group|sg|port|ssh|rdp|firewall|ingress)\b', text):
        return None
    if not re.search(r'\b(open|expos\w*|public\w*|internet|anywhere|world|reachable)\b|0\.0\.0\.0', text):
        return None
    port_match = re.search(r'\bport\s+(\d+)', text)
    port = int(port_match.group(1)) if port_match else (3389 if 'rdp' in text else 22)
    return Draft(
        english=english, kind='sg-open-port', params={'port': port}, intent=OpenPortIntent(port=port),
        policy_yaml=f'''policies:
  - name: no-public-port-{port}
    resource: aws.security-group
    filters:
      - or:
          - type: ingress
            Ports: [{port}]
            Cidr:
              value: 0.0.0.0/0
          - type: ingress
            Ports: [{port}]
            CidrV6:
              value: "::/0"
''',
        explanation=f'Flags security groups that allow port {port} from the whole internet.',
        assumptions=['Covers IPv6 (::/0) as well as IPv4 — an IPv4-only check misses half the exposure.'],
    )


def _region(text: str, english: str) -> Draft | None:
    """'No resources outside ap-south-1' — the rule that catches a forgotten instance in another region."""
    if not re.search(r'\b(outside|other than|only in|only operate in|restricted to|stay in|wrong region|'
                     r'different region)\b', text):
        return None
    # A region rule must name a region. Without this, "instances outside production" and "nothing
    # other than t3.micro" both looked like region rules, because of one stray "outside".
    match = re.search(r'\b([a-z]{2}(?:-[a-z]+)+-\d)\b', text)
    if not match:
        return None
    region = match.group(1)
    return Draft(
        english=english, kind='region', params={'region': region}, intent=RegionIntent(region=region),
        policy_yaml=f'''policies:
  - name: only-{region}
    resource: aws.ec2
    filters:
      - State.Name: running
      - type: value
        key: Placement.AvailabilityZone
        op: not-in
        value: [{region}a, {region}b, {region}c]
''',
        explanation=f'Flags running instances outside {region}.',
        assumptions=[
            f'Availability zones are matched as {region}a/b/c.',
            'Only running instances are flagged; a stopped instance elsewhere costs only its storage.',
        ],
    )
