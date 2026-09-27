"""The fine-tuned compiler, reached over HTTP. The model server is faked with httpx.MockTransport:
these tests are about Ward's side of the conversation, and need neither a model nor a network."""
import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_compiler, get_inventory
from app.compiler import prompt
from app.compiler.llm import HybridCompiler, LlmCompiler
from app.compiler.service import compile_rule
from app.main import app
from tests.conftest import REGION

GPU_6H = '''policies:
  - name: gpu-max-runtime-6h
    resource: aws.ec2
    filters:
      - State.Name: running
      - type: value
        key: InstanceType
        op: regex
        value: "^(p|g|inf)[0-9].*"
      - type: instance-age
        op: greater-than
        hours: 6
'''
# The v1 model's real mistake: the word "gpu" leaks into the regex, which then matches no instance type.
GPU_6H_LEAKED = GPU_6H.replace('"^(p|g|inf)[0-9].*"', '"^(p|g|inf)[0-9].*gpu"')
UNREADABLE = "Don't let the big GPU box run overnight"  # the templates cannot parse "overnight"


class FakeModelServer:
    """Answers /chat/completions with a fixed policy and remembers what it was asked."""

    def __init__(self, answer: str = GPU_6H, fail: Exception | None = None):
        self.answer, self.fail, self.requests = answer, fail, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.fail:
            raise self.fail
        self.requests.append(json.loads(request.content) if request.content else None)
        if request.url.path.endswith('/models'):
            return httpx.Response(200, json={'data': [{'id': 'ward-compiler'}]})
        return httpx.Response(200, json={'choices': [{'message': {'role': 'assistant', 'content': self.answer}}]})


def compiler_for(server: FakeModelServer, prefer_llm: bool = False) -> HybridCompiler:
    llm = LlmCompiler('http://model/v1', 'ward-compiler', transport=httpx.MockTransport(server))
    return HybridCompiler(llm, prefer_llm=prefer_llm)


# ─── Asked the way it was trained ─────────────────────────────────────────────

def test_the_backend_prompt_is_the_one_the_model_was_trained_on():
    """The backend keeps its own copy (it ships without finetune/). This is what keeps them equal."""
    path = Path(__file__).resolve().parents[2] / 'finetune' / 'scripts' / 'prompting.py'
    if not path.exists():
        pytest.skip('finetune/ not present in this checkout')
    spec = importlib.util.spec_from_file_location('training_prompting', path)
    training = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(training)

    assert prompt.SYSTEM == training.SYSTEM
    assert prompt.SCHEMA == training.SCHEMA
    assert prompt.FILTERS == training.FILTERS
    for rule in ['No GPU runs over 6 hours', 'Every volume needs an Owner tag', 'SSH open to the internet',
                 'Only t3.micro allowed', 'No resources outside eu-west-1', UNREADABLE, 'make it cheaper']:
        assert prompt.retrieve(rule) == training.retrieve(rule)
        assert prompt.build_messages(rule, 'ref') == training.build_messages(rule, 'ref')


def test_the_model_is_asked_in_the_trained_shape_and_greedily():
    server = FakeModelServer()
    compiler_for(server, prefer_llm=True).compile('No GPU instance runs more than 6 hours')

    body = server.requests[0]
    assert body['temperature'] == 0
    system, user = body['messages']
    assert system == {'role': 'system', 'content': prompt.SYSTEM}
    assert user['content'].startswith('RULE: No GPU instance runs more than 6 hours')
    assert '\n\nREFERENCE:\n' in user['content'] and 'instance-age' in user['content']


# ─── hybrid: templates first ──────────────────────────────────────────────────

def test_hybrid_uses_the_templates_when_they_can_read_the_sentence(sample):
    server = FakeModelServer()
    result = compile_rule('No GPU instance runs more than 6 hours', sample, REGION, compiler=compiler_for(server))

    assert result['status'] == 'compiled'
    assert result['compiler'] == 'templates-v1'
    assert server.requests == [], 'the model should not be asked what the templates already know'


def test_hybrid_asks_the_model_only_for_what_the_templates_cannot_read(sample):
    server = FakeModelServer(GPU_6H)
    result = compile_rule(UNREADABLE, sample, REGION, compiler=compiler_for(server), skip_clarify=True)

    assert result['status'] == 'unverified'
    assert result['compiler'] == 'llm:ward-compiler'
    assert 'nothing independent' in result['reason']
    assert result['simulation']['policies'], 'an unverified draft still shows what it would match'
    assert 'verifier' not in result, 'nothing was verified, so nothing should claim to have been'


# ─── llm: the model writes everything, graded where it can be ─────────────────

def test_llm_mode_grades_the_model_against_the_templates_reading(sample):
    result = compile_rule('No GPU instance runs more than 6 hours', sample, REGION,
                          compiler=compiler_for(FakeModelServer(GPU_6H), prefer_llm=True))
    assert result['status'] == 'compiled'
    assert result['verifier']['passed'] is True
    assert result['compiler'] == 'llm:ward-compiler'


def test_llm_mode_catches_the_real_v1_mistake(sample):
    """The leaked-"gpu" regex from validation: valid YAML, valid Custodian, matches nothing."""
    result = compile_rule('No GPU instance runs more than 6 hours', sample, REGION,
                          compiler=compiler_for(FakeModelServer(GPU_6H_LEAKED), prefer_llm=True))
    assert result['status'] == 'failed'
    assert 'missed' in result['verifier']['error']


# ─── Safety and failure ───────────────────────────────────────────────────────

def test_a_policy_with_actions_is_refused_whoever_wrote_it(sample):
    terminate = GPU_6H + '    actions:\n      - terminate\n'
    result = compile_rule(UNREADABLE, sample, REGION, compiler=compiler_for(FakeModelServer(terminate)),
                          skip_clarify=True)

    assert result['status'] == 'failed'
    assert 'terminate' in result['verifier']['error'] and 'never changes' in result['verifier']['error']


def test_an_unloadable_model_policy_is_a_failure_not_an_unverified_draft(sample):
    result = compile_rule(UNREADABLE, sample, REGION, skip_clarify=True,
                          compiler=compiler_for(FakeModelServer('policies:\n  - name: x\n    resource: aws.nothing\n')))
    assert result['status'] == 'failed'
    assert 'rejects' in result['verifier']['error']


def test_a_model_server_that_is_down_is_a_message_not_a_crash(sample):
    down = FakeModelServer(fail=httpx.ConnectError('connection refused'))
    result = compile_rule(UNREADABLE, sample, REGION, compiler=compiler_for(down), skip_clarify=True)

    assert result['status'] == 'failed'
    assert '07_serve.py' in result['verifier']['error'] and 'WARD_COMPILER=templates' in result['verifier']['error']


# ─── Through the API ──────────────────────────────────────────────────────────

@pytest.fixture
def client(sample):
    server = FakeModelServer(GPU_6H)
    app.dependency_overrides[get_inventory] = lambda: sample
    app.dependency_overrides[get_compiler] = lambda: compiler_for(server)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_compile_endpoint_returns_an_unverified_draft(client):
    body = client.post('/rules/compile', json={'english': UNREADABLE, 'skipClarify': True}).json()
    assert body['status'] == 'unverified' and body['yaml'].startswith('policies:')


def test_an_unverified_draft_cannot_be_activated(client):
    """SRS §4.1: a policy that has not passed the verifier is never stored."""
    res = client.post('/rules', json={'english': UNREADABLE})
    assert res.status_code == 422
    assert 'could not be verified' in res.json()['detail']['message']
