"""The router sorts what was typed — rule, question or small talk — before the compiler sees it.
The router model is faked with httpx.MockTransport: these tests are about Ward's side of the call."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_inventory, get_router
from app.compiler.router import NOT_A_RULE, Router, _parse
from app.main import app


def fake(reply: dict | str | Exception):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        if isinstance(reply, Exception):
            raise reply
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return httpx.Response(200, json={'choices': [{'message': {'content': content}}]})
    return Router('http://m/v1', 'key', 'router-model', transport=httpx.MockTransport(handler)), calls


def test_small_talk_never_costs_a_model_call():
    router, calls = fake({'route': 'rule', 'answer': ''})
    route = router.route('hello')
    assert route.kind == 'other' and route.by == 'gate' and route.answer == NOT_A_RULE
    assert calls == []


def test_a_question_about_a_cloud_word_is_answered_not_compiled():
    router, calls = fake({'route': 'question', 'answer': 'A server is a computer that runs your app.'})
    route = router.route('what is server ?')
    assert route.kind == 'question' and route.by == 'model'
    assert route.answer == 'A server is a computer that runs your app.'
    assert calls[0]['messages'][1] == {'role': 'user', 'content': 'what is server ?'}
    assert calls[0]['temperature'] == 0


def test_a_rule_goes_through():
    router, _ = fake({'route': 'rule', 'answer': ''})
    route = router.route("Don't expose Redis to the world")
    assert route.is_rule and route.answer is None


def test_the_reply_may_be_wrapped_in_prose_or_fences():
    route = _parse('Sure!\n```json\n{"route": "other", "answer": ""}\n```')
    assert route.kind == 'other' and route.answer == NOT_A_RULE, 'an empty answer gets the standard one'
    assert _parse('no json here') is None
    assert _parse('{"route": "maybe"}') is None


@pytest.mark.parametrize('sentence, kind', [
    ('what is server ?', 'question'),
    ('How much does a t3.micro instance cost?', 'question'),
    ('No GPU instance may run for more than 6 hours', 'rule'),
])
def test_when_the_router_model_is_down_a_heuristic_decides(sentence, kind):
    router, _ = fake(httpx.ConnectError('down'))
    route = router.route(sentence)
    assert route.kind == kind and route.by == 'heuristic'


def test_without_a_router_model_it_still_works():
    router = Router()
    assert router.route('what is an ec2 instance?').kind == 'question'
    assert router.route('No GPU instance may run for more than 6 hours').is_rule


def test_the_compile_endpoint_answers_instead_of_inventing_a_policy(sample):
    router, _ = fake({'route': 'question', 'answer': 'A server is a computer that runs your app.'})
    app.dependency_overrides[get_inventory] = lambda: sample
    app.dependency_overrides[get_router] = lambda: router
    try:
        with TestClient(app) as c:
            body = c.post('/rules/compile', json={'english': 'what is server ?'}).json()
    finally:
        app.dependency_overrides.clear()
    assert body == {'status': 'not-a-rule', 'english': 'what is server ?', 'route': 'question',
                    'answer': 'A server is a computer that runs your app.', 'decidedBy': 'model'}
