"""Grow the hand-written seed rules into a training-sized set (SRS §9.3).

Three kinds of variation: **paraphrase** (the same rule said differently), **parameter** (6 hours
becomes 2, 12, 24) and **resource** (the same shape applied to volumes instead of instances).

Every variant's English is generated *from its intent*, never edited as a string. That matters: if a
paraphrase said "6 hours" while its intent said 12, the pair would be silently wrong and the verifier
— which builds fixtures from the intent — would happily certify a policy that answers a different
question than the sentence asks.

Variants of one seed keep that seed's id as their `group`, so 04_build_dataset.py can split whole
groups and never leak a parameter variant from train into test.

    python scripts/01_expand_rules.py [--seeds ...] [--out ...] [--max-per-seed 12]
"""
import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEEDS = ROOT / 'data' / 'seeds' / 'rules_seed.jsonl'
DEFAULT_OUT = ROOT / 'data' / 'generated' / 'rules_expanded.jsonl'

# Parameter grids per family. The seed's own value is always kept; these add neighbours.
HOURS = [1, 1.5, 2, 3, 4, 6, 8, 10, 12, 24, 48, 72]
DAYS = [0, 3, 5, 7, 14, 30, 60, 90]
PORTS = [21, 22, 23, 3306, 3389, 5432, 6379, 8080, 9200, 27017]
TAGS = ['Owner', 'Project', 'Environment', 'Team', 'CostCentre', 'expiry', 'Purpose']
REGIONS = ['ap-south-1', 'ap-southeast-1', 'eu-west-1', 'eu-central-1', 'us-east-1', 'us-west-2']
TYPE_SETS = [
    ['t3.micro', 't2.micro'], ['t3.small'], ['t3.medium', 't3.large'], ['t2.micro'],
    ['m5.large', 'm5.xlarge'], ['g4dn.xlarge'], ['t3.nano', 't3.micro'], ['c5.large'],
    ['t3.micro', 't3.small', 't3.medium'], ['g5.xlarge'],
]


def _a(word: str) -> str:
    """"a Owner tag" is not English, and bad English in the training data is bad data."""
    return f'an {word}' if word[0].lower() in 'aeiou' else f'a {word}'


def _cap(text: str) -> str:
    """Capitalise the first letter only — str.capitalize() would turn GPU into Gpu."""
    return text[:1].upper() + text[1:]


def _hours(n: float) -> str:
    if n == 1:
        return 'an hour'
    if n == 24:
        return 'a day'
    if n == 168:
        return 'a week'
    return f'{n:g} hours'


def phrasings_runtime(intent: dict) -> list[str]:
    what = 'GPU instance' if intent.get('gpu_only') else 'EC2 instance'
    plural = 'GPU instances' if intent.get('gpu_only') else 'instances'
    h = _hours(intent['hours'])
    exempt = ' outside production' if intent.get('exempt_tag') else ''
    return [
        f'No {what}{exempt} may run for more than {h}',
        f'{_cap(plural)}{exempt} must not run longer than {h}',
        f'Flag any {what}{exempt} running more than {h}',
        f'Stop {plural}{exempt} that have been up for over {h}',
        f'Alert me when {"a " + what if not exempt else "an instance" + exempt} runs beyond {h}',
        f'Nothing{exempt} should run for more than {h}' if not intent.get('gpu_only')
        else f'No accelerator{exempt} should run for more than {h}',
    ]


def phrasings_tag(intent: dict) -> list[str]:
    tag = intent['tag']
    noun = 'volume' if intent.get('resource') == 'ebs' else 'instance'
    nouns = f'{noun}s'
    gpu = 'GPU ' if intent.get('gpu_only') else ''
    return [
        f'Every {gpu}{noun} must have {_a(tag)} tag',
        f'Flag {gpu}{nouns} with no {tag} tag',
        f'{_cap(nouns)} without {_a(tag)} tag should be reported',
        f'{_cap(_a(tag))} tag is mandatory on every {gpu}{noun}',
        f'Report any {gpu}{noun} missing {_a(tag)} tag',
        f'No {gpu}{noun} may exist without {_a(tag)} tag',
    ]


def phrasings_ebs(intent: dict) -> list[str]:
    d = intent['min_age_days']
    when = '' if d == 0 else f' for more than {d} days'
    return [
        f'Flag EBS volumes unattached{when}',
        f'Report volumes attached to nothing{when}',
        f'Unattached disks{when} are waste',
        f'Find EBS volumes not attached to any instance{when}',
        f'Clean up storage left unattached{when}',
        f'Alert on detached volumes{when}',
    ]


def phrasings_rds(_: dict) -> list[str]:
    return [
        'No database may be publicly accessible',
        'RDS instances must not accept connections from the internet',
        'Flag any database exposed to the public internet',
        'Databases should never be reachable from outside the VPC',
        'Alert me if a DB instance has a public endpoint',
        'No RDS instance may be publicly reachable',
    ]


def phrasings_port(intent: dict) -> list[str]:
    p = intent['port']
    named = {22: 'SSH', 3389: 'RDP', 3306: 'MySQL', 5432: 'Postgres', 6379: 'Redis',
             27017: 'MongoDB', 9200: 'Elasticsearch', 21: 'FTP', 23: 'Telnet'}.get(p)
    service = f'{named} on port {p}' if named else f'port {p}'
    return [
        f'No security group may allow {service} from the internet',
        f'Flag security groups exposing {service} to 0.0.0.0/0',
        f'{_cap(service)} must not be open to the world',
        f'Alert if {service} is reachable from anywhere on the internet',
        f'Do not allow {service} from the public internet',
        f'Nothing should expose {service} publicly',
    ]


def phrasings_type(intent: dict) -> list[str]:
    allowed = intent['allowed']
    listed = ' and '.join([', '.join(allowed[:-1]), allowed[-1]]) if len(allowed) > 1 else allowed[0]
    return [
        f'Only {listed} instances are allowed',
        f'Instances are restricted to {listed}',
        f'We only permit {listed}',
        f'Compute is limited to {listed}',
        f'Nothing other than {listed} may run',
        f'Only {listed} is allowed in this account',
    ]


def phrasings_region(intent: dict) -> list[str]:
    r = intent['region']
    return [
        f'No resources outside {r}',
        f'Everything must stay in {r}',
        f'Flag instances running outside {r}',
        f'We only operate in {r}',
        f'Nothing should run in a region other than {r}',
        f'Compute outside {r} is a mistake',
    ]


PHRASINGS = {
    'ec2-runtime': phrasings_runtime,
    'require-tag': phrasings_tag,
    'ebs-unattached': phrasings_ebs,
    'rds-public': phrasings_rds,
    'sg-open-port': phrasings_port,
    'instance-type': phrasings_type,
    'region': phrasings_region,
}


def variants(intent: dict, rng: random.Random, n: int = 3) -> list[dict]:
    """Parameter and resource variations of one intent, including the original."""
    kind = intent['kind']
    out = [dict(intent)]

    def add(field: str, pool: list):
        for value in rng.sample([v for v in pool if v != intent.get(field)], k=min(n, len(pool) - 1)):
            out.append({**intent, field: value})

    if kind == 'ec2-runtime':
        add('hours', HOURS)
        out.append({**intent, 'gpu_only': not intent.get('gpu_only', False)})  # resource variation
    elif kind == 'require-tag':
        add('tag', TAGS)
        out.append({**intent, 'resource': 'ebs' if intent.get('resource') == 'ec2' else 'ec2'})
    elif kind == 'ebs-unattached':
        add('min_age_days', DAYS)
    elif kind == 'sg-open-port':
        add('port', PORTS)
    elif kind == 'region':
        add('region', REGIONS)
    elif kind == 'instance-type':
        for allowed in rng.sample([t for t in TYPE_SETS if t != intent['allowed']], k=min(n, len(TYPE_SETS) - 1)):
            out.append({**intent, 'allowed': allowed})
    return out


def expand(seeds: list[dict], max_per_seed: int, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    rules, seen = [], set()
    for s in seeds:
        family = s['family']
        produced = 0
        for intent in variants(s['intent'], rng):
            options = PHRASINGS[family](intent)
            rng.shuffle(options)
            for english in options:
                key = english.lower()
                if key in seen:
                    continue
                seen.add(key)
                rules.append({
                    'id': f'{s["id"]}-{len(rules):05d}',
                    'group': s['id'],  # split by this, so no variant of one seed crosses the split
                    'family': family,
                    'english': english,
                    'intent': intent,
                })
                produced += 1
                if produced >= max_per_seed:
                    break
            if produced >= max_per_seed:
                break
    return rules


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--seeds', type=Path, default=DEFAULT_SEEDS)
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--max-per-seed', type=int, default=12)
    args = ap.parse_args()

    seeds = [json.loads(line) for line in args.seeds.read_text(encoding='utf-8').splitlines() if line.strip()]
    rules = expand(seeds, args.max_per_seed)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rules) + '\n', encoding='utf-8')

    by_family: dict[str, int] = {}
    for r in rules:
        by_family[r['family']] = by_family.get(r['family'], 0) + 1
    print(f'{len(seeds)} seeds -> {len(rules)} rules  ({args.out.relative_to(ROOT)})')
    for family, count in sorted(by_family.items(), key=lambda kv: -kv[1]):
        print(f'  {family:16} {count}')


if __name__ == '__main__':
    main()
