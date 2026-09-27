"""Hand-written, verified starter rules (SRS §2) — the default rulebook, and the tests' gold policies."""
from dataclasses import dataclass

from app.verifier.intents import (
    Ec2RuntimeIntent, EbsUnattachedIntent, OpenPortIntent, RdsPublicIntent, RequireTagIntent,
)

GPU_REGEX = '''
      - type: value
        key: InstanceType
        op: regex
        value: "^(p|g|inf)[0-9].*"'''


@dataclass(frozen=True)
class RuleTemplate:
    english: str
    intent: object
    policy_yaml: str


STARTER = (
    RuleTemplate('No GPU instance runs more than 6 hours', Ec2RuntimeIntent(hours=6, gpu_only=True), f'''
policies:
  - name: gpu-max-6h
    resource: aws.ec2
    filters:
      - State.Name: running{GPU_REGEX}
      - type: instance-age
        op: greater-than
        hours: 6
'''),
    RuleTemplate('Flag any EC2 instance with no Owner tag', RequireTagIntent(tag='Owner'), '''
policies:
  - name: require-owner
    resource: aws.ec2
    filters:
      - "tag:Owner": absent
'''),
    RuleTemplate('Flag EBS volumes unattached for more than 7 days', EbsUnattachedIntent(min_age_days=7), '''
policies:
  - name: ebs-unattached-7d
    resource: aws.ebs
    filters:
      - Attachments: []
      - type: value
        key: CreateTime
        value_type: age
        op: greater-than
        value: 7
'''),
    RuleTemplate('No database may be publicly accessible', RdsPublicIntent(), '''
policies:
  - name: rds-not-public
    resource: aws.rds
    filters:
      - PubliclyAccessible: true
'''),
    RuleTemplate('No security group may allow SSH from the internet', OpenPortIntent(port=22), '''
policies:
  - name: no-public-ssh
    resource: aws.security-group
    filters:
      - or:
          - type: ingress
            Ports: [22]
            Cidr:
              value: 0.0.0.0/0
          - type: ingress
            Ports: [22]
            CidrV6:
              value: "::/0"
'''),
)
