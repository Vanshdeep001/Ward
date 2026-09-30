"""The RAG evaluation reports (app/rag/evaluate.py), served to the internal System quality page.

GET /evals/rag   the latest run in full — minus the per-question rows, which are the bulk of the file —
                 with its failures, plus a short history of earlier runs for trends.

Read-only, and only what evaluate.py already wrote to backend/evals/results/. These numbers describe
Ward itself on the sample account, not any user's data, so the page that shows them is kept out of the
app's navigation.
"""
import json
from pathlib import Path

from fastapi import APIRouter

from app.rag.evaluate import RESULTS

router = APIRouter(tags=['evals'])


def _runs() -> list[Path]:
    return sorted(Path(RESULTS).glob('rag-*.json'), reverse=True) if Path(RESULTS).exists() else []


def _headline(report: dict) -> dict:
    retrieval = report.get('retrieval') or {}
    answers = (report.get('answers') or {}).get('overall') or {}
    best = report.get('answerSetup') if report.get('answerSetup') in retrieval else next(iter(retrieval), None)
    r = (retrieval.get(best) or {}).get('overall') or {}
    return {
        'at': report.get('at'), 'cases': report.get('cases'), 'model': report.get('model'), 'judge': report.get('judge'),
        'setup': best, 'recall': r.get('recall'), 'ctxPrecision': r.get('ctx_precision'), 'mrr': r.get('mrr'),
        'faithfulness': answers.get('faithfulness'), 'relevance': answers.get('relevance'),
        'grounded': answers.get('grounded'), 'behaviour': answers.get('behaviour'),
        'latencyP50': ((report.get('answers') or {}).get('latency') or {}).get('seconds', {}).get('p50'),
    }


@router.get('/evals/rag')
def rag_evals():
    runs = _runs()
    if not runs:
        return {'latest': None, 'history': []}
    latest = json.loads(runs[0].read_text(encoding='utf-8'))
    answers = latest.get('answers') or {}
    rows = answers.get('rows') or []
    failures = [
        {'case': r['case'], 'category': r['category'], 'question': r['question'], 'answer': (r.get('answer') or '')[:400],
         'why': ([] if r.get('behaviour') else ['wrong behaviour'])
                + [f'figure not in the documents: {u}' for u in r.get('unsupported') or []]
                + [f'unsupported claim: {c}' for c in (r.get('unsupported_claims') or [])[:2]]}
        for r in rows if not (r.get('behaviour') and r.get('grounded') and r.get('faithfulness', 1) == 1)
    ]
    retrieval = {name: {'overall': v.get('overall'), 'byCategory': v.get('byCategory')}
                 for name, v in (latest.get('retrieval') or {}).items()}
    return {
        'latest': {
            'file': runs[0].name, **_headline(latest), 'documents': latest.get('documents'), 'k': latest.get('k'),
            'price': latest.get('price'), 'retrieval': retrieval,
            'answers': {'overall': answers.get('overall'), 'byCategory': answers.get('byCategory'),
                        'latency': answers.get('latency'), 'judged': answers.get('judged')} if answers else None,
            'failures': failures,
        },
        'history': [{'file': p.name, **_headline(json.loads(p.read_text(encoding='utf-8')))} for p in runs[:10]],
    }
