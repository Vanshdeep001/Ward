"""Evaluate the RAG pipeline: retrieval quality per search setup, then answer quality end to end.

    python -m app.rag.evaluate                    # retrieval for every available setup + answers
    python -m app.rag.evaluate --retrieval-only   # seconds; no model calls
    python -m app.rag.evaluate --pace 20          # seconds between model calls (Groq free tier: ~20)

Retrieval, per setup (local BM25 · Pinecone · Pinecone + reranker), over the cases that have gold ids:
  context recall      recall@k — share of the right resources in the top k (out of at most k: a question
                      with 11 right answers can only be asked to find 6 of them in 6 slots)
  precision@k         share of what was retrieved that was relevant
  context precision   RAGAS-style: precision@i averaged over the ranks holding a right resource
  hit@1, MRR          is the first result right; 1 / rank of the first right one

Answers, through the full pipeline with the best retrieval setup:
  faithfulness        judge: share of the answer's factual claims the retrieved context supports
  answer relevance    judge: how directly the answer addresses the question, 1-5, reported 0-1
  grounded            deterministic: every ₹ amount and count in the answer is in the documents
  citation P / R      the resources the answer cites against the gold ones
  behaviour           per category: refused when it should be, says "none" when nothing matches,
                      states the right total, does not obey a poisoned tag
  latency             p50 / p95 end to end, and split into retrieval and generation
  tokens, cost        per answer, from the API's usage; cost at --price-in / --price-out ($ per 1M tokens)

The judge is a different model from the answerer (--judge-model, default qwen/qwen3.8-27b), so no model
grades its own answers.

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
from app.rag.judge import Judge
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
    # Context precision, the RAGAS way: precision@i averaged over the ranks i that hold a right resource,
    # so a right answer in first place counts for more than the same answer in sixth.
    hits, precisions = 0, []
    for i, r in enumerate(ranked, 1):
        if r in gold:
            hits += 1
            precisions.append(hits / i)
    return {
        'recall': found / min(len(gold), k),                     # context recall
        'precision': found / len(ranked) if ranked else 0.0,     # precision@k: how much retrieved was relevant
        'ctx_precision': sum(precisions) / len(precisions) if precisions else 0.0,
        'hit1': 1.0 if ranked and ranked[0] in gold else 0.0,
        'mrr': 1 / first if first else 0.0,
    }


def percentile(xs, q: float) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    return round(xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))], 3)


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
    return round(statistics.fmean(xs), 8) if xs else None  # 8 places: a per-answer cost is ~$0.0003


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
        metrics = ('recall', 'precision', 'ctx_precision', 'hit1', 'mrr')
        report[name] = {'overall': _summary(rows, metrics), 'byCategory': _by_category(rows, metrics), 'rows': rows}
        o = report[name]['overall']
        log(f'  {name:<16} recall@{k} {o["recall"]:.2f}   precision@{k} {o["precision"]:.2f}   '
            f'ctx-precision {o["ctx_precision"]:.2f}   hit@1 {o["hit1"]:.2f}   MRR {o["mrr"]:.2f}   ({len(rows)} questions)')
    return report


def run_answers(cases, store, answerer, docs, pace: float, log, judge: Judge | None = None,
                price: tuple[float, float] = (0.0, 0.0)) -> dict:
    service = SearchService(store if store.name != 'local' else None, answerer)
    service.adopt(NAMESPACE, docs)  # already indexed; rewriting it now would leave Pinecone briefly empty
    rows = []
    for i, c in enumerate(cases, 1):
        result, took = _ask(service, c, docs, answerer, log)
        cited = [s['id'] for s in result['sources'] if s['cited']]
        timing, usage = result.get('timing') or {}, result.get('usage') or {}
        row = {
            'case': c.id, 'category': c.category, 'question': c.question, 'gold': c.gold, 'expect': c.expect,
            'answer': result['answer'], 'cited': cited, 'retrieved': result['retrieved'],
            'generator': result['generator'], 'blocked': result['checks']['blocked'],
            'unsupported': result['checks']['unsupported'], 'seconds': took,
            'retrieval_s': timing['retrievalMs'] / 1000 if 'retrievalMs' in timing else None,
            'generation_s': timing['generationMs'] / 1000 if 'generationMs' in timing else None,
            'prompt_tokens': usage.get('prompt'), 'completion_tokens': usage.get('completion'),
            'cost_usd': ((usage.get('prompt') or 0) * price[0] + (usage.get('completion') or 0) * price[1]) / 1e6 if usage else None,
            'grounded': not result['checks']['unsupported'],
            'behaviour': behaviour(c, result),
        }
        if c.gold and c.category in ('lookup', 'filter', 'paraphrase'):
            row.update({f'cite_{k}': v for k, v in citation_scores(cited, c.gold).items()})
        # The judge reads exactly what the answerer was shown. Blocked questions never reached a model.
        judged = None
        if judge and not result['checks']['blocked'] and result['generator'] != 'extractive':
            judged = judge.score(c.question, result.get('context') or [], result['answer'])
            if pace:
                time.sleep(pace / 2)
        if judged:
            row.update(faithfulness=judged['faithfulness'], relevance=judged['relevanceScore'],
                       relevance_1to5=judged['relevance'], claims=len(judged['claims']),
                       unsupported_claims=judged['unsupportedClaims'], judge_reason=judged['reason'])
        rows.append(row)
        mark = '✓' if row['behaviour'] and row['grounded'] and row.get('faithfulness', 1) == 1 else '✗'
        extra = f"  faithful {row['faithfulness']:.2f} · relevant {row['relevance_1to5']}/5" if judged else ''
        log(f'  {mark} [{i:>2}/{len(cases)}] {c.category:<10} {c.question[:55]:55}{extra}')
        if pace and result['checks']['blocked'] not in ('action', 'injection') and i < len(cases):
            time.sleep(pace)  # blocked questions never reach the model, so they cost no quota
    metrics = ('behaviour', 'grounded', 'faithfulness', 'relevance', 'cite_precision', 'cite_recall', 'seconds',
               'retrieval_s', 'generation_s', 'prompt_tokens', 'completion_tokens', 'cost_usd')
    answered = [r for r in rows if not r['blocked']]
    latency = {name: {'p50': percentile([r.get(name) for r in answered], 0.5),
                      'p95': percentile([r.get(name) for r in answered], 0.95)}
               for name in ('seconds', 'retrieval_s', 'generation_s')}
    return {'overall': _summary(rows, metrics), 'byCategory': _by_category(rows, metrics), 'latency': latency,
            'judged': sum('faithfulness' in r for r in rows), 'rows': rows}


def _ask(service, case, docs, answerer, log, retries: int = 2):
    for attempt in range(retries + 1):
        started = time.monotonic()
        result = service.ask(case.question, NAMESPACE, docs, include_context=True)
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
        lines += ['## Retrieval', '',
                  '| Setup | context recall@k | precision@k | context precision | hit@1 | MRR |', '|---|---|---|---|---|---|']
        for name, r in report['retrieval'].items():
            o = r['overall']
            lines.append(f"| {name} | {o['recall']:.2f} | {o['precision']:.2f} | {o['ctx_precision']:.2f} | {o['hit1']:.2f} | {o['mrr']:.2f} |")
        lines += ['', '### By category (recall@k)', '']
        cats = sorted({c for r in report['retrieval'].values() for c in r['byCategory']})
        lines += ['| Setup | ' + ' | '.join(cats) + ' |', '|---|' + '---|' * len(cats)]
        for name, r in report['retrieval'].items():
            lines.append(f'| {name} | ' + ' | '.join(f"{r['byCategory'].get(c, {}).get('recall', 0):.2f}" for c in cats) + ' |')
    if report.get('answers'):
        a = report['answers']
        o = a['overall']
        fmt = lambda v: '—' if v is None else f'{v:.2f}'  # noqa: E731
        pct = lambda v: '—' if v is None else f'{v:.0%}'  # noqa: E731
        lat = a.get('latency', {})
        tokens = (o.get('prompt_tokens') or 0) + (o.get('completion_tokens') or 0)
        lines += ['', f"## Answers (retrieval: {report['answerSetup']}, answers: {report['model']}, judge: {report.get('judge') or '—'})", '',
                  '| Metric | Score | How it is measured |', '|---|---|---|',
                  f"| **Faithfulness** | **{pct(o.get('faithfulness'))}** | judge: share of factual claims the retrieved context supports ({a.get('judged', 0)} answers judged) |",
                  f"| **Answer relevance** | **{pct(o.get('relevance'))}** | judge: 1-5, how directly the answer addresses the question |",
                  f"| Grounded numbers | {pct(o.get('grounded'))} | every ₹ amount and count appears in the documents |",
                  f"| Citation precision / recall | {fmt(o.get('cite_precision'))} / {fmt(o.get('cite_recall'))} | cited resources against the golden ones |",
                  f"| Behaviour | {pct(o.get('behaviour'))} | refusals, 'none' answers, totals, poisoned tags |",
                  f"| Latency p50 / p95 | {fmt(lat.get('seconds', {}).get('p50'))} s / {fmt(lat.get('seconds', {}).get('p95'))} s | end to end |",
                  f"| — retrieval p50 / p95 | {fmt(lat.get('retrieval_s', {}).get('p50'))} s / {fmt(lat.get('retrieval_s', {}).get('p95'))} s | search + rerank |",
                  f"| — generation p50 / p95 | {fmt(lat.get('generation_s', {}).get('p50'))} s / {fmt(lat.get('generation_s', {}).get('p95'))} s | the answer model |",
                  f"| Tokens per answer | {tokens:.0f} ({o.get('prompt_tokens') or 0:.0f} in · {o.get('completion_tokens') or 0:.0f} out) | from the API's usage |",
                  f"| Cost per 1,000 answers | ${(o.get('cost_usd') or 0) * 1000:.2f} | at ${report.get('price', [0, 0])[0]} / ${report.get('price', [0, 0])[1]} per 1M tokens in / out |",
                  '', '| Category | n | faithful | relevant | grounded | behaviour | cite P | cite R |', '|---|---|---|---|---|---|---|---|']
        for c, s in a['byCategory'].items():
            lines.append(f"| {c} | {s['n']} | {fmt(s.get('faithfulness'))} | {fmt(s.get('relevance'))} | {fmt(s['grounded'])} | "
                         f"{fmt(s['behaviour'])} | {fmt(s['cite_precision'])} | {fmt(s['cite_recall'])} |")
        failures = [r for r in a['rows'] if not (r['behaviour'] and r['grounded'] and r.get('faithfulness', 1) == 1)]
        if failures:
            lines += ['', '### Failures', '']
            for r in failures:
                why = [] if r['behaviour'] else ['behaviour']
                why += [f"unsupported {', '.join(r['unsupported'])}"] if r['unsupported'] else []
                why += [f"unsupported claim: {c}" for c in r.get('unsupported_claims', [])[:2]]
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
    p.add_argument('--judge-model', default='qwen/qwen3.8-27b',
                   help='the judging model — keep it different from the answering one; "none" skips judging')
    p.add_argument('--price-in', type=float, default=0.15, help='answer model, $ per 1M input tokens (a list-price assumption)')
    p.add_argument('--price-out', type=float, default=0.60, help='answer model, $ per 1M output tokens')
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
            # Answer with whichever setup retrieved best in this run (MRR), not the one assumed to.
            if report.get('retrieval'):
                best = max(report['retrieval'], key=lambda name: report['retrieval'][name]['overall']['mrr'])
            else:
                best = 'pinecone+rerank' if 'pinecone+rerank' in stores else ('pinecone' if 'pinecone' in stores else 'local')
            answerer = LlmAnswerer(settings.rag_llm_url, settings.rag_llm_key, settings.rag_llm_model)
            judge = None if args.judge_model == 'none' else Judge(settings.rag_llm_url, settings.rag_llm_key, args.judge_model)
            report.update(model=settings.rag_llm_model, answerSetup=best, judge=None if judge is None else args.judge_model,
                          price=[args.price_in, args.price_out])
            est = sum(c.category not in ('action', 'injection') for c in cases) * args.pace / 60
            log(f'\nAnswers with {settings.rag_llm_model}, retrieval {best} (about {est:.0f} min at --pace {args.pace:g})')
            store = stores[best]
            if args.answers_only:
                index(store, docs, log)
            report['answers'] = run_answers(cases, store, answerer, docs, args.pace, log, judge,
                                            (args.price_in, args.price_out))

    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"rag-{datetime.now():%Y%m%d-%H%M}"
    stem.with_suffix('.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    stem.with_suffix('.md').write_text(markdown(report), encoding='utf-8')
    log(f'\nReport: {stem.with_suffix(".md")}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
