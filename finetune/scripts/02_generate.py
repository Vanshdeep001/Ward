"""A teacher writes a candidate policy for each rule (SRS §9.2).

Nothing here decides whether a candidate is *correct* — 03_verify.py does that, against fixtures
built from the intent. The teacher only has to be right often enough to be worth filtering.

Two teachers:

  --teacher templates   app.compiler.templates.TemplateCompiler, already in the repo. Free, offline,
                        deterministic. Its candidates are as good as the patterns it knows, so the
                        dataset it produces teaches the model to imitate those patterns.
  --teacher api         a frontier model. Costs roughly $15-20 for ~2,000 rules, and buys the thing
                        templates cannot: phrasing the patterns do not cover. This is the arm that
                        supports novelty claim N2.

Keep the two as separate runs (--out differs) so the report can compare them.

    python scripts/02_generate.py --teacher templates
    ANTHROPIC_API_KEY=... python scripts/02_generate.py --teacher api --model claude-sonnet-5
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / 'backend'))

DEFAULT_IN = ROOT / 'data' / 'generated' / 'rules_expanded.jsonl'
DEFAULT_OUT = ROOT / 'data' / 'generated' / 'candidates.jsonl'

SYSTEM = (
    'You write Cloud Custodian policies. Given a rule in English, output only valid YAML for a '
    'single policy. No explanation, no markdown fences.'
)


class TemplateTeacher:
    name = 'templates'

    def __init__(self, **_):
        from app.compiler.templates import TemplateCompiler

        self.compiler = TemplateCompiler()

    def write(self, rule: dict) -> str | None:
        draft = self.compiler.compile(rule['english'])
        return draft.policy_yaml if draft else None


class ApiTeacher:
    """A frontier model. Deliberately given the sentence only — never the intent, and never the
    fixtures it will be graded against."""

    def __init__(self, model: str, **_):
        import anthropic

        self.name = model
        self.model = model
        self.client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

    def write(self, rule: dict) -> str | None:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=700,
            system=SYSTEM,
            messages=[{'role': 'user', 'content': f'RULE: {rule["english"]}'}],
        )
        text = ''.join(block.text for block in message.content if block.type == 'text')
        return _strip_fences(text)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0]
    return text.strip() + '\n'


TEACHERS = {'templates': TemplateTeacher, 'api': ApiTeacher}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--teacher', choices=TEACHERS, default='templates')
    ap.add_argument('--model', default='claude-sonnet-5', help='only used by --teacher api')
    ap.add_argument('--rules', type=Path, default=DEFAULT_IN)
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--limit', type=int, default=0, help='stop after N rules — useful for costing an API run')
    args = ap.parse_args()

    rules = [json.loads(line) for line in args.rules.read_text(encoding='utf-8').splitlines() if line.strip()]
    if args.limit:
        rules = rules[:args.limit]

    teacher = TEACHERS[args.teacher](model=args.model)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    written, refused = 0, 0
    with args.out.open('w', encoding='utf-8') as fh:
        for i, rule in enumerate(rules, 1):
            try:
                policy_yaml = teacher.write(rule)
            except Exception as exc:  # one bad rule must not end the run
                print(f'  ! {rule["id"]}: {type(exc).__name__}: {exc}')
                policy_yaml = None
            if policy_yaml is None:
                refused += 1
                continue
            fh.write(json.dumps({**rule, 'policy_yaml': policy_yaml, 'teacher': teacher.name}, ensure_ascii=False) + '\n')
            written += 1
            if i % 100 == 0:
                print(f'  {i}/{len(rules)}…')

    print(f'{written} candidates written, {refused} rules the teacher would not attempt '
          f'({written / max(len(rules), 1):.0%} attempted)  ({args.out.relative_to(ROOT)})')
    if refused:
        print('  Refusals are a coverage signal, not an error: these are phrasings this teacher '
              'cannot map. The API teacher usually covers them.')


if __name__ == '__main__':
    main()
