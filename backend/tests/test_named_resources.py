"""Rules about one named resource: "stop my vansh-api server when its cost reaches ₹500".

Ward finds the resource itself, the compiler only writes the rule's shape, Ward pins the policy to the ID,
and the verifier proves the pinned policy ignores an identical twin.
"""
from datetime import datetime, timezone

import pytest
import yaml
from fastapi.testclient import TestClient

from app.api.deps import get_inventory
from app.compiler import clarify, targets
from app.compiler.base import Draft
from app.compiler.service import compile_rule
from app.inventory.store import Snapshot
from app.main import app
from app.verifier import fixtures as fixture_gen
from app.verifier.intents import Ec2RuntimeIntent, Target
from app.verifier.runner import verify
from app.watcher.evaluator import _stop_hint

REGION = 'ap-south-1'


class Frozen:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def latest(self):
        return self.snapshot


# ─── Resolving the name ──────────────────────────────────────────────────────

def test_a_name_resolves_to_its_id_and_leaves_the_compiler_a_name_free_sentence(sample):
    r = targets.resolve('Alert if riya-notebook runs more than 3 hours', sample.latest())
    assert r.status == 'resolved'
    assert [t.id for t in r.targets] == ['i-0b3d4']
    assert 'riya' not in r.english.lower() and 'instance' in r.english


@pytest.mark.parametrize('written', ['vansh-api', 'VanshApi', 'vansh api', 'i-03e4f'])
def test_names_match_however_they_are_written_and_ids_work_too(sample, written):
    r = targets.resolve(f'Alert if {written} runs more than 5 hours', sample.latest())
    assert [t.id for t in r.targets] == ['i-03e4f']


def test_a_rule_about_every_resource_is_left_alone(sample):
    r = targets.resolve('No GPU instance runs more than 6 hours', sample.latest())
    assert r.status == 'none' and r.english == 'No GPU instance runs more than 6 hours'


def test_a_name_that_is_also_a_word_needs_pointing_at(sample):
    assert targets.resolve('Flag any worker instance running more than 10 hours', sample.latest()).targets[0].id == 'i-06k7l'
    assert targets.resolve('Alert me about scratch work that runs over 5 hours', sample.latest()).status == 'none'


@pytest.mark.parametrize('sentence', ['stop my AlgoBench server after 5 hours', 'Alert if i-deadbeef runs more than 2 hours',
                                      'flag the instance named payments-api if it runs 4 hours'])
def test_an_unknown_resource_is_reported_never_guessed(sample, sentence):
    r = targets.resolve(sentence, sample.latest())
    assert r.status == 'not-found' and r.message
    result = compile_rule(sentence, sample, REGION)
    assert result['status'] == 'failed' and 'inventory' in result['verifier']['error']


def test_a_name_shared_by_two_resources_is_a_question_whose_answers_are_ids(sample):
    base = sample.latest()
    twin = {**next(r for r in base.of_type('aws.ec2') if r['InstanceId'] == 'i-0a1f2'), 'InstanceId': 'i-dup99'}
    snap = Snapshot(base.taken_at, {**base.resources, 'aws.ec2': [*base.of_type('aws.ec2'), twin]})
    sentence = 'Alert if ml-training runs more than 3 hours'

    asked = compile_rule(sentence, Frozen(snap), REGION)
    assert asked['status'] == 'needs-clarification'
    q = asked['questions'][0]
    assert [o['value'] for o in q['options']][:2] == ['i-0a1f2', 'i-dup99']

    picked = clarify.apply_choices(sentence, {q['term']: 'i-dup99'})
    assert compile_rule(picked, Frozen(snap), REGION, skip_clarify=True)['scope'][0]['id'] == 'i-dup99'


# ─── Cost → hours, and "stop" ────────────────────────────────────────────────

def test_a_cost_limit_becomes_a_runtime_limit_at_wards_prices(sample):
    r = targets.resolve('Stop my vansh-api server when its cost reaches ₹500', sample.latest())
    assert r.english == 'No EC2 instance runs longer than 266 hours'  # ₹500 ÷ ₹1.88/h (t3.small)
    assert any('₹1.88/hour' in a for a in r.assumptions)
    assert r.stop_requested


def test_a_cost_limit_too_large_to_watch_is_refused_with_the_arithmetic(sample):
    r = targets.resolve('stop my bastion server when cost reaches ₹50000', sample.latest())
    assert r.status == 'unsupported' and '53,192 hours' in r.message


def test_stop_becomes_an_alert_that_carries_the_command(sample):
    result = compile_rule('stop vansh-api after 5 hours', sample, REGION)
    assert result['status'] == 'compiled' and result['stopRequested'] is True
    assert 'actions' not in result['yaml'], 'Ward is read-only: the policy only watches'
    assert result['compiledAs'] == 'No instance runs longer than 5 hours'

    class Rule:
        intent = result['intent']

    class Summary:
        id, region = 'i-03e4f', 'ap-south-1'

    assert 'aws ec2 stop-instances --instance-ids i-03e4f' in _stop_hint(Rule, Summary, 'aws.ec2')


# ─── Pinning and proving it ──────────────────────────────────────────────────

def test_ward_pins_the_compiled_policy_to_the_id_and_it_matches_only_that_resource(sample):
    result = compile_rule('Alert if riya-notebook runs more than 3 hours', sample, REGION)
    assert result['status'] == 'compiled'
    policy = yaml.safe_load(result['yaml'])['policies'][0]
    assert policy['filters'][0] == {'InstanceId': 'i-0b3d4'}
    assert result['intent']['targets'][0]['id'] == 'i-0b3d4'
    matched = [m['id'] for p in result['simulation']['policies'] for m in p['matched']]
    assert matched == ['i-0b3d4'], 'ml-training also runs past 3 hours, but it isn’t riya-notebook'


def test_every_positive_has_a_twin_that_must_not_be_flagged():
    intent = Ec2RuntimeIntent(hours=5, targets=[Target(id='i-abc', name='algobench', resource_type='aws.ec2')])
    fx = fixture_gen.generate(intent, datetime.now(timezone.utc))
    positives = [f for f in fx if f.expected]
    twins = [f for f in fx if f.id.startswith('twin-')]
    assert positives and len(twins) == len(positives) and not any(t.expected for t in twins)
    assert all(f.resource['InstanceId'] == 'i-abc' for f in fx if not f.id.startswith('twin-'))


def test_a_policy_that_forgot_its_scope_fails_on_the_twin():
    intent = Ec2RuntimeIntent(hours=5, targets=[Target(id='i-abc', resource_type='aws.ec2')])
    unscoped = '''policies:
  - name: runtime
    resource: aws.ec2
    filters:
      - State.Name: running
      - type: instance-age
        op: greater-than
        hours: 5
'''
    report = verify(unscoped, fixture_gen.generate(intent), REGION)
    assert not report.passed
    assert {f.id for f in report.fixtures if f.correct is False} == {'twin-pos-over-limit', 'twin-pos-just-over'}
    scoped = targets.scope_policy(unscoped, intent.targets)
    assert verify(scoped, fixture_gen.generate(intent), REGION).passed


def test_a_rule_that_is_not_about_the_named_resource_type_is_refused(sample):
    class RdsOnly:
        name = 'fake'

        def compile(self, english):
            return Draft(english=english, kind='rds-public', explanation='x',
                         policy_yaml='policies:\n  - name: p\n    resource: aws.rds\n    filters:\n      - PubliclyAccessible: true\n')

    result = compile_rule('Alert if vansh-api runs more than 5 hours', sample, REGION, compiler=RdsOnly())
    assert result['status'] == 'failed' and 'narrowed' in result['verifier']['error']


def test_a_scoped_rule_is_stored_with_its_id_and_reverified_on_save(sample):
    app.dependency_overrides[get_inventory] = lambda: sample
    try:
        with TestClient(app) as c:
            saved = c.post('/rules', json={'english': 'Alert if vansh-api runs more than 5 hours'})
    finally:
        app.dependency_overrides.clear()
    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert body['intent']['targets'] == [{'id': 'i-03e4f', 'name': 'vansh-api', 'resource_type': 'aws.ec2'}]
    assert 'InstanceId: i-03e4f' in body['yaml']
