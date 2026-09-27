"""Evaluate the RAG pipeline: retrieval quality per search setup, then answer quality end to end.

    python -m app.rag.evaluate                    # retrieval for every available setup + answers
    python -m app.rag.evaluate --retrieval-only   # seconds; no model calls
    python -m app.rag.evaluate --pace 20          # seconds between model calls (Groq free tier: ~20)

Retrieval, per setup (local BM25 · Pinecone · Pinecone + reranker), over the cases that have gold ids:
  recall@k   share of the right resources in the top k (out of at most k — a question with 11 right
             answers can only be asked to find 6 of them in 6 slots)
  hit@1      the first result is a right one
  MRR        1 / rank of the first right result, averaged

Answers, through the full pipeline with the best available setup:
  citation precision / recall   the resources the answer cites against the gold ones
  grounded                      every ₹ amount and count in the answer is in the retrieved documents
  behaviour                     per category: refused when it should be, says "none" when nothing
                                matches, states the right total, does not obey a poisoned tag

Results go to backend/evals/results/rag-<timestamp>.json and .md, so runs can be compared.
"""
import argparse
import json
import re
import statistics
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.guardian import findings as finder
from app.inventory.sample import SampleInventory
from app.rag import evalset
from app.rag.answer import LlmAnswerer
from app.rag.documents import OVERVIEW_ID, build_documents
from app.rag.service import SearchService
from app.rag.stores import LocalStore, PineconeStore

NAMESPACE = 'eval-sample'
RESULTS = Path(__file__).resolve().parents[2] / 'evals' / 'results'
NONE_WORDS = re.compile(r"\b(no|none|not any|nothing|there are no|there is no|doesn[’']t|does not|don[’']t|do not|isn[’']t|aren[’']t)\b", re.I)


# ─── Metrics ─────────────────────────────────────────────────────────────────

def retrieval_scores(ranked: list[str], gold: list[str], k: int) -> dict:
    ranked = [r for r in ranked if r != OVERVIEW_ID][:k]
    found = len(set(ranked) & set(gold))
    first = next((i for i, r in enumerate(ranked, 1) if r in gold), None)
    return {
        'recall': found / min(len(gold), k),
        'hit1': 1.0 if ranked and ranked[0] in gold else 0.0,
        'mrr': 1 / first if first else 0.0,
    }


def citation_scores(cited: list[str], gold: list[str]) -> dict:
    hit = len(set(cited) & set(gold))
    return {
        'precision': hit / len(cited) if cited else (1.0 if not gold else 0.0),
        'recall': hit / len(gold) if gold else 1.0,
    }


def behaviour(case: evalset.Case, result: dict) -> bool:
    e, answer = case.expect, result['answer']
    blocked = result['checks']['blocked']
    if 'blocked' in e:
        return blocked == e['blocked']
    if blocked:
        return False  # a real question must not be refused
    if e.get('none'):
        return bool(NONE_WORDS.search(answer)) and not any(s['cited'] for s in result['sources'])
    if 'mentions' in e:
        return all(m.replace(',', '') in answer.replace(',', '') for m in e['mentions'])
    if 'not_contains' in e:
        return e['not_contains'] not in answer
    return True


def mean(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 3) if xs else None


# ─── Setups ──────────────────────────────────────────────────────────────────

def setups() -> dict:
    out = {'local': LocalStore()}
    if settings.pinecone_api_key:
        common = dict(api_key=settings.pinecone_api_key, index=settings.pinecone_index, cloud=settings.pinecone_cloud,
                      region=settings.pinecone_region, embed_model=settings.pinecone_embed_model)
        out['pinecone'] = PineconeStore(**common, rerank_model=None)
        if settings.pinecone_rerank_model:
            out['pinecone+rerank'] = PineconeStore(**common, rerank_model=settings.pinecone_rerank_model)
    return out


def index(store, docs, log) -> None:
    """Write the eval namespace and wait until every record is searchable."""
    service = SearchService(store)
    service.sync(NAMESPACE, docs)
    if store.name == 'pinecone':
        deadline = time.monotonic() + 90
        while store.count(NAMESPACE) < len(docs) and time.monotonic() < deadline:
            time.sleep(2)
        time.sleep(3)  # counted is not quite the same as searchable
    log(f'  indexed {len(docs)} documents into {store.name}:{NAMESPACE}')


# ─── Runs ────────────────────────────────────────────────────────────────────

def run_retrieval(cases, stores: dict, docs, k: int, log) -> dict:
    report = {}
    indexed = set()
    for name, store in stores.items():
        if store.name not in indexed or store.name == 'local':
            index(store, docs, log)
            indexed.add(store.name)
        rows = []
        for c in (c for c in cases if c.scores_retrieval):
            ranked = [h.id for h in store.search(NAMESPACE, c.question, k)]
            rows.append({'case': c.id, 'category': c.category, 'question': c.question, 'gold': c.gold,
                         'ranked': ranked, **retrieval_scores(ranked, c.gold, k)})
        report[name] = {'overall': _summary(rows, ('recall', 'hit1', 'mrr')), 'byCategory': _by_category(rows, ('recall', 'hit1', 'mrr')), 'rows': rows}
        o = report[name]['overall']
        log(f'  {name:<16} recall@{k} {o["recall"]:.2f}   hit@1 {o["hit1"]:.2f}   MRR {o["mrr"]:.2f}   ({len(rows)} questions)')
    return report


def run_answers(cases, store, answerer, docs, pace: float, log) -> dict:
    service = SearchService(store if store.name != 'local' else None, answerer)
    service.adopt(NAMESPACE, docs)  # already indexed; rewriting it now would leave Pinecone briefly empty
    rows = []
    for i, c in enumerate(cases, 1):
        result, took = _ask(service, c, docs, answerer, log)
        cited = [s['id'] for s in result['sources'] if s['cited']]
        row = {
            'case': c.id, 'category': c.category, 'question': c.question, 'gold': c.gold, 'expect': c.expect,
            'answer': result['answer'], 'cited': cited, 'retrieved': result['retrieved'],
            'generator': result['generator'], 'blocked': result['checks']['blocked'],
            'unsupported': result['checks']['unsupported'], 'seconds': took,
            'grounded': not result['checks']['unsupported'],
            'behaviour': behaviour(c, result),
        }
        if c.gold and c.category in ('lookup', 'filter', 'paraphrase'):
            row.update({f'cite_{k}': v for k, v in citation_scores(cited, c.gold).items()})
        rows.append(row)
        mark = '✓' if row['behaviour'] and row['grounded'] else '✗'
        log(f'  {mark} [{i:>2}/{len(cases)}] {c.category:<10} {c.question[:60]}')
        if pace and result['checks']['blocked'] not in ('action', 'injection') and i < len(cases):
            time.sleep(pace)  # blocked questions never reach the model, so they cost no quota
    metrics = ('behaviour', 'grounded', 'cite_precision', 'cite_recall', 'seconds')
    return {'overall': _summary(rows, metrics), 'byCategory': _by_category(rows, metrics), 'rows': rows}


def _ask(service, case, docs, answerer, log, retries: int = 2):
    for attempt in range(retries + 1):
        started = time.monotonic()
        result = service.ask(case.question, NAMESPACE, docs)
        took = round(time.monotonic() - started, 2)
        fell_back = answerer is not None and result['generator'] == 'extractive' and not result['checks']['blocked']
        if not fell_back or attempt == retries:
            return result, took
        log(f'    model unavailable ({(result["notice"] or "")[:80]}); waiting 30 s')
        time.sleep(30)


def _summary(rows, metrics) -> dict:
    return {m: mean(float(r[m]) if isinstance(r.get(m), bool) else r.get(m) for r in rows) for m in metrics}


def _by_category(rows, metrics) -> dict:
    cats = sorted({r['category'] for r in rows})
    return {c: {'n': sum(r['category'] == c for r in rows), **_summary([r for r in rows if r['category'] == c], metrics)} for c in cats}


# ─── Report ──────────────────────────────────────────────────────────────────

def markdown(report: dict) -> str:
    lines = [f"# RAG evaluation — {report['at']}", '',
             f"{report['documents']} documents · {report['cases']} questions · k = {report['k']} · "
             f"answer model: {report.get('model') or '—'}", '']
    if report.get('retrieval'):
        lines += ['## Retrieval', '', '| Setup | recall@k | hit@1 | MRR |', '|---|---|---|---|']
        for name, r in report['retrieval'].items():
            o = r['overall']
            lines.append(f"| {name} | {o['recall']:.2f} | {o['hit1']:.2f} | {o['mrr']:.2f} |")
        lines += ['', '### By category (recall@k)', '']
        cats = sorted({c for r in report['retrieval'].values() for c in r['byCategory']})
        lines += ['| Setup | ' + ' | '.join(cats) + ' |', '|---|' + '---|' * len(cats)]
        for name, r in report['retrieval'].items():
            lines.append(f'| {name} | ' + ' | '.join(f"{r['byCategory'].get(c, {}).get('recall', 0):.2f}" for c in cats) + ' |')
    if report.get('answers'):
        a = report['answers']
        o = a['overall']
        lines += ['', f"## Answers (retrieval: {report['answerSetup']})", '',
                  f"- Behaviour correct: **{o['behaviour']:.0%}**",
                  f"- Grounded (every number is in the documents): **{o['grounded']:.0%}**",
                  f"- Citation precision: **{(o['cite_precision'] or 0):.2f}** · recall: **{(o['cite_recall'] or 0):.2f}**",
                  f"- Mean latency: {o['seconds']:.1f} s", '',
                  '| Category | n | behaviour | grounded | cite P | cite R |', '|---|---|---|---|---|---|']
        for c, s in a['byCategory'].items():
            fmt = lambda v: '—' if v is None else f'{v:.2f}'  # noqa: E731
            lines.append(f"| {c} | {s['n']} | {fmt(s['behaviour'])} | {fmt(s['grounded'])} | {fmt(s['cite_precision'])} | {fmt(s['cite_recall'])} |")
        failures = [r for r in a['rows'] if not (r['behaviour'] and r['grounded'])]
        if failures:
            lines += ['', '### Failures', '']
            for r in failures:
                why = [] if r['behaviour'] else ['behaviour']
                why += [f"unsupported {', '.join(r['unsupported'])}"] if r['unsupported'] else []
                lines.append(f"- **{r['case']}** “{r['question']}” — {'; '.join(why)}  \n  > {r['answer'][:300].replace(chr(10), ' ')}")
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--retrieval-only', action='store_true', help='skip the answering model')
    p.add_argument('--answers-only', action='store_true', help='skip the retrieval comparison')
    p.add_argument('--k', type=int, default=6)
    p.add_argument('--pace', type=float, default=20.0, help='seconds between model calls (rate limits)')
    p.add_argument('--categories', help='comma-separated subset, e.g. filter,paraphrase')
    p.add_argument('--out', type=Path, default=RESULTS)
    args = p.parse_args(argv)

    def log(msg):
        print(msg, flush=True)

    snapshot = evalset.poison(SampleInventory().latest())
    docs = build_documents(snapshot, [], finder.find_all(snapshot), settings.region)
    cases = evalset.build(docs, settings.region)
    if args.categories:
        wanted = set(args.categories.split(','))
        cases = [c for c in cases if c.category in wanted]
    stores = setups()
    log(f'{len(docs)} documents, {len(cases)} questions; setups: {", ".join(stores)}')

    report = {'at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'), 'documents': len(docs), 'cases': len(cases),
              'k': args.k, 'model': None, 'caseList': [asdict(c) for c in cases]}
    if not args.answers_only:
        log('\nRetrieval')
        report['retrieval'] = run_retrieval(cases, stores, docs, args.k, log)

    if not args.retrieval_only:
        if not settings.rag_llm_key:
            log('\nAnswers: skipped — WARD_RAG_LLM_KEY is not set.')
        else:
            best = 'pinecone+rerank' if 'pinecone+rerank' in stores else ('pinecone' if 'pinecone' in stores else 'local')
            answerer = LlmAnswerer(settings.rag_llm_url, settings.rag_llm_key, settings.rag_llm_model)
            report.update(model=settings.rag_llm_model, answerSetup=best)
            est = sum(c.category not in ('action', 'injection') for c in cases) * args.pace / 60
            log(f'\nAnswers with {settings.rag_llm_model}, retrieval {best} (about {est:.0f} min at --pace {args.pace:g})')
            store = stores[best]
            if args.answers_only:
                index(store, docs, log)
            report['answers'] = run_answers(cases, store, answerer, docs, args.pace, log)

    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"rag-{datetime.now():%Y%m%d-%H%M}"
    stem.with_suffix('.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    stem.with_suffix('.md').write_text(markdown(report), encoding='utf-8')
    log(f'\nReport: {stem.with_suffix(".md")}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
