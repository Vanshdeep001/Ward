"""Search (RAG). Pinecone and the answering model are faked with httpx.MockTransport: these tests are
about Ward's side — what it indexes, what it sends, how it cites, how it falls back — and need neither
a key nor a network."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_inventory, get_search
from app.guardian import findings as finder
from app.main import app
from app.rag.answer import LlmAnswerer, cited, extractive
from app.rag.documents import OVERVIEW_ID, build_documents
from app.rag.service import SearchService
from app.rag.stores import LocalStore, PineconeStore, tokens
from tests.conftest import REGION


@pytest.fixture(scope='module')
def docs(sample):
    snapshot = sample.latest()
    alerts = [{'resourceId': 'i-0a1f2', 'rule': 'No GPU instance runs more than 6 hours', 'level': 'alert', 'status': 'open'}]
    return build_documents(snapshot, alerts, finder.find_all(snapshot), REGION)


def doc(docs, rid):
    return next(d for d in docs if d.id == rid)


# ─── Documents ───────────────────────────────────────────────────────────────

def test_every_resource_becomes_one_document_plus_an_overview(sample, docs):
    total = sum(len(rs) for rs in sample.latest().resources.values())
    assert len(docs) == total + 1
    assert docs[-1].id == OVERVIEW_ID
    assert f'{total} resources in total' in docs[-1].text


def test_documents_say_things_the_way_people_ask_them(docs):
    gpu = doc(docs, 'i-0a1f2').text
    assert 'virtual server' in gpu and 'GPU' in gpu
    assert 'No owner' in gpu
    assert 'Guardrail breaking: "No GPU instance runs more than 6 hours"' in gpu
    assert 'the whole internet' in doc(docs, 'sg-0ssh').text and '(SSH)' in doc(docs, 'sg-0ssh').text
    assert 'unattached' in doc(docs, 'vol-01').text


def test_metadata_never_holds_none_because_pinecone_rejects_it(docs):
    assert all(v is not None for d in docs for v in d.fields.values())


def test_a_fingerprint_changes_only_when_the_text_does(docs):
    d = docs[0]
    assert d.fingerprint == type(d)(d.id, d.text, d.fields).fingerprint
    assert d.fingerprint != type(d)(d.id, d.text + ' changed', d.fields).fingerprint


# ─── Local retrieval ────────────────────────────────────────────────────────

def test_tokens_split_dotted_names_so_instance_families_match():
    assert {'t3.micro', 't3', 'micro'} <= set(tokens('Type t3.micro'))


@pytest.mark.parametrize('question, expected', [
    ('gpu machines', 'i-0a1f2'),
    ('ssh open to the internet', 'sg-0ssh'),
    ('unattached idle disks', 'vol-01'),
    ('postgres database', 'attendance-db'),
])
def test_local_search_finds_the_resource_a_question_is_about(docs, question, expected):
    store = LocalStore()
    store.upsert('t', docs)
    ids = [h.id for h in store.search('t', question, 4)]
    assert expected in ids


# ─── Pinecone, faked ────────────────────────────────────────────────────────

class FakePinecone:
    """Enough of Pinecone's REST API: the index doesn't exist until created, then records are stored per
    namespace and search returns them by a crude word overlap (the real one embeds)."""

    def __init__(self):
        self.created, self.spaces, self.requests = False, {}, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append((request.method, path, request.headers.get('Api-Key')))
        if path == '/indexes/ward-resources':
            if not self.created:
                return httpx.Response(404, json={'error': 'not found'})
            return httpx.Response(200, json={'host': 'ward-resources-x.svc.pinecone.io', 'status': {'ready': True}})
        if path == '/indexes/create-for-model':
            self.created = True
            body = json.loads(request.content)
            assert body['embed'] == {'model': 'llama-text-embed-v2', 'field_map': {'text': 'text'}}
            return httpx.Response(201, json={'name': body['name']})
        if path.endswith('/upsert'):
            ns = path.split('/')[-2]
            assert request.headers['Content-Type'] == 'application/x-ndjson'
            for line in request.content.decode().splitlines():
                record = json.loads(line)
                self.spaces.setdefault(ns, {})[record['_id']] = record
            return httpx.Response(201)
        if path == '/vectors/delete':
            body = json.loads(request.content)
            space = self.spaces.setdefault(body['namespace'], {})
            if body.get('deleteAll'):
                space.clear()
            for i in body.get('ids', []):
                space.pop(i, None)
            return httpx.Response(200, json={})
        if path.endswith('/search'):
            ns = path.split('/')[-2]
            body = json.loads(request.content)
            words = set(tokens(body['query']['inputs']['text']))
            ranked = sorted(self.spaces.get(ns, {}).values(), key=lambda r: -len(words & set(tokens(r['text']))))
            top = ranked[:body['rerank']['top_n'] if 'rerank' in body else body['query']['top_k']]
            hits = [{'_id': r['_id'], '_score': 0.9, 'fields': {k: v for k, v in r.items() if k != '_id'}} for r in top]
            return httpx.Response(200, json={'result': {'hits': hits}})
        return httpx.Response(500, text=f'unexpected {path}')


def pinecone(fake):
    return PineconeStore('pc-key', 'ward-resources', transport=httpx.MockTransport(fake), ready_timeout=0)


def test_pinecone_index_is_created_with_hosted_embeddings_and_records_are_text(docs):
    fake = FakePinecone()
    service = SearchService(pinecone(fake))
    service.sync('acct-1', docs)

    assert fake.created
    assert len(fake.spaces['acct-1']) == len(docs)
    record = fake.spaces['acct-1']['i-0a1f2']
    assert 'virtual server' in record['text'] and record['type'] == 'ec2'
    assert all(key == 'pc-key' for _, _, key in fake.requests), 'every call carries the API key'


def test_only_changed_documents_are_re_sent(docs):
    fake = FakePinecone()
    service = SearchService(pinecone(fake))
    service.sync('acct-1', docs)
    upserts_before = sum(1 for m, p, _ in fake.requests if p.endswith('/upsert'))

    stats = service.sync('acct-1', docs)
    assert stats['upserted'] == 0 and stats['deleted'] == 0
    assert sum(1 for m, p, _ in fake.requests if p.endswith('/upsert')) == upserts_before

    stats = service.sync('acct-1', docs[1:])  # a resource was deleted from the account
    assert stats['deleted'] == 1
    assert docs[0].id not in fake.spaces['acct-1']


def test_search_asks_pinecone_to_rerank_and_returns_sources(docs):
    fake = FakePinecone()
    result = SearchService(pinecone(fake)).ask('ssh open to the internet', 'acct-1', docs)
    assert result['retriever'] == 'pinecone'
    assert 'sg-0ssh' in [s['id'] for s in result['sources']]
    assert all(s['id'] != OVERVIEW_ID for s in result['sources']), 'the overview is context, not a source'


def test_an_unreachable_pinecone_falls_back_to_the_local_index(docs):
    def down(request):
        raise httpx.ConnectError('no route', request=request)

    result = SearchService(PineconeStore('k', 'ward-resources', transport=httpx.MockTransport(down))).ask(
        'postgres database', 'acct-1', docs)
    assert result['retriever'] == 'local'
    assert 'attendance-db' in [s['id'] for s in result['sources']]
    assert 'Pinecone' in result['notice']


def test_a_rejected_pinecone_key_says_where_to_fix_it(docs):
    result = SearchService(PineconeStore('bad', 'ward-resources', transport=httpx.MockTransport(
        lambda r: httpx.Response(401, json={'error': 'unauthorized'})))).ask('gpu', 'acct-1', docs)
    assert 'WARD_PINECONE_API_KEY' in result['notice']


# ─── Answering ──────────────────────────────────────────────────────────────

class FakeModel:
    def __init__(self, answer):
        self.answer, self.requests = answer, []

    def __call__(self, request):
        self.requests.append((request.headers.get('Authorization'), json.loads(request.content)))
        return httpx.Response(200, json={'choices': [{'message': {'role': 'assistant', 'content': self.answer}}]})


def answerer(fake):
    return LlmAnswerer('http://model/v1', 'sk-test', 'gpt-test', transport=httpx.MockTransport(fake))


def test_the_model_answers_from_the_retrieved_documents_and_its_citations_become_sources(docs):
    model = FakeModel('ml-training [i-0a1f2] is a running GPU box with no owner. Also [i-made-up].')
    result = SearchService(answerer=answerer(model)).ask('gpu machines', 'ns', docs)

    auth, body = model.requests[0]
    assert auth == 'Bearer sk-test'
    system = body['messages'][0]['content']
    assert '[i-0a1f2]' in system, 'retrieved documents go in the prompt, headed by their id'
    assert 'Account overview' in system, 'the totals always ride along'
    assert body['messages'][-1] == {'role': 'user', 'content': 'gpu machines'}

    assert result['generator'] == 'gpt-test'
    assert result['sources'][0] == {**result['sources'][0], 'id': 'i-0a1f2', 'cited': True}
    assert 'i-made-up' not in [s['id'] for s in result['sources']], 'an id nobody retrieved is not trusted'


def test_conversation_history_is_passed_so_follow_ups_resolve(docs):
    model = FakeModel('It costs ₹1,585.20 a day [i-0a1f2].')
    history = [{'role': 'user', 'content': 'tell me about ml-training'}, {'role': 'assistant', 'content': 'A GPU box [i-0a1f2].'}]
    SearchService(answerer=answerer(model)).ask('how much does it cost?', 'ns', docs, history)
    assert model.requests[0][1]['messages'][1:3] == history


def test_when_the_model_is_down_the_matches_are_the_answer(docs):
    def down(request):
        raise httpx.ConnectError('refused', request=request)

    result = SearchService(answerer=LlmAnswerer('http://x/v1', 'k', 'm', transport=httpx.MockTransport(down))).ask(
        'postgres database', 'ns', docs)
    assert result['generator'] == 'extractive'
    assert 'attendance-db' in result['answer']
    assert 'answering model' in result['notice']


def test_extractive_and_citation_helpers():
    from app.rag.stores import Hit
    hits = [Hit('a', 1, 'EC2 instance "a" …', {'name': 'a', 'type': 'ec2'})]
    assert '[a]' in extractive('q', hits)
    assert cited('see [a] and [b] and [a]', hits) == ['a']


# ─── Through the API ────────────────────────────────────────────────────────

@pytest.fixture
def client(sample):
    app.dependency_overrides[get_inventory] = lambda: sample
    app.dependency_overrides[get_search] = lambda: SearchService()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_search_endpoint(client):
    body = client.post('/search', json={'query': 'unattached idle disks'}).json()
    assert body['retriever'] == 'local' and body['generator'] == 'extractive'
    assert body['sources'][0]['type'] == 'ebs'
    assert {'id', 'name', 'snippet', 'score', 'cited'} <= set(body['sources'][0])


def test_reindex_and_status(client):
    stats = client.post('/search/reindex').json()
    assert stats['namespace'] == 'sample' and stats['upserted'] == stats['total']
    assert client.get('/search/status').json()['retriever'] == 'local'


def test_chat_sends_questions_about_a_named_resource_to_search(client):
    body = client.post('/chat', json={'message': 'tell me about ml-training', 'state': {}}).json()
    assert body['message']['intent'] == 'SEARCH'
    assert body['message']['sources'][0]['id'] == 'i-0a1f2'
    assert body['state']['history'][-2]['content'] == 'tell me about ml-training'


def test_loose_citations_are_tidied_and_still_count():
    from app.rag.answer import tidy
    from app.rag.stores import Hit
    hits = [Hit('i-0abc', 1, '', {'name': 'algobench'}), Hit(OVERVIEW_ID, 0, '', {})]
    text = tidy('algobench (i‑0abc) 【 i‑0abc 】 costs ₹5 [account-overview].', hits)
    assert text == 'algobench [i-0abc] costs ₹5.'
    assert cited('algobench (i-0abc) is running', hits) == ['i-0abc'], 'a bare id is a citation too'


def test_a_rate_limit_is_waited_out_once(docs):
    calls = []

    def limited(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, text='Rate limit reached ... Please try again in 5ms.')
        return httpx.Response(200, json={'choices': [{'message': {'content': 'ok [vol-01]'}}]})

    result = SearchService(answerer=LlmAnswerer('http://m/v1', 'k', 'm', transport=httpx.MockTransport(limited))).ask(
        'idle disks', 'ns', docs)
    assert len(calls) == 2 and result['generator'] == 'm'


def test_without_a_model_a_totals_question_gets_the_overview_and_others_get_resources(docs):
    service = SearchService()
    assert service.ask('how much do I spend in total', 'ns', docs)['answer'].startswith('Account overview')
    assert service.ask('which volumes are unattached', 'ns', docs)['answer'].startswith('Closest matches')
