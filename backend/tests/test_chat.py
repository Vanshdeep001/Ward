"""Copilot. Every answer is computed from the account, so these assert against real numbers."""
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_inventory
from app.main import app


@pytest.fixture(scope='module')
def client(sample):
    app.dependency_overrides[get_inventory] = lambda: sample
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def ask(client, message, state=None):
    return client.post('/chat', json={'message': message, 'state': state or {}}).json()


def test_asking_ward_to_change_something_is_refused_with_the_command(client):
    """Read-only is the design (SRS §7), so Ward explains and hands over the command."""
    body = ask(client, 'stop ml-training')

    assert body['message']['intent'] == 'REFUSE'
    assert 'read-only' in body['message']['text'].lower()
    assert body['message']['command'].startswith('aws ec2 stop-instances')
    assert 'i-0a1f2' in body['message']['command'], 'the named resource should be resolved to its id'


def test_spend_questions_are_answered_with_this_accounts_numbers(client):
    body = ask(client, 'what is costing me the most?')

    assert body['message']['intent'] == 'ANSWER'
    assert body['message']['table'], 'the answer should name resources, not just a total'
    assert body['message']['table'][0]['costPerDay'] > 0
    assert body['state']['referentId'], 'the top line becomes the referent for follow-ups'


def test_why_did_my_bill_change_names_the_mover(client):
    body = ask(client, 'why did my bill go up?')

    assert body['message']['intent'] == 'ANSWER'
    assert '/day' in body['message']['text']
    assert body['message']['table']


def test_a_follow_up_uses_the_resource_from_the_previous_answer(client):
    first = ask(client, 'what is costing me the most?')
    second = ask(client, 'create a rule so that does not happen again', first['state'])

    assert second['message']['intent'] == 'ACT'
    draft = second['message']['draft']
    assert draft['english'] and draft['yaml']
    assert draft['matched'] >= 1, 'a drafted rule should be simulated against the account'


def test_asking_for_a_rule_with_no_context_asks_which_resource(client):
    body = ask(client, 'create a guardrail')

    assert body['message']['intent'] == 'ACT'
    assert 'which resource' in body['message']['text'].lower()


def test_risk_questions_surface_the_urgent_finding_first(client):
    body = ask(client, 'what is exposed?')

    assert 'publicly accessible' in body['message']['text']
    assert body['message']['command'].startswith('aws rds modify-db-instance')


def test_an_unrecognised_question_offers_what_ward_can_answer(client):
    body = ask(client, 'hello there')
    assert body['message']['intent'] == 'ANSWER'
    assert 'spend' in body['message']['text']
