"""Correct policies for each intent. If one fails its own fixtures, the fixture labels are wrong."""
from app.library import GPU_REGEX, STARTER
from app.verifier.intents import Ec2RuntimeIntent, EbsUnattachedIntent, RequireTagIntent

GOLD = [(t.intent, t.policy_yaml) for t in STARTER] + [
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
]
