"""Hand-written correct policies for each intent. If one fails its own fixtures, the fixture labels are wrong."""
from app.verifier.intents import (
    Ec2RuntimeIntent, EbsUnattachedIntent, OpenPortIntent, RdsPublicIntent, RequireTagIntent,
)

GPU_REGEX = '''
      - type: value
        key: InstanceType
        op: regex
        value: "^(p|g|inf)[0-9].*"'''

GOLD = [
    (Ec2RuntimeIntent(hours=6, gpu_only=True), f'''
policies:
  - name: gpu-max-6h
    resource: aws.ec2
    filters:
      - State.Name: running{GPU_REGEX}
      - type: instance-age
        op: greater-than
        hours: 6
'''),
    (Ec2RuntimeIntent(hours=6, exempt_tag='Environment'), '''
policies:
  - name: max-6h-unless-environment
    resource: aws.ec2
    filters:
      - State.Name: running
      - "tag:Environment": absent
      - type: instance-age
        op: greater-than
        hours: 6
'''),
    (Ec2RuntimeIntent(hours=24), '''
policies:
  - name: max-24h
    resource: aws.ec2
    filters:
      - State.Name: running
      - type: instance-age
        op: greater-than
        hours: 24
'''),
    (RequireTagIntent(tag='Owner'), '''
policies:
  - name: require-owner
    resource: aws.ec2
    filters:
      - "tag:Owner": absent
'''),
    (RequireTagIntent(tag='ExpiresAt', gpu_only=True), f'''
policies:
  - name: gpu-require-expiry
    resource: aws.ec2
    filters:
      - "tag:ExpiresAt": absent{GPU_REGEX}
'''),
    (RequireTagIntent(tag='Owner', resource='ebs'), '''
policies:
  - name: ebs-require-owner
    resource: aws.ebs
    filters:
      - "tag:Owner": absent
'''),
    (EbsUnattachedIntent(), '''
policies:
  - name: ebs-unattached
    resource: aws.ebs
    filters:
      - Attachments: []
'''),
    (EbsUnattachedIntent(min_age_days=7), '''
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
    (RdsPublicIntent(), '''
policies:
  - name: rds-not-public
    resource: aws.rds
    filters:
      - PubliclyAccessible: true
'''),
    (OpenPortIntent(port=22), '''
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
]
