import pytest

from app.verifier.fixtures import generate
from app.verifier.intents import OpenPortIntent
from app.verifier.runner import verify
from tests.gold_policies import GOLD

GPU_6H, GPU_POLICY = GOLD[0]


def failing(report):
    return {f.id for f in report.fixtures if not f.correct}


@pytest.mark.parametrize('intent', [i for i, _ in GOLD], ids=lambda i: i.kind)
def test_every_intent_has_the_minimum_fixture_mix(intent):
    kinds = [f.kind for f in generate(intent)]
    assert kinds.count('positive') >= 2
    assert kinds.count('negative') >= 2
    assert kinds.count('edge') >= 1


@pytest.mark.parametrize('intent,policy', GOLD, ids=lambda x: getattr(x, 'kind', None))
def test_gold_policy_passes_its_fixtures(intent, policy):
    report = verify(policy, generate(intent))
    assert report.error is None
    assert report.passed, f'unexpected results on {failing(report)}'
    assert report.rates.positive_pass == report.rates.negative_pass == report.rates.edge_pass == 1.0


def test_wrong_threshold_misses_violations():
    twelve_hours = GPU_POLICY.replace('hours: 6', 'hours: 12')
    report = verify(twelve_hours, generate(GPU_6H))
    assert not report.passed
    assert 'pos-just-over' in failing(report)  # an 8-hour GPU session slips past a 12-hour limit
    assert report.rates.positive_pass < 1.0
    assert report.rates.negative_pass == 1.0


def test_forgetting_the_running_check_flags_stopped_instances():
    no_state = GPU_POLICY.replace('      - State.Name: running\n', '')
    report = verify(no_state, generate(GPU_6H))
    assert failing(report) == {'edge-stopped'}


def test_policy_that_flags_everything_fails_negatives():
    everything = 'policies:\n  - name: all\n    resource: aws.ec2\n'
    report = verify(everything, generate(GPU_6H))
    assert not report.passed
    assert report.rates.positive_pass == 1.0
    assert report.rates.negative_pass == 0.0


def test_ipv4_only_ssh_check_misses_ipv6_exposure():
    ipv4_only = '''
policies:
  - name: ssh-v4-only
    resource: aws.security-group
    filters:
      - type: ingress
        Ports: [22]
        Cidr:
          value: 0.0.0.0/0
'''
    report = verify(ipv4_only, generate(OpenPortIntent(port=22)))
    assert failing(report) == {'edge-ipv6-open'}


@pytest.mark.parametrize('policy,message', [
    ('policies: [unclosed', 'Not valid YAML'),
    ('rules: []', "non-empty 'policies' list"),
    ('policies:\n  - name: x\n    resource: aws.ec2\n    filters:\n      - type: instance-age\n        hourz: 6\n', 'hourz'),
    ('policies:\n  - name: x\n    resource: aws.lambda\n', 'not supported'),
    ('policies:\n  - name: x\n    resource: aws.ebs\n    filters:\n      - Attachments: []\n', 'about aws.ec2'),
])
def test_invalid_policies_produce_a_failed_report_with_a_reason(policy, message):
    report = verify(policy, generate(GPU_6H))
    assert not report.passed
    assert message in report.error
    assert all(f.actual is None for f in report.fixtures)


def test_short_resource_names_are_accepted():
    policy = GPU_POLICY.replace('resource: aws.ec2', 'resource: ec2')
    assert verify(policy, generate(GPU_6H)).passed


def test_verification_is_fast_once_warm():
    report = verify(GPU_POLICY, generate(GPU_6H))
    assert report.duration_ms < 1000
