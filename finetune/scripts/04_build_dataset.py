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

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IN = ROOT / 'data' / 'verified' / 'pairs.jsonl'
DEFAULT_OUT = ROOT / 'data' / 'splits'

SYSTEM = (
    'You write Cloud Custodian policies. Given a rule in English and reference documentation, '
    'output only valid YAML. No explanation, no markdown fences.'
)

# Stand-in for Phase 3 retrieval: one chunk per resource type, one per filter type. Same shape the
# retriever will produce, so the model never sees an input format it wasn't trained on.
SCHEMA = {
    'aws.ec2': 'resource: aws.ec2 — EC2 instances. Fields: InstanceId, InstanceType, State.Name '
               '(running|stopped), LaunchTime, Placement.AvailabilityZone, Tags. Instance age is read '
               'from the root volume attach time, not LaunchTime.',
    'aws.ebs': 'resource: aws.ebs — EBS volumes. Fields: VolumeId, Size, State (in-use|available), '
               'CreateTime, Attachments (empty list means attached to nothing), Tags.',
    'aws.rds': 'resource: aws.rds — RDS instances. Fields: DBInstanceIdentifier, DBInstanceClass, '
               'PubliclyAccessible (bool), Engine, Tags.',
    'aws.security-group': 'resource: aws.security-group — security groups. Fields: GroupId, GroupName, '
                          'IpPermissions[].FromPort/ToPort, IpRanges[].CidrIp, Ipv6Ranges[].CidrIpv6.',
}
FILTERS = {
    'ec2-runtime': 'filter instance-age — matches on how long an instance has been running. Takes op '
                   '(greater-than|less-than) and hours or days. Pair it with State.Name: running.',
    'require-tag': 'filter "tag:<Key>": absent — matches resources missing that tag key. Tag keys are '
                   'case-sensitive.',
    'ebs-unattached': 'filter Attachments: [] — matches volumes attached to nothing. Combine with a '
                      'value filter on CreateTime with value_type: age for a minimum age.',
    'rds-public': 'filter PubliclyAccessible: true — matches databases reachable from the internet.',
    'sg-open-port': 'filter type: ingress — takes Ports, Cidr (IPv4) and CidrV6. 0.0.0.0/0 is the whole '
                    'internet over IPv4; ::/0 is the whole internet over IPv6.',
    'instance-type': 'filter type: value with key InstanceType and op in/not-in — matches an allowlist '
                     'of instance types. The match is exact.',
    'region': 'filter type: value with key Placement.AvailabilityZone and op not-in — availability zones '
              'are the region plus a letter suffix.',
}


def reference_for(pair: dict) -> str:
    resource = _resource_of(pair['policy_yaml'])
    chunks = [SCHEMA.get(resource, ''), FILTERS.get(pair['family'], '')]
    return '\n\n'.join(c for c in chunks if c)


def _resource_of(policy_yaml: str) -> str:
    for line in policy_yaml.splitlines():
        if 'resource:' in line:
            return line.split('resource:', 1)[1].strip()
    return ''


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
    """Assign whole groups to train/val/test, stratified by family so each split sees the same mix."""
    rng = random.Random(seed)
    by_family: dict[str, list[str]] = defaultdict(list)
    for group, family in {(p['group'], p['family']) for p in pairs}:
        by_family[family].append(group)

    assignment: dict[str, set[str]] = {'train': set(), 'val': set(), 'test_holdout': set()}
    for family, groups in by_family.items():
        groups = sorted(groups)
        rng.shuffle(groups)
        n = len(groups)
        n_train = max(1, round(n * 0.6))
        n_val = max(1, round(n * 0.1)) if n >= 3 else 0
        assignment['train'].update(groups[:n_train])
        assignment['val'].update(groups[n_train:n_train + n_val])
        assignment['test_holdout'].update(groups[n_train + n_val:])
    return assignment


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pairs', type=Path, default=DEFAULT_IN)
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--no-context', action='store_true', help='train without the REFERENCE block')
    args = ap.parse_args()

    pairs = [json.loads(line) for line in args.pairs.read_text(encoding='utf-8').splitlines() if line.strip()]
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
