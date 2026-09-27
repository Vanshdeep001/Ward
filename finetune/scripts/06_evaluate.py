"""Score a checkpoint (SRS §9.9). Two modes, because the two halves run in different places.

    # on the GPU box, after training
    python 06_evaluate.py --mode generate --adapter ward-compiler-v1 --split data/splits/val.jsonl \
        --out results/preds_val.jsonl

    # on the laptop, where the verifier lives
    python 06_evaluate.py --mode score --preds results/preds_val.jsonl

The metric is **compile rate**: the share of predictions that pass the same fixtures the training
pairs passed. Not BLEU, not exact match — a policy can be written three ways and still be right, and
a policy one character off is still wrong. The verifier is the only judge that knows the difference.

Default split is val.jsonl. Pointing this at test_holdout.jsonl is a Phase 9 decision, not a
convenience — see data/splits/README.md.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def generate(args) -> None:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not torch.cuda.is_available():
        raise SystemExit('Generation needs a GPU. Run --mode score on the laptop instead.')

    tokenizer = AutoTokenizer.from_pretrained(args.adapter)
    model = AutoModelForCausalLM.from_pretrained(args.base_model, device_map='auto', dtype='auto')
    model = PeftModel.from_pretrained(model, str(args.adapter))
    model.eval()

    rows = [json.loads(line) for line in args.split.read_text(encoding='utf-8').splitlines() if line.strip()]
    args.out.parent.mkdir(parents=True, exist_ok=True)

    with args.out.open('w', encoding='utf-8') as fh:
        for i, row in enumerate(rows, 1):
            prompt = tokenizer.apply_chat_template(row['messages'][:-1], tokenize=False, add_generation_prompt=True)
            inputs = tokenizer(prompt, return_tensors='pt').to(model.device)
            with torch.no_grad():
                # Greedy: the task has one right answer, and sampling would measure luck.
                out = model.generate(**inputs, max_new_tokens=400, do_sample=False,
                                     pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id)
            text = tokenizer.decode(out[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)
            fh.write(json.dumps({'meta': row['meta'], 'prediction': _strip_fences(text),
                                 'reference': row['messages'][-1]['content']}, ensure_ascii=False) + '\n')
            if i % 20 == 0:
                print(f'  {i}/{len(rows)}…')
    print(f'{len(rows)} predictions -> {args.out}')


def score(args) -> None:
    import sys

    sys.path.insert(0, str(ROOT.parent / 'backend'))
    from pydantic import TypeAdapter

    from app.engine import custodian
    from app.verifier import fixtures as fixture_gen
    from app.verifier.intents import Intent
    from app.verifier.runner import verify

    custodian.warm_up(args.region)
    intents = TypeAdapter(Intent)

    rows = [json.loads(line) for line in args.preds.read_text(encoding='utf-8').splitlines() if line.strip()]
    stats = defaultdict(lambda: {'pass': 0, 'fail': 0})
    exact, passed, failures = 0, 0, []

    for row in rows:
        meta = row['meta']
        report = verify(row['prediction'], fixture_gen.generate(intents.validate_python(meta['intent'])), args.region)
        stats[meta['family']]['pass' if report.passed else 'fail'] += 1
        if report.passed:
            passed += 1
        else:
            failures.append((meta['english'], report.error or 'wrong resources matched'))
        if row['prediction'].strip() == row['reference'].strip():
            exact += 1

    n = len(rows)
    groups = {r['meta']['group'] for r in rows}
    print(f'\ncompile rate : {passed}/{n} = {passed / n:.1%}   <- the number that matters')
    print(f'exact match  : {exact}/{n} = {exact / n:.1%}   (lower is fine: valid policies differ in wording)')
    print(f'independent groups in this split: {len(groups)}')
    if len(groups) < 30:
        print(f'  ! {len(groups)} groups is too few to separate two systems — see finetune/README.md')

    print(f'\n{"family":18}{"pass":>6}{"fail":>6}{"rate":>8}')
    for family, s in sorted(stats.items(), key=lambda kv: -kv[1]['pass']):
        total = s['pass'] + s['fail']
        print(f'{family:18}{s["pass"]:>6}{s["fail"]:>6}{s["pass"] / total:>8.0%}')

    if failures:
        print(f'\nfirst failures ({len(failures)} total):')
        for english, why in failures[:8]:
            print(f'  {english[:58]:60} {why[:50]}')

    if args.record:
        _record(args, passed / n, exact / n, n, len(groups))


def _record(args, compile_rate: float, exact: float, n: int, groups: int) -> None:
    """Append to results/eval_runs.csv — reconstructing this later from memory is not possible."""
    import csv
    from datetime import datetime, timezone

    path = ROOT / 'results' / 'eval_runs.csv'
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open('a', newline='', encoding='utf-8') as fh:
        writer = csv.writer(fh)
        if new:
            writer.writerow(['date', 'run', 'preds', 'examples', 'groups', 'compile_rate', 'exact_match'])
        writer.writerow([datetime.now(timezone.utc).date().isoformat(), args.record, args.preds.name,
                         n, groups, f'{compile_rate:.4f}', f'{exact:.4f}'])
    print(f'\nrecorded in {path.relative_to(ROOT)}')


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0]
    return text.strip() + '\n'


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode', choices=['generate', 'score'], required=True)
    ap.add_argument('--adapter', type=Path, help='generate: the trained adapter directory')
    ap.add_argument('--base-model', default='Qwen/Qwen2.5-Coder-1.5B-Instruct')
    ap.add_argument('--split', type=Path, default=ROOT / 'data' / 'splits' / 'val.jsonl')
    ap.add_argument('--out', type=Path, default=ROOT / 'results' / 'preds_val.jsonl')
    ap.add_argument('--preds', type=Path, default=ROOT / 'results' / 'preds_val.jsonl')
    ap.add_argument('--region', default='ap-south-1')
    ap.add_argument('--record', default=None, help='score: a run name to append to results/eval_runs.csv')
    args = ap.parse_args()

    generate(args) if args.mode == 'generate' else score(args)


if __name__ == '__main__':
    main()
