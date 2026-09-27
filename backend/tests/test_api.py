import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_inventory
from app.main import app
from tests.test_simulator import GPU_6H


@pytest.fixture(scope='module')
def client(sample):
    app.dependency_overrides[get_inventory] = lambda: sample
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health(client):
    body = client.get('/health').json()
    assert body['status'] == 'ok'
    assert body['inventory'] == 'sample'


def test_resources_match_the_frontend_shape(client):
    body = client.get('/resources').json()
    assert len(body['items']) == 23
    ml = next(i for i in body['items'] if i['id'] == 'i-0a1f2')
    assert ml['name'] == 'ml-training'
    assert ml['type'] == 'ec2' and ml['running'] is True
    assert ml['costPerHour'] == 66.05
    assert ml['tags'] == {}


def test_verify_with_generated_fixtures(client):
    res = client.post('/rules/verify', json={'policy_yaml': GPU_6H, 'intent': {'kind': 'ec2-runtime', 'hours': 6, 'gpu_only': True}})
    assert res.status_code == 200
    assert res.json()['passed'] is True


def test_verify_with_custom_fixtures(client):
    fixtures = [
        {'id': 'bad', 'resource_type': 'aws.rds', 'expected': True,
         'resource': {'DBInstanceIdentifier': 'db-a', 'PubliclyAccessible': True, 'Tags': []}},
        {'id': 'ok', 'resource_type': 'aws.rds', 'expected': False,
         'resource': {'DBInstanceIdentifier': 'db-b', 'PubliclyAccessible': False, 'Tags': []}},
    ]
    policy = 'policies:\n  - name: p\n    resource: aws.rds\n    filters:\n      - PubliclyAccessible: true\n'
    body = client.post('/rules/verify', json={'policy_yaml': policy, 'fixtures': fixtures}).json()
    assert body['passed'] is True
    assert body['actual'] == ['db-a']


def test_verify_requires_exactly_one_fixture_source(client):
    res = client.post('/rules/verify', json={'policy_yaml': GPU_6H})
    assert res.status_code == 422


def test_verify_rejects_unknown_intent(client):
    res = client.post('/rules/verify', json={'policy_yaml': GPU_6H, 'intent': {'kind': 'delete-everything'}})
    assert res.status_code == 422


def test_fixture_preview_is_json_serialisable(client):
    res = client.post('/rules/verify/fixtures', json={'intent': {'kind': 'ebs-unattached', 'min_age_days': 7}})
    assert res.status_code == 200
    assert {f['kind'] for f in res.json()} == {'positive', 'negative', 'edge'}


def test_simulate_returns_matches_and_history(client):
    body = client.post('/rules/simulate', json={'policy_yaml': GPU_6H}).json()
    [policy] = body['policies']
    assert {m['id'] for m in policy['matched']} == {'i-0a1f2', 'i-0b3d4'}
    assert body['history']['fires'] == 8


def test_simulate_can_skip_history(client):
    body = client.post('/rules/simulate', json={'policy_yaml': GPU_6H, 'history_days': 0}).json()
    assert body['history'] is None


def test_simulate_invalid_policy_is_422(client):
    res = client.post('/rules/simulate', json={'policy_yaml': 'policies: [oops'})
    assert res.status_code == 422
    assert 'Not valid YAML' in res.json()['detail']


def test_alerts_carry_live_resource_facts_not_just_prose(client):
    """The Alerts page groups and lays out resources from structured facts — never by parsing the message."""
    client.post('/watcher/sweep')
    alerts = client.get('/alerts').json()
    assert alerts, 'a sweep of the sample account should open alerts'

    ec2 = next(a for a in alerts if a['resource']['type'] == 'aws.ec2' and a['resource'].get('present'))
    assert ec2['resource']['detail']  # the instance type, e.g. g5.xlarge
    assert ec2['resource']['region']
    assert 'runningHours' in ec2['resource'] and 'costPerDay' in ec2['resource']
