"""Answer "why fine-tune?" with numbers: every compiler on the same split, graded by the same verifier.

    python 08_compare.py                                   # val split, templates + zero-shot API model
    python 08_compare.py --preds finetuned=results/preds_v2.jsonl --preds base=results/preds_base_val.jsonl
    python 08_compare.py --split data/splits/test_holdout.jsonl ...   # Phase 9 only — see below

Systems:

  templates   app.compiler.templates — the hand-written rules Ward shipped with. Free, instant, brittle.
  api         a large general model, zero-shot, over any OpenAI-compatible API (Ward's search model:
              WARD_RAG_LLM_* in backend/.env — gpt-oss-120b on Groq). It gets exactly the prompt the
              fine-tuned model gets — the same system message and REFERENCE block — and no training.
  --preds     anything generated elsewhere in 06_evaluate.py's format. From Colab:
                python 06_evaluate.py --mode generate --adapter <v2 adapter> --split val.jsonl --out preds_v2.jsonl
                python 06_evaluate.py --mode generate --no-adapter          --split val.jsonl --out preds_base_val.jsonl

Every prediction is graded by fixtures built from the row's intent, exactly as 06_evaluate.py grades
the fine-tuned model, so the table is like-for-like.

API predictions are cached in results/preds_<split>_api.jsonl and the run resumes where it stopped, so a
free-tier rate limit costs time, not work. --limit takes the first N rows (for a quick, cheap look).

The holdout is locked (data/splits/README.md): run this on val while you are still changing things, and on
test_holdout.jsonl once, at the end, for the number that goes in the report.
"""
import argparse
import importlib.util
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT.parent / 'backend'
sys.path.insert(0, str(BACKEND))

# 06_evaluate.py starts with a digit, so it is loaded by path rather than imported.
_spec = importlib.util.spec_from_file_location('evaluate06', Path(__file__).with_name('06_evaluate.py'))
evaluate06 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evaluate06)


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def row_out(row: dict, prediction: str) -> dict:
    return {'meta': row['meta'], 'prediction': prediction, 'reference': row['messages'][-1]['content']}


# ─── Templates ───────────────────────────────────────────────────────────────

def predict_templates(rows: list[dict]) -> tuple[list[dict], float]:
    from app.compiler.templates import TemplateCompiler

    compiler = TemplateCompiler()
    started = time.perf_counter()
    out = []
    for row in rows:
        draft = compiler.compile(row['meta']['english'])
        out.append(row_out(row, draft.policy_yaml if draft else ''))
    return out, (time.perf_counter() - started) / max(len(rows), 1)


# ─── A general model, zero-shot ──────────────────────────────────────────────

def predict_api(rows: list[dict], cache: Path, pace: float) -> tuple[list[dict], float, str]:
    import httpx

    from app.config import settings

    if not settings.rag_llm_key:
        raise SystemExit('No API model configured: set WARD_RAG_LLM_URL/_KEY/_MODEL in backend/.env, or use --skip-api.')
    url, model = settings.rag_llm_url.rstrip('/'), settings.rag_llm_model
    client = httpx.Client(timeout=120, headers={'Authorization': f'Bearer {settings.rag_llm_key}'})

    done = {r['meta']['id']: r for r in load(cache)} if cache.exists() else {}
    todo = [r for r in rows if r['meta']['id'] not in done]
    if done:
        print(f'  api: {len(done)} cached, {len(todo)} to go')
    latencies = []
    with cache.open('a', encoding='utf-8') as fh:
        for i, row in enumerate(todo, 1):
            body = {'model': model, 'messages': row['messages'][:-1], 'temperature': 0, 'max_tokens': 1500}
            for attempt in range(6):
                started = time.perf_counter()
                response = client.post(f'{url}/chat/completions', json=body)
                if response.status_code != 429:
                    break
                wait = _retry_after(response)
                print(f'    rate-limited; waiting {wait:.0f}s')
                time.sleep(wait)
            if not response.is_success:
                raise SystemExit(f'API answered {response.status_code}: {response.text[:300]}')
            latencies.append(time.perf_counter() - started)
            text = response.json()['choices'][0]['message']['content'] or ''
            record = {**row_out(row, evaluate06._strip_fences(text)), 'latency_s': round(latencies[-1], 2)}
            fh.write(json.dumps(record, ensure_ascii=False) + '\n')
            fh.flush()
            done[row['meta']['id']] = record
            if i % 10 == 0:
                print(f'  api: {i}/{len(todo)}…')
            if pace and i < len(todo):
                time.sleep(pace)
    cached = [done[r['meta']['id']] for r in rows]
    known = [r['latency_s'] for r in cached if 'latency_s' in r]
    return cached, (sum(known) / len(known) if known else 0.0), model


def _retry_after(response) -> float:
    header = response.headers.get('retry-after')
    if header:
        try:
            return float(header) + 1
        except ValueError:
            pass
    found = re.search(r'try again in ([\d.]+)(ms|s)', response.text)
    return (float(found[1]) / (1000 if found[2] == 'ms' else 1) + 1) if found else 20.0


# ─── The table ───────────────────────────────────────────────────────────────

PROFILE = {
    'templates': ('hand-written rules', '—', '₹0', 'yes'),
    'api': ('general model, zero-shot', '120B', 'per call', 'no'),
    'base': ('Qwen2.5-Coder-1.5B, untuned', '1.5B', '₹0', 'yes'),
    'finetuned': ('Qwen2.5-Coder-1.5B + Ward adapter', '1.5B', '₹0', 'yes'),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--split', type=Path, default=ROOT / 'data' / 'splits' / 'val.jsonl')
    ap.add_argument('--preds', action='append', default=[], metavar='NAME=PATH',
                    help='predictions generated elsewhere, e.g. finetuned=results/preds_v2.jsonl (repeatable)')
    ap.add_argument('--skip-api', action='store_true')
    ap.add_argument('--limit', type=int, default=0, help='only the first N rows of the split')
    ap.add_argument('--pace', type=float, default=4.0, help='seconds between API calls (free tiers limit tokens/min)')
    ap.add_argument('--region', default='ap-south-1')
    args = ap.parse_args()

    if 'holdout' in args.split.name:
        print('!! Scoring the LOCKED holdout. Do this once, when nothing will change afterwards.\n')
    rows = load(args.split)
    if args.limit:
        rows = rows[:args.limit]
    ids = {r['meta']['id'] for r in rows}
    split = args.split.stem

    systems: dict[str, tuple[list[dict], float | None, str]] = {}
    print(f'{len(rows)} rows from {args.split.name}')

    preds, per_rule = predict_templates(rows)
    systems['templates'] = (preds, per_rule, 'TemplateCompiler')

    if not args.skip_api:
        cache = ROOT / 'results' / f'preds_{split}_api.jsonl'
        preds, per_rule, model = predict_api(rows, cache, args.pace)
        systems['api'] = (preds, per_rule, model)

    for spec in args.preds:
        name, _, path = spec.partition('=')
        loaded = [r for r in load(Path(path)) if r['meta']['id'] in ids]
        if len(loaded) != len(rows):
            print(f'  ! {name}: {len(loaded)} of {len(rows)} rows found in {path} — scored on those only')
        systems[name] = (loaded, None, path)

    print('\ngrading with the verifier…')
    results = {name: evaluate06.grade(preds, args.region) for name, (preds, _, _) in systems.items()}
    report = table(split, len(rows), systems, results)
    print('\n' + report)

    out = ROOT / 'results' / f'compare_{split}_{datetime.now():%Y%m%d-%H%M}.md'
    out.write_text(report, encoding='utf-8')
    print(f'\nsaved {out.relative_to(ROOT)}')


def table(split: str, n: int, systems: dict, results: dict) -> str:
    lines = [f'# Compiler comparison — {split}, {n} rules', '',
             'Every prediction graded by the same verifier: fixtures built from the rule\'s intent.', '',
             '| System | What it is | Params | Verified correct | Exact match | Per rule | Cost | Offline |',
             '|---|---|---|---|---|---|---|---|']
    for name, (_, per_rule, source) in systems.items():
        g = results[name]
        what, params, cost, offline = PROFILE.get(name, (source, '?', '?', '?'))
        if name == 'api':
            what = f'{source}, zero-shot'
        speed = f'{per_rule:.2f} s' if per_rule is not None else '—'
        lines.append(f'| **{name}** | {what} | {params} | **{g["passed"] / g["n"]:.1%}** ({g["passed"]}/{g["n"]}) | '
                     f'{g["exact"] / g["n"]:.1%} | {speed} | {cost} | {offline} |')

    families = sorted({f for g in results.values() for f in g['stats']})
    lines += ['', '## By rule family (verified correct)', '',
              '| System | ' + ' | '.join(families) + ' |', '|---|' + '---|' * len(families)]
    for name, g in results.items():
        cells = []
        for f in families:
            s = g['stats'].get(f)
            cells.append(f'{s["pass"] / (s["pass"] + s["fail"]):.0%}' if s else '—')
        lines.append(f'| {name} | ' + ' | '.join(cells) + ' |')

    for name, g in results.items():
        if g['failures']:
            lines += ['', f'### {name}: first failures ({len(g["failures"])})', '']
            lines += [f'- {english} — {why}' for english, why in g['failures'][:8]]
    groups = len(next(iter(results.values()))['groups']) if results else 0
    lines += ['', f'{groups} independent rule groups in this split.'
              + (' Too few to separate close systems; treat small gaps as noise.' if groups < 30 else '')]
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    main()
