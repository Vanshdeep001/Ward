"""Format verified pairs into training examples and split them (SRS §9.4, §9.5).

Two things here decide whether the final number means anything.

**The input shape must match serving.** The model is served with retrieved context, so it trains with
a REFERENCE block. Phase 3's retriever isn't built yet, so the block is filled from a small schema
table — the shape is real even though the retrieval isn't. When the retriever lands, only
`reference_for()` changes.

**The split is by rule family, not by row.** A random split would put "no GPU over 6 hours" in train
and "no GPU over 12 hours" in test, and the test score would measure memorisation. Whole groups —
a seed rule and every paraphrase and parameter variant of it — move together, and families are
stratified so each split sees the same mix.

    python scripts/04_build_dataset.py
"""
import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from prompting import SYSTEM, reference_for  # the one definition of the prompt shape

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / 'data' / 'verified' / 'pairs.jsonl'
DEFAULT_OUT = ROOT / 'data' / 'splits'


def to_example(pair: dict, with_context: bool) -> dict:
    user = f'RULE: {pair["english"]}'
    if with_context:
        user += f'\n\nREFERENCE:\n{reference_for(pair)}'
    return {
        'messages': [
            {'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': user},
            {'role': 'assistant', 'content': pair['policy_yaml'].strip() + '\n'},
        ],
        # The intent rides along so 06_evaluate.py can build fixtures for a prediction and grade it
        # the same way 03_verify.py graded the training pair.
        'meta': {'id': pair['id'], 'group': pair['group'], 'family': pair['family'],
                 'teacher': pair.get('teacher'), 'intent': pair['intent'], 'english': pair['english']},
    }


def split_groups(pairs: list[dict], seed: int = 13) -> dict[str, set[str]]:
    """Assign whole groups to train/val/test, stratified by family so each split sees the same mix.

    Deterministic across runs: families are visited in sorted order and each gets its own generator
    seeded by name. An earlier version iterated a set — whose order Python randomises per process —
    through one shared generator, so every run produced a different split.
    """
    by_family: dict[str, set[str]] = defaultdict(set)
    for p in pairs:
        by_family[p['family']].add(p['group'])

    assignment: dict[str, set[str]] = {'train': set(), 'val': set(), 'test_holdout': set()}
    for family in sorted(by_family):
        groups = sorted(by_family[family])
        random.Random(f'{seed}:{family}').shuffle(groups)  # string seeds are stable across processes
        n = len(groups)
        n_train = max(1, round(n * 0.6))
        n_val = max(1, round(n * 0.1)) if n >= 3 else 0
        assignment['train'].update(groups[:n_train])
        assignment['val'].update(groups[n_train:n_train + n_val])
        assignment['test_holdout'].update(groups[n_train + n_val:])
    return assignment


def pinned_groups(folder: Path, pairs: list[dict]) -> dict[str, set[str]]:
    """Rebuild the split a model was trained on, from the files it was trained on.

    What matters for an honest holdout is not byte-identity but membership: the holdout must hold
    exactly the groups that were in neither train nor val when the model was trained.
    """
    def groups_in(name: str) -> set[str]:
        path = folder / f'{name}.jsonl'
        if not path.exists():
            raise SystemExit(f'--keep-from: {path} not found — copy it back from Colab/Drive first.')
        return {json.loads(line)['meta']['group'] for line in path.read_text(encoding='utf-8').splitlines() if line.strip()}

    train, val = groups_in('train'), groups_in('val')
    if train & val:
        raise SystemExit(f'--keep-from: groups in both train and val: {sorted(train & val)}')
    everything = {p['group'] for p in pairs}
    return {'train': train, 'val': val, 'test_holdout': everything - train - val}


def extended_groups(folder: Path, pairs: list[dict]) -> dict[str, set[str]]:
    """Grow a dataset without disturbing the split an earlier model was trained on.

    Every group the earlier model saw keeps its place — train stays train, val stays val, and its
    holdout groups stay in the holdout, so that holdout is still clean for both models and they can be
    compared on it. Only groups that are new are split, stratified by family as usual.
    """
    def groups_in(name: str) -> set[str]:
        path = folder / f'{name}.jsonl'
        if not path.exists():
            raise SystemExit(f'--extend-from: {path} not found.')
        return {json.loads(line)['meta']['group'] for line in path.read_text(encoding='utf-8').splitlines() if line.strip()}

    old = {name: groups_in(name) for name in ('train', 'val', 'test_holdout')}
    everything_old = set().union(*old.values())
    new_pairs = [p for p in pairs if p['group'] not in everything_old]
    fresh = split_groups(new_pairs) if new_pairs else {'train': set(), 'val': set(), 'test_holdout': set()}
    return {name: old[name] | fresh[name] for name in old}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pairs', type=Path, default=DEFAULT_IN)
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--no-context', action='store_true', help='train without the REFERENCE block')
    ap.add_argument('--keep-from', type=Path, default=None,
                    help='a folder holding the train.jsonl and val.jsonl a model was actually trained on. '
                         'Their groups are kept exactly; every other group becomes the holdout.')
    ap.add_argument('--extend-from', type=Path, default=None,
                    help='a folder holding the train/val/test_holdout.jsonl of an earlier model. Its groups keep '
                         'their split; only groups new since then are split.')
    args = ap.parse_args()
    if args.keep_from and args.extend_from:
        raise SystemExit('use --keep-from or --extend-from, not both')

    pairs = [json.loads(line) for line in args.pairs.read_text(encoding='utf-8').splitlines() if line.strip()]
    if args.keep_from:
        assignment = pinned_groups(args.keep_from, pairs)
    elif args.extend_from:
        assignment = extended_groups(args.extend_from, pairs)
    else:
        assignment = split_groups(pairs)
    args.out.mkdir(parents=True, exist_ok=True)

    buckets: dict[str, list[dict]] = {'train': [], 'val': [], 'test_holdout': []}
    for pair in pairs:
        for name, groups in assignment.items():
            if pair['group'] in groups:
                buckets[name].append(to_example(pair, not args.no_context))
                break

    for name, rows in buckets.items():
        path = args.out / f'{name}.jsonl'
        path.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8')

    # The check that matters: no rule group may appear in more than one split.
    seen: dict[str, str] = {}
    for name, rows in buckets.items():
        for row in rows:
            group = row['meta']['group']
            if group in seen and seen[group] != name:
                raise SystemExit(f'LEAK: group {group} is in both {seen[group]} and {name}')
            seen[group] = name

    total = sum(len(r) for r in buckets.values())
    print(f'{len(pairs)} verified pairs -> {total} examples in {args.out.relative_to(ROOT)}')
    print(f'{"split":14}{"rows":>6}{"groups":>8}{"share":>8}   families')
    for name, rows in buckets.items():
        families = defaultdict(int)
        for row in rows:
            families[row['meta']['family']] += 1
        mix = ' '.join(f'{f}:{c}' for f, c in sorted(families.items(), key=lambda kv: -kv[1]))
        print(f'{name:14}{len(rows):>6}{len(assignment[name]):>8}{len(rows) / total:>8.0%}   {mix}')
    print('\nno group appears in two splits — checked')
    print(f'holdout is locked: see {(args.out / "README.md").relative_to(ROOT)}')


if __name__ == '__main__':
    main()
