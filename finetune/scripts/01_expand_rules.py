"""Grow the hand-written seed rules into a training-sized set (SRS §9.3).

Every seed contributes, in this order:

1. **its own sentence** — written by a person, the most natural phrasing in the set. v1 dropped these
   and trained only on template sentences, which is why it stumbled on "No accelerator should…";
2. **template paraphrases** of the same intent;
3. **parameter and resource variants** — 6 hours becomes 2 or 24, instances become volumes — each
   with its own paraphrases.

Variants are interleaved round-robin, so a seed's quota is spread across parameters instead of being
spent on eight wordings of one of them.

Every generated sentence is written *from its intent*, never edited as a string. If a paraphrase said
"6 hours" while its intent said 12, the pair would be silently wrong, and the verifier — which builds
fixtures from the intent — would certify a policy that answers a different question.

Variants keep their seed's id as `group`, so 04_build_dataset.py splits whole groups and never leaks
a parameter variant from train into test.

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
HOURS = [1, 1.5, 2, 3, 4, 5, 6, 8, 10, 12, 16, 24, 36, 48, 72, 168]
DAYS = [0, 1, 3, 5, 7, 10, 14, 21, 30, 45, 60, 90, 180]
PORTS = [21, 22, 23, 3306, 3389, 5432, 6379, 8080, 9200, 27017]
TAGS = ['Owner', 'Project', 'Environment', 'Team', 'CostCentre', 'expiry', 'Purpose']
REGIONS = ['ap-south-1', 'ap-south-2', 'ap-southeast-1', 'eu-west-1', 'eu-west-2', 'eu-central-1', 'us-east-1', 'us-west-2']
TYPE_SETS = [
    ['t3.micro', 't2.micro'], ['t3.small'], ['t3.medium', 't3.large'], ['t2.micro'],
    ['m5.large', 'm5.xlarge'], ['g4dn.xlarge'], ['t3.nano', 't3.micro'], ['c5.large'],
    ['t3.micro', 't3.small', 't3.medium'], ['g5.xlarge'], ['t3a.micro'], ['t4g.small'],
    ['m6i.large'], ['g5.xlarge', 'g4dn.xlarge'],
]
REGION_NAMES = {
    'ap-south-1': 'Mumbai', 'ap-south-2': 'Hyderabad', 'ap-southeast-1': 'Singapore', 'eu-west-1': 'Ireland',
    'eu-west-2': 'London', 'eu-central-1': 'Frankfurt', 'us-east-1': 'N. Virginia', 'us-west-2': 'Oregon',
}
SMALL = {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight', 9: 'nine',
         10: 'ten', 12: 'twelve'}


def _a(word: str) -> str:
    """"a Owner tag" is not English, and bad English in the training data is bad data."""
    return f'an {word}' if word[0].lower() in 'aeiou' else f'a {word}'


def _cap(text: str) -> str:
    """Capitalise the first letter only — str.capitalize() would turn GPU into Gpu."""
    return text[:1].upper() + text[1:]


def _hours(n: float, rng: random.Random) -> str:
    """The same duration, said one of the ways people say it. Every form means exactly n hours."""
    forms = {1: ['an hour', '1 hour', 'one hour', '60 minutes'], 1.5: ['90 minutes', '1.5 hours', 'an hour and a half'],
             12: ['12 hours', 'twelve hours', 'half a day'], 24: ['a day', '24 hours', 'one day'],
             36: ['36 hours', 'a day and a half'], 48: ['48 hours', 'two days', '2 days'],
             72: ['72 hours', 'three days', '3 days'], 168: ['a week', '168 hours', 'seven days']}
    if n in forms:
        return rng.choice(forms[n])
    options = [f'{n:g} hours', f'{n:g}h' if n >= 2 else f'{n:g} hours']
    if n in SMALL:
        options.append(f'{SMALL[n]} hours')
    return rng.choice(options)


def _days(d: int, rng: random.Random) -> str:
    forms = {1: ['a day', '1 day', 'one day'], 7: ['7 days', 'a week', 'seven days'], 14: ['14 days', 'two weeks', 'a fortnight'],
             21: ['21 days', 'three weeks'], 30: ['30 days', 'a month'], 60: ['60 days', 'two months'],
             90: ['90 days', 'three months'], 180: ['180 days', 'six months']}
    if d in forms:
        return rng.choice(forms[d])
    return rng.choice([f'{d} days'] + ([f'{SMALL[d]} days'] if d in SMALL else []))


# ─── Phrasing banks: every sentence is built from the intent ─────────────────

def phrasings_runtime(intent: dict, rng: random.Random) -> list[str]:
    gpu = intent.get('gpu_only')
    what = rng.choice(['GPU instance', 'GPU box', 'GPU machine', 'accelerator instance']) if gpu else rng.choice(['EC2 instance', 'instance', 'server', 'VM'])
    plural = rng.choice(['GPU instances', 'GPU boxes', 'GPU machines', 'accelerators']) if gpu else rng.choice(['instances', 'EC2 instances', 'servers', 'machines'])
    h = lambda: _hours(intent['hours'], rng)  # noqa: E731 — a fresh wording per sentence
    ex = ' outside production' if intent.get('exempt_tag') else ''
    out = [
        f'No {what}{ex} may run for more than {h()}',
        f'{_cap(plural)}{ex} must not run longer than {h()}',
        f'Flag any {what}{ex} running more than {h()}',
        f'Stop {plural}{ex} that have been up for over {h()}',
        f'Alert me when {_a(what)}{ex} runs beyond {h()}',
        f"Don't let {_a(what)}{ex} run past {h()}",
        f'Make sure no {what}{ex} stays on longer than {h()}',
        f'{_cap(plural)}{ex} left running over {h()} should be flagged',
        f'Warn me about any {what}{ex} still up after {h()}',
        f'Keep {plural}{ex} under {h()} of runtime',
        f'Shut down {plural}{ex} after {h()}',
        f'Report {plural}{ex} with an uptime above {h()}',
    ]
    if gpu:
        out.append(f'No accelerator{ex} should run for more than {h()}')
    else:
        out.append(f'Nothing{ex} should run for more than {h()}')
    if ex:
        out.append(f'Except for production, no {what} should run over {h()}')
    return out


def phrasings_tag(intent: dict, rng: random.Random) -> list[str]:
    tag = intent['tag']
    ebs = intent.get('resource') == 'ebs'
    noun = rng.choice(['volume', 'EBS volume', 'disk']) if ebs else rng.choice(['instance', 'EC2 instance', 'server'])
    nouns = f'{noun}s'
    gpu = 'GPU ' if intent.get('gpu_only') else ''
    return [
        f'Every {gpu}{noun} must have {_a(tag)} tag',
        f'Flag {gpu}{nouns} with no {tag} tag',
        f'{_cap(gpu + nouns)} without {_a(tag)} tag should be reported',
        f'{_cap(_a(tag))} tag is mandatory on every {gpu}{noun}',
        f'Report any {gpu}{noun} missing {_a(tag)} tag',
        f'No {gpu}{noun} may exist without {_a(tag)} tag',
        f'Make sure every {gpu}{noun} has {_a(tag)} tag',
        f"Don't allow {gpu}{nouns} without {_a(tag)} tag",
        f'Any {gpu}{noun} missing the {tag} tag should be flagged',
        f'{_cap(gpu + nouns)} need {_a(tag)} tag',
        f'Warn me about {gpu}{nouns} that have no {tag} tag',
        f'Every {gpu}{noun} should carry {_a(tag)} tag',
    ]


def phrasings_ebs(intent: dict, rng: random.Random) -> list[str]:
    d = intent['min_age_days']
    when = (lambda: '') if d == 0 else (lambda: f' for more than {_days(d, rng)}')  # noqa: E731
    return [
        f'Flag EBS volumes unattached{when()}',
        f'Report volumes attached to nothing{when()}',
        f'Unattached disks{when()} are waste',
        f'Find EBS volumes not attached to any instance{when()}',
        f'Clean up storage left unattached{when()}',
        f'Alert on detached volumes{when()}',
        f'Warn me about orphaned EBS volumes{when()}',
        f'Disks sitting unattached{when()} need attention',
        f'Any EBS volume left detached{when()} is waste',
        f'Make sure no volume stays unattached{when()}',
        f'Report orphaned disks{when()}',
        f'Volumes nobody has attached{when()} should be flagged',
    ]


def phrasings_rds(_: dict, rng: random.Random) -> list[str]:
    return [
        'No database may be publicly accessible',
        'RDS instances must not accept connections from the internet',
        'Flag any database exposed to the public internet',
        'Databases should never be reachable from outside the VPC',
        'Alert me if a DB instance has a public endpoint',
        'No RDS instance may be publicly reachable',
        'Make sure no RDS database is publicly accessible',
        "Don't let databases have a public endpoint",
        'Every RDS instance must be private',
        'Warn me about public databases',
        'Keep all RDS instances off the public internet',
        'Report RDS instances with public access turned on',
    ]


def phrasings_port(intent: dict, rng: random.Random) -> list[str]:
    p = intent['port']
    named = {22: 'SSH', 3389: 'RDP', 3306: 'MySQL', 5432: 'Postgres', 6379: 'Redis',
             27017: 'MongoDB', 9200: 'Elasticsearch', 21: 'FTP', 23: 'Telnet'}.get(p)
    forms = [f'port {p}'] + ([f'{named} on port {p}', f'{named} ({p})', f'{named} port {p}'] if named else [])
    s = lambda: rng.choice(forms)  # noqa: E731
    return [
        f'No security group may allow {s()} from the internet',
        f'Flag security groups exposing {s()} to 0.0.0.0/0',
        f'{_cap(s())} must not be open to the world',
        f'Alert if {s()} is reachable from anywhere on the internet',
        f'Do not allow {s()} from the public internet',
        f'Nothing should expose {s()} publicly',
        f'Make sure {s()} is never open to 0.0.0.0/0',
        f"Don't expose {s()} to the internet",
        f'Security groups must not open {s()} to everyone',
        f'Warn me if anyone opens {s()} to the world',
        f'Block public access to {s()}',
        f'Report security groups with {s()} open to all IPs',
    ]


def phrasings_type(intent: dict, rng: random.Random) -> list[str]:
    allowed = intent['allowed']
    joined = lambda word: ' {} '.format(word).join([', '.join(allowed[:-1]), allowed[-1]]) if len(allowed) > 1 else allowed[0]  # noqa: E731
    listed, either = joined('and'), joined('or')
    return [
        f'Only {listed} instances are allowed',
        f'Instances are restricted to {listed}',
        f'We only permit {listed}',
        f'Compute is limited to {listed}',
        f'Nothing other than {listed} may run',
        f'Only {listed} is allowed in this account',
        f'Only allow {listed}',
        f'Anything other than {listed} should be flagged',
        f'Allowed instance types: {listed}',
        f'Stick to {listed} instances',
        f'Flag instances that are not {either}',
        f"Don't run anything except {listed}",
    ]


def phrasings_region(intent: dict, rng: random.Random) -> list[str]:
    r = intent['region']
    name = REGION_NAMES.get(r)
    where = lambda: rng.choice([r, f'{r} ({name})'] if name else [r])  # noqa: E731
    return [
        f'No resources outside {where()}',
        f'Everything must stay in {where()}',
        f'Flag instances running outside {where()}',
        f'We only operate in {where()}',
        f'Nothing should run in a region other than {where()}',
        f'Compute outside {where()} is a mistake',
        f'Only {where()} is allowed',
        f'Flag anything launched outside {where()}',
        f"Don't run instances anywhere but {where()}",
        f'All compute must live in {where()}',
        f'Keep everything in {where()}',
        f'Warn me about instances outside {where()}',
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
    """Parameter and resource variations of one intent, the original first."""
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
    # A resource variation of a GPU-only tag rule would ask for GPU volumes, which don't exist.
    return [v for v in out if not (v.get('resource') == 'ebs' and v.get('gpu_only'))]


def expand(seeds: list[dict], max_per_seed: int, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    rules, seen = [], set()

    def keep(s, english, intent, source) -> bool:
        key = english.lower().strip()
        if key in seen:
            return False
        seen.add(key)
        rules.append({
            'id': f'{s["id"]}-{len(rules):05d}',
            'group': s['id'],  # split by this, so no variant of one seed crosses the split
            'family': s['family'],
            'english': english,
            'intent': intent,
            'source': source,
        })
        return True

    for s in seeds:
        produced = int(keep(s, s['english'], s['intent'], 'seed'))
        # One shuffled queue of paraphrases per variant, then take from them in turn.
        queues = []
        for intent in variants(s['intent'], rng):
            options = PHRASINGS[s['family']](intent, rng)
            rng.shuffle(options)
            queues.append((intent, options))
        while produced < max_per_seed and any(q for _, q in queues):
            for intent, options in queues:
                while options and produced < max_per_seed:
                    if keep(s, options.pop(), intent, 'template'):
                        produced += 1
                        break
    return rules


def _shown(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--seeds', type=Path, default=DEFAULT_SEEDS)
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--max-per-seed', type=int, default=12)
    args = ap.parse_args()

    seeds = [json.loads(line) for line in args.seeds.read_text(encoding='utf-8').splitlines() if line.strip()]
    ids = [s['id'] for s in seeds]
    if len(ids) != len(set(ids)):
        raise SystemExit(f'duplicate seed ids: {sorted({i for i in ids if ids.count(i) > 1})}')
    rules = expand(seeds, args.max_per_seed)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rules) + '\n', encoding='utf-8')

    by_family: dict[str, int] = {}
    for r in rules:
        by_family[r['family']] = by_family.get(r['family'], 0) + 1
    from_seeds = sum(r['source'] == 'seed' for r in rules)
    print(f'{len(seeds)} seeds -> {len(rules)} rules ({from_seeds} hand-written)  ({_shown(args.out)})')
    for family, count in sorted(by_family.items(), key=lambda kv: -kv[1]):
        print(f'  {family:16} {count}')


if __name__ == '__main__':
    main()
