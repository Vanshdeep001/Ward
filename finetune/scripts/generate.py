"""Ask the fine-tuned Ward compiler for a policy — interactively, for one rule, or for a file of rules.

    python generate.py                                  # interactive: type rules, get YAML
    python generate.py "Stop GPU instances running over 3 hours"
    python generate.py --file my_rules.txt --save results/tries.jsonl

The model is asked **exactly as it was trained**: the same system prompt, `RULE:` prefix and
REFERENCE block (see prompting.py). Asking with a bare sentence is testing it on an input it never
saw, which makes a good model look bad.

Decoding is greedy. A policy has one right answer; sampling would make the same rule give different
YAML on different runs, and would measure luck rather than the model.

Every answer is checked, cheapest first:
  1. parses as YAML with a `policies:` list
  2. read-only — no `actions:` block, since Custodian executes what it is given
  3. loads as a real Cloud Custodian policy               (needs the Ward backend alongside)
  4. passes fixtures built from the template compiler's reading of your sentence
                                                          (needs the backend; only when the templates
                                                           can read the sentence at all)

Checks 3 and 4 run when ../backend is present — on the laptop. In Colab you see 1 and 2.

Runs on a GPU (Colab/Kaggle) in about a second per rule. On a laptop CPU it works but is slow —
roughly 10-30 seconds per rule, ~6 GB of RAM for the 1.5B model.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import yaml

from prompting import build_messages, retrieve

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT.parent / 'backend'
REGION = 'ap-south-1'

# Keep downloaded models beside the project rather than in the user profile: the base model is ~3 GB
# and C: is often the small drive. Only the *model cache* moves (HF_HUB_CACHE) — not HF_HOME, which
# also holds the login token, so `hf auth login` keeps working. An explicit setting still wins.
os.environ.setdefault('HF_HUB_CACHE', str(ROOT.parent / '.hf-cache' / 'hub'))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')  # Windows consoles default to cp1252 and choke on ✓ and ₹


# ─── The model ───────────────────────────────────────────────────────────────

def load_model(base_model: str, adapter: str, cpu_fp32: bool = False):
    try:
        import torch
    except ImportError:
        raise SystemExit(
            'PyTorch is not installed. In Colab it already is. On the laptop:\n'
            '  pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu\n'
            '  pip install --no-cache-dir transformers peft accelerate'
        ) from None
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    gpu = torch.cuda.is_available()
    # GPU: fp16. CPU: bfloat16 by default — Qwen's native precision, and half the RAM of fp32
    # (~3 GB instead of ~6 GB for the 1.5B), which matters on a 16 GB laptop with a browser open.
    # fp16 is avoided on CPU, where it is slow or unsupported.
    dtype = torch.float16 if gpu else (torch.float32 if cpu_fp32 else torch.bfloat16)
    where = f'GPU ({torch.cuda.get_device_name(0)})' if gpu else f'CPU, {str(dtype).split(".")[-1]} — expect ~10-30 s per rule'
    print(f'Loading {base_model} + {adapter} on {where}…')

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    model = AutoModelForCausalLM.from_pretrained(base_model, dtype=dtype, device_map='auto' if gpu else None)
    try:
        model = PeftModel.from_pretrained(model, adapter)
    except Exception as exc:  # peft wraps the hub's 401 in a ValueError; unwrap it into advice
        chain = f'{exc} {exc.__cause__} {exc.__context__}'
        if '401' in chain or 'Repository Not Found' in chain:
            raise SystemExit(
                f'Could not fetch the adapter "{adapter}" — Hugging Face said 401, which means the repo\n'
                f'is private and this machine is not logged in. Either:\n'
                f'  1. log in once:   hf auth login        (paste a READ token from\n'
                f'                                          https://huggingface.co/settings/tokens)\n'
                f'  2. or use a local copy: download the adapter folder from Colab/Drive and run\n'
                f'       python generate.py --adapter path\\to\\ward-compiler-v1'
            ) from None
        raise
    model.eval()
    return model, tokenizer


def generate(model, tokenizer, rule: str, use_reference: bool = True) -> dict:
    import torch

    family, reference = retrieve(rule) if use_reference else (None, None)
    prompt = tokenizer.apply_chat_template(build_messages(rule, reference), tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors='pt').to(model.device)

    started = time.perf_counter()
    with torch.no_grad():
        output = model.generate(**inputs, max_new_tokens=400, do_sample=False,
                                pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id)
    new_tokens = output[0][inputs['input_ids'].shape[1]:]
    elapsed = time.perf_counter() - started

    return {
        'rule': rule,
        'retrieved_family': family,
        'yaml': _strip_fences(tokenizer.decode(new_tokens, skip_special_tokens=True)),
        'latency_s': round(elapsed, 2),
        'tokens_per_s': round(len(new_tokens) / elapsed, 1) if elapsed else None,
    }


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0]
    return text.strip() + '\n'


# ─── The checks ──────────────────────────────────────────────────────────────

class Verifier:
    """Ward's own checks, when the backend is importable. Absent in Colab, present on the laptop."""

    def __init__(self):
        self.available = False
        if not BACKEND.exists():
            return
        sys.path.insert(0, str(BACKEND))
        try:
            from app.compiler.templates import TemplateCompiler
            from app.engine import custodian
            from app.verifier import fixtures
            from app.verifier.runner import verify
        except ImportError:
            return
        custodian.warm_up(REGION)
        self.custodian, self.fixtures, self.verify = custodian, fixtures, verify
        self.templates = TemplateCompiler()
        self.available = True

    def check(self, rule: str, policy_yaml: str) -> dict:
        result = {'yaml': False, 'read_only': None, 'custodian': None, 'verified': None, 'judged_as': None, 'error': None}

        try:
            doc = yaml.safe_load(policy_yaml)
        except yaml.YAMLError as exc:
            result['error'] = f'not YAML: {exc}'.splitlines()[0]
            return result
        policies = doc.get('policies') if isinstance(doc, dict) else None
        if not isinstance(policies, list) or not policies:
            result['error'] = 'YAML, but no `policies:` list'
            return result
        result['yaml'] = True
        result['read_only'] = not any(isinstance(p, dict) and p.get('actions') for p in policies)

        if not self.available:
            return result

        try:
            self.custodian.load_policies(policy_yaml, REGION)
            result['custodian'] = True
        except self.custodian.PolicyError as exc:
            result['custodian'] = False
            result['error'] = str(exc)[:160]
            return result

        # Grading needs a statement of what the sentence *means*. The template compiler supplies one
        # when it can read the sentence; when it can't, the answer is shown ungraded, not marked wrong.
        reading = self.templates.compile(rule)
        if reading is None:
            return result
        report = self.verify(policy_yaml, self.fixtures.generate(reading.intent), REGION)
        result['verified'] = report.passed
        result['judged_as'] = f'{reading.kind} {reading.params}'
        if not report.passed:
            missed = [f.id for f in report.fixtures if f.expected and f.actual is False]
            wrong = [f.id for f in report.fixtures if not f.expected and f.actual is True]
            result['error'] = '; '.join(filter(None, [
                f'missed {", ".join(missed)}' if missed else '',
                f'wrongly flagged {", ".join(wrong)}' if wrong else '',
            ])) or report.error
        return result


def show(answer: dict, checks: dict) -> None:
    print('\n' + answer['yaml'].rstrip())
    print('─' * 60)
    mark = {True: '✓', False: '✗', None: '·'}
    print(f'  {mark[checks["yaml"]]} parses as a policy file')
    print(f'  {mark[checks["read_only"]]} read-only (no actions block)')
    print(f'  {mark[checks["custodian"]]} valid Cloud Custodian policy' + ('' if checks['custodian'] is not None else '   (needs the backend — run on the laptop)'))
    if checks['verified'] is None and checks['custodian']:
        print('  · not graded — the template compiler cannot read this sentence, so there is nothing to grade against')
    elif checks['verified'] is not None:
        print(f'  {mark[checks["verified"]]} passes the verifier, judged as: {checks["judged_as"]}')
    if checks['error']:
        print(f'    ↳ {checks["error"]}')
    print(f'  retrieved: {answer["retrieved_family"] or "nothing — no REFERENCE block sent"}  ·  '
          f'{answer["latency_s"]} s, {answer["tokens_per_s"]} tok/s')


# ─── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('rule', nargs='?', help='one rule to compile; omit for interactive mode')
    ap.add_argument('--file', type=Path, help='a text file with one rule per line')
    ap.add_argument('--save', type=Path, help='append every answer and its checks to this .jsonl file')
    ap.add_argument('--base-model', default='Qwen/Qwen2.5-Coder-1.5B-Instruct')
    ap.add_argument('--adapter', default='vansh-deep/ward-compiler-1.5b')
    ap.add_argument('--no-reference', action='store_true', help='omit the REFERENCE block (not how it was trained)')
    ap.add_argument('--cpu-fp32', action='store_true', help='on CPU, load in float32 (~6 GB RAM) instead of bfloat16 (~3 GB)')
    args = ap.parse_args()

    verifier = Verifier()
    if not verifier.available:
        print('Ward backend not found alongside — checks 3 and 4 are off. (Expected in Colab.)')
    model, tokenizer = load_model(args.base_model, args.adapter, cpu_fp32=args.cpu_fp32)

    def run(rule: str) -> dict:
        answer = generate(model, tokenizer, rule, use_reference=not args.no_reference)
        checks = verifier.check(rule, answer['yaml'])
        show(answer, checks)
        if args.save:
            args.save.parent.mkdir(parents=True, exist_ok=True)
            with args.save.open('a', encoding='utf-8') as fh:
                fh.write(json.dumps({**answer, 'checks': checks}, ensure_ascii=False) + '\n')
        return checks

    if args.rule:
        run(args.rule)
    elif args.file:
        rules = [line.strip() for line in args.file.read_text(encoding='utf-8').splitlines()
                 if line.strip() and not line.startswith('#')]
        results = [run(rule) for rule in rules]
        _summary(results)
    else:
        print('\nType a rule in English. Empty line or "exit" to quit.')
        while True:
            try:
                rule = input('\nrule> ').strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not rule or rule.lower() in ('exit', 'quit'):
                break
            run(rule)


def _summary(results: list[dict]) -> None:
    n = len(results)
    def share(key):
        vals = [r[key] for r in results if r[key] is not None]
        return f'{sum(vals)}/{len(vals)}' if vals else 'n/a'
    print(f'\n{n} rules  ·  YAML {share("yaml")}  ·  read-only {share("read_only")}  ·  '
          f'Custodian-valid {share("custodian")}  ·  verified {share("verified")}')


if __name__ == '__main__':
    main()
