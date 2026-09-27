"""The verifier grades every candidate (SRS §9.2). This is the step that makes the dataset trustworthy.

Fixtures are generated from the rule's **intent** — the structured statement of what the rule is
supposed to do — and never from the candidate policy. A candidate therefore cannot grade itself: it
is run against resources it has never seen, labelled by something that does not know how it was
written.

A pass is kept as training data. A failure is kept too, in data/generated/failed.jsonl, because the
pattern of failures is the error analysis Phase 9 asks for.

    python scripts/03_verify.py
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / 'backend'))

DEFAULT_IN = ROOT / 'data' / 'generated' / 'candidates.jsonl'
DEFAULT_PASSED = ROOT / 'data' / 'verified' / 'pairs.jsonl'
DEFAULT_FAILED = ROOT / 'data' / 'generated' / 'failed.jsonl'


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidates', type=Path, default=DEFAULT_IN)
    ap.add_argument('--passed', type=Path, default=DEFAULT_PASSED)
    ap.add_argument('--failed', type=Path, default=DEFAULT_FAILED)
    ap.add_argument('--region', default='ap-south-1')
    args = ap.parse_args()

    from pydantic import TypeAdapter

    from app.engine import custodian
    from app.verifier import fixtures as fixture_gen
    from app.verifier.intents import Intent
    from app.verifier.runner import verify

    custodian.warm_up(args.region)
    intents = TypeAdapter(Intent)

    candidates = [json.loads(line) for line in args.candidates.read_text(encoding='utf-8').splitlines() if line.strip()]
    args.passed.parent.mkdir(parents=True, exist_ok=True)
    args.failed.parent.mkdir(parents=True, exist_ok=True)

    stats = defaultdict(lambda: {'pass': 0, 'fail': 0})
    reasons = defaultdict(int)
    kept = 0

    with args.passed.open('w', encoding='utf-8') as ok, args.failed.open('w', encoding='utf-8') as bad:
        for i, candidate in enumerate(candidates, 1):
            intent = intents.validate_python(candidate['intent'])
            report = verify(candidate['policy_yaml'], fixture_gen.generate(intent), args.region)
            family = candidate['family']

            if report.passed:
                stats[family]['pass'] += 1
                kept += 1
                ok.write(json.dumps({**candidate, 'verified': True,
                                     'fixtures': len(report.fixtures)}, ensure_ascii=False) + '\n')
            else:
                stats[family]['fail'] += 1
                reasons[_reason(report)] += 1
                bad.write(json.dumps({**candidate, 'verified': False,
                                      'error': report.error,
                                      'missed': [f.id for f in report.fixtures if f.expected and f.actual is False],
                                      'false_alarms': [f.id for f in report.fixtures if not f.expected and f.actual is True]},
                                     ensure_ascii=False) + '\n')
            if i % 100 == 0:
                print(f'  {i}/{len(candidates)}…')

    total = len(candidates)
    print(f'\ncompile rate: {kept}/{total} = {kept / max(total, 1):.1%}   '
          f'({args.passed.relative_to(ROOT)})')
    print(f'{"family":18}{"pass":>6}{"fail":>6}{"rate":>8}')
    for family, s in sorted(stats.items(), key=lambda kv: -kv[1]['pass']):
        n = s['pass'] + s['fail']
        print(f'{family:18}{s["pass"]:>6}{s["fail"]:>6}{s["pass"] / n:>8.0%}')
    if reasons:
        print('\nwhy candidates failed:')
        for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f'  {count:>4}  {reason}')


def _reason(report) -> str:
    if report.error:
        return f'invalid policy: {report.error[:60]}'
    if any(f.expected and f.actual is False for f in report.fixtures):
        return 'missed a violation it should have caught'
    if any(not f.expected and f.actual is True for f in report.fixtures):
        return 'flagged a resource it should have left alone'
    return 'unknown'


if __name__ == '__main__':
    main()
