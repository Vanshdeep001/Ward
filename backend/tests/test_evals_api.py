"""GET /evals/rag serves the latest evaluation report to the internal System quality page."""
import json

from fastapi.testclient import TestClient

from app.api import evals
from app.main import app

REPORT = {
    'at': '2026-09-29 05:38 UTC', 'cases': 58, 'documents': 26, 'k': 6, 'model': 'answer-model', 'judge': 'judge-model',
    'answerSetup': 'pinecone', 'price': [0.15, 0.6],
    'retrieval': {'pinecone': {'overall': {'recall': 0.96, 'ctx_precision': 0.94, 'mrr': 0.96}, 'byCategory': {}, 'rows': [1, 2]}},
    'answers': {
        'overall': {'faithfulness': 1.0, 'relevance': 0.99, 'grounded': 1.0, 'behaviour': 0.98},
        'byCategory': {}, 'latency': {'seconds': {'p50': 3.2, 'p95': 22.6}}, 'judged': 43,
        'rows': [
            {'case': 'lookup-01', 'category': 'lookup', 'question': 'q1', 'answer': 'fine', 'behaviour': True, 'grounded': True, 'faithfulness': 1.0},
            {'case': 'poisoned-02', 'category': 'poisoned', 'question': 'Tell me about sly-box', 'answer': '… PWNED',
             'behaviour': False, 'grounded': True, 'unsupported': []},
        ],
    },
}


def test_no_runs_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(evals, 'RESULTS', tmp_path)
    with TestClient(app) as c:
        assert c.get('/evals/rag').json() == {'latest': None, 'history': []}


def test_the_latest_run_with_its_failures_and_without_the_bulk(tmp_path, monkeypatch):
    (tmp_path / 'rag-20260928-0900.json').write_text(json.dumps({**REPORT, 'at': 'older'}), encoding='utf-8')
    (tmp_path / 'rag-20260929-1143.json').write_text(json.dumps(REPORT), encoding='utf-8')
    monkeypatch.setattr(evals, 'RESULTS', tmp_path)
    with TestClient(app) as c:
        body = c.get('/evals/rag').json()
    latest = body['latest']
    assert latest['file'] == 'rag-20260929-1143.json' and latest['faithfulness'] == 1.0 and latest['recall'] == 0.96
    assert [f['case'] for f in latest['failures']] == ['poisoned-02']
    assert 'rows' not in latest['answers'] and 'rows' not in latest['retrieval']['pinecone'], 'the bulk stays on disk'
    assert [h['at'] for h in body['history']] == ['2026-09-29 05:38 UTC', 'older'], 'newest first'
