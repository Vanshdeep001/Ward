"""Rules about one named resource: "stop my algobench server when its cost reaches ₹500".

The model is good at the *shape* of a rule and has never seen your inventory, so the two halves are kept
apart:

1. Resolve — deterministic. The name (or an ID) is looked up in the latest inventory. Not there → say so;
   more than one match → ask which; never a guess.
2. De-name — the sentence goes to the compiler with the name replaced by a generic subject, so the compiler
   writes a rule about "an instance". A cost threshold becomes a runtime limit using Ward's own prices.
3. Scope — Ward adds the ID filter to the compiled policy itself. The verifier then proves the rule still
   has the right shape on that resource *and* ignores its twin (see verifier/fixtures.py).

Ward is read-only: "stop", "terminate", "shut down" become an alert that carries the command to run.
"""
import re
from dataclasses import dataclass, field

import yaml

from app.engine.custodian import ID_KEYS
from app.inventory.pricing import HOURLY_INR
from app.inventory.store import Snapshot
from app.verifier.intents import Target

SUBJECT = {'aws.ec2': 'instance', 'aws.ebs': 'volume', 'aws.rds': 'RDS database', 'aws.security-group': 'security group',
           'aws.nat-gateway': 'NAT gateway'}
TYPE_WORDS = {
    'aws.ec2': r'server|servers|instance|instances|box|machine|vm|ec2|host',
    'aws.ebs': r'volume|volumes|disk|disks|ebs',
    'aws.rds': r'database|databases|db|rds',
    'aws.security-group': r'security group|security groups|sg|firewall',
    'aws.nat-gateway': r'nat gateway|nat',
}
_ANY_TYPE = '|'.join(TYPE_WORDS.values())
# Names that are also ordinary words: only a resource when the sentence points at one ("my worker server").
GENERIC = {'worker', 'scratch', 'test', 'demo', 'server', 'web', 'api', 'app', 'db', 'database', 'prod', 'production',
           'dev', 'staging', 'bastion', 'main', 'default', 'backend', 'frontend', 'gpu', 'jenkins', 'build'}
_ID = re.compile(r'\b(?:i|vol|sg|nat)-[0-9a-z]{4,}\b', re.IGNORECASE)
_STOP = re.compile(r'^\s*(?:please\s+)?(?:stop|shut\s*down|shutdown|terminate|kill|turn\s+off|power\s+off|halt)\b\s*',
                   re.IGNORECASE)
_MONEY = (r'(?:₹|rs\.?\s*|inr\s*)\s*(?P<a>\d[\d,]*(?:\.\d+)?)(?!\s*(?:/|per\s+)\s*(?:h|hr|hour|day|d|month|mo)\b)'
          r'|(?P<b>\d[\d,]*(?:\.\d+)?)\s*(?:rupees|rs\b|inr\b)(?!\s*(?:/|per\s+)\s*(?:h|hr|hour|day|d|month|mo)\b)')
_COST_VERB = r'\b(?:cost|costs|bill|spend|spends|spent|spending|charges?)\b'


@dataclass
class Resolution:
    status: str  # 'none' (not about a particular resource) | 'resolved' | 'ambiguous' | 'not-found' | 'unsupported'
    english: str  # what the compiler sees: the name replaced by a generic subject
    targets: list[Target] = field(default_factory=list)
    stop_requested: bool = False
    assumptions: list[str] = field(default_factory=list)
    message: str | None = None
    questions: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class _Entry:
    id: str
    name: str | None
    resource_type: str
    resource: dict


def _name_of(rtype: str, r: dict) -> str | None:
    tags = r.get('Tags') or []
    tag = next((t.get('Value') for t in tags if isinstance(t, dict) and t.get('Key') == 'Name'), None)
    if tag:
        return tag
    if rtype == 'aws.security-group':
        return r.get('GroupName')
    if rtype == 'aws.rds':
        return r.get('DBInstanceIdentifier')
    return None


def catalog(snapshot: Snapshot) -> list[_Entry]:
    out = []
    for rtype, key in ID_KEYS.items():
        for r in snapshot.of_type(rtype):
            if key in r:
                out.append(_Entry(r[key], _name_of(rtype, r), rtype, r))
    return out


def _name_pattern(name: str) -> re.Pattern:
    """'algo-bench' also matches 'algobench', 'algo bench' and 'AlgoBench'."""
    parts = [re.escape(p) for p in re.split(r'[-_\s.]+', name.strip()) if p]
    body = r'[-_\s.]?'.join(parts)
    return re.compile(rf'(?<![\w-]){body}(?![\w-])', re.IGNORECASE)


def _cued(text: str, span: tuple[int, int]) -> bool:
    before, after = text[:span[0]].lower(), text[span[1]:].lower()
    return bool(re.search(r'\b(?:my|our|the|named|called)\s*["\']?$', before)
                or re.match(rf'\s*["\']?\s*(?:{_ANY_TYPE})\b', after))


def resolve(english: str, snapshot: Snapshot) -> Resolution:
    text = english
    entries = catalog(snapshot)
    by_id = {e.id.lower(): e for e in entries}

    found: list[tuple[tuple[int, int], list[_Entry], str]] = []  # (span, candidates, what was written)
    for m in _ID.finditer(text):
        entry = by_id.get(m.group(0).lower())
        if entry is None:
            return Resolution('not-found', english, message=f'Ward can’t see {m.group(0)} in your account’s latest '
                                                            f'inventory. Check the ID, or refresh the inventory if it was just created.')
        found.append((m.span(), [entry], m.group(0)))

    names: dict[str, list[_Entry]] = {}
    for e in entries:
        if e.name and len(e.name) >= 3 and e.name.lower() != e.id.lower():
            names.setdefault(e.name.lower(), []).append(e)
    taken = [s for s, _, _ in found]
    # Longest names first, so "vansh-lab-2" wins over "vansh-lab".
    for key in sorted(names, key=len, reverse=True):
        for m in _name_pattern(key).finditer(text):
            if any(m.start() < b and a < m.end() for a, b in taken):
                continue
            if key in GENERIC and not _cued(text, m.span()):
                continue
            found.append((m.span(), names[key], m.group(0)))
            taken.append(m.span())

    if not found:
        missing = _unknown_name(text)
        if missing:
            return Resolution('not-found', english, message=f'There’s no resource called “{missing}” in your account’s latest '
                                                            f'inventory. Check the name (it is the Name tag in AWS), or use its ID.')
        return Resolution('none', english)

    # A type word in the sentence settles "the algobench instance" vs its volume of the same name.
    mentioned = {t for t, words in TYPE_WORDS.items() if re.search(rf'\b(?:{words})\b', text, re.IGNORECASE)}
    targets: list[Target] = []
    for span, candidates, written in found:
        narrowed = [c for c in candidates if c.resource_type in mentioned] or candidates
        if len(narrowed) > 1:
            return Resolution('ambiguous', english, questions=[_which(written, narrowed)])
        c = narrowed[0]
        targets.append(Target(id=c.id, name=c.name, resource_type=c.resource_type))

    if len({t.resource_type for t in targets}) > 1:
        return Resolution('unsupported', english, targets=targets,
                          message='One rule can be about one kind of resource. Write a rule for each: '
                                  + ', '.join(f'{t.name or t.id} ({SUBJECT[t.resource_type]})' for t in targets) + '.')

    rtype = targets[0].resource_type
    stop = bool(_STOP.match(text))
    assumptions: list[str] = []
    rewritten = _denamed(text, [s for s, _, _ in found], rtype, len(targets) > 1)

    money = re.search(_MONEY, text, re.IGNORECASE)
    if money and (re.search(_COST_VERB, text, re.IGNORECASE) or stop):
        amount = float((money.group('a') or money.group('b')).replace(',', ''))
        converted = _cost_to_hours(amount, targets, rtype, snapshot)
        if isinstance(converted, str):
            return Resolution('unsupported', english, targets=targets, message=converted)
        hours, note = converted
        rewritten = f'No EC2 instance runs longer than {hours:g} hours'
        assumptions.append(note)
    elif stop:
        # "Stop X after 5 hours": the verb asks for an action Ward will not take; the rule is the condition.
        rewritten = _STOP.sub('', rewritten, count=1)
        if rtype == 'aws.ec2':  # "stop X after 5 hours" → "No instance runs longer than 5 hours"
            rewritten = re.sub(r'^\s*any instance\s+(?:(?:if|when|once)\s+it\s+(?:has\s+)?(?:runs?|been\s+running)\s+)?'
                               r'(?:for\s+)?(?:after|past|beyond|over|more than|longer than)\s+(?=\d)',
                               'No instance runs longer than ', rewritten, flags=re.IGNORECASE)
        rewritten = rewritten[:1].upper() + rewritten[1:]

    if stop:
        assumptions.append('Ward only watches and warns — it never changes your resources. When this rule breaks, '
                           'the alert carries the exact command to stop it.')
    return Resolution('resolved', rewritten.strip(), targets=targets, stop_requested=stop, assumptions=assumptions)


def _denamed(text: str, spans: list[tuple[int, int]], rtype: str, several: bool) -> str:
    """Replace every mention (with its "my"/"the" and a trailing "server"/"instance") by one generic subject."""
    subject = f'any {SUBJECT[rtype]}'
    out, last = [], 0
    for n, (a, b) in enumerate(sorted(spans)):
        pre = re.search(r'(?:\b(?:my|our|the|named|called)\s+)?["\']?$', text[last:a], re.IGNORECASE)
        a = last + pre.start() if pre else a
        # "algobench and vansh-lab servers": the joining word and the type word go with the names.
        post = re.match(rf'["\']?(?:\s*(?:,|and|or)\s*)?(?:\s*(?:{TYPE_WORDS[rtype]})\b)?', text[b:], re.IGNORECASE)
        b = b + (post.end() if post else 0)
        out.append(text[last:a])
        if n == 0:
            out.append(subject + ' ')
        last = b
    out.append(text[last:])
    return re.sub(r'\s{2,}', ' ', ''.join(out)).strip()


def _cost_to_hours(amount: float, targets: list[Target], rtype: str, snapshot: Snapshot):
    if rtype != 'aws.ec2':
        return (f'Ward can turn a cost limit into a rule for EC2 instances, where cost grows with running time. '
                f'For a {SUBJECT[rtype]}, write the limit as a condition instead.')
    resources = {r.get('InstanceId'): r for r in snapshot.of_type('aws.ec2')}
    prices = []
    for t in targets:
        itype = resources.get(t.id, {}).get('InstanceType')
        price = HOURLY_INR.get(itype)
        if price is None:
            return f'Ward has no price for {t.name or t.id} ({itype or "unknown type"}), so it can’t turn ₹{amount:,.0f} into a running time.'
        prices.append((t, itype, price))
    t, itype, price = max(prices, key=lambda p: p[2])  # the dearest one reaches the limit first
    hours = round(amount / price, 1)
    if hours > 24 * 30:
        return (f'At ₹{price:g}/hour ({itype}), ₹{amount:,.0f} is {hours:,.0f} hours of running — more than the 30 days Ward '
                f'can watch a single run for. Pick a lower amount.')
    if hours < 0.25:
        return f'At ₹{price:g}/hour ({itype}), ₹{amount:,.0f} is spent in under 15 minutes — pick a higher amount.'
    return hours, (f'₹{amount:,.0f} ÷ ₹{price:g}/hour ({itype} on-demand, ap-south-1) ≈ {hours:g} hours. The cost is counted '
                   f'from the instance’s current start, for compute only — storage and data transfer are not included.')


def _unknown_name(text: str) -> str | None:
    """A name the sentence clearly means as one ("named X", "my AlgoBench server") that isn't in the inventory."""
    m = re.search(r'\b(?:named|called)\s+["\']?([\w][\w.-]*)', text, re.IGNORECASE) \
        or re.search(r'["\']([\w][\w .-]{1,40})["\']', text)
    if m:
        return m.group(1)
    for m in re.finditer(rf'\b(?:my|our|the)\s+([\w][\w.-]*)\s+(?:{_ANY_TYPE})\b', text, re.IGNORECASE):
        word = m.group(1)
        # Only a word that reads as a name: capitalised mid-word, or with a digit or a hyphen.
        if re.search(r'[a-z][A-Z]|\d|-', word) and word.lower() not in GENERIC and not re.fullmatch(r'[a-z]\d\w*', word.lower()):
            return word
    return None


def _which(written: str, candidates: list[_Entry]) -> dict:
    """A clarifier question whose answers are resource IDs — picking one rewrites the sentence with the ID."""
    def label(e: _Entry) -> str:
        r = e.resource
        state = r.get('State', {}).get('Name') or r.get('DBInstanceStatus') or ''
        detail = ', '.join(x for x in (r.get('InstanceType') or r.get('DBInstanceClass'), state) if x)
        return f'{e.name or e.id} · {e.id}' + (f' ({detail})' if detail else '')

    options = [{'label': label(e), 'value': e.id, 'matches': 1} for e in candidates]
    options.append({'label': f'all {len(candidates)} of them', 'value': ' and '.join(e.id for e in candidates),
                    'matches': len(candidates)})
    return {'term': written, 'question': f'“{written}” is more than one resource — which one?', 'defaultIndex': 0,
            'options': options}


def scope_policy(policy_yaml: str, targets: list[Target]) -> str | None:
    """Add the ID filter to every policy of the targets' type — first, so it is also the cheapest check.

    None when no policy in the document is about that type: the rule can't be narrowed to these resources.
    """
    doc = yaml.safe_load(policy_yaml)
    rtype = targets[0].resource_type
    key = ID_KEYS[rtype]
    ids = [t.id for t in targets]
    scope = {key: ids[0]} if len(ids) == 1 else {'type': 'value', 'key': key, 'op': 'in', 'value': ids}
    slug = re.sub(r'[^a-z0-9]+', '-', (targets[0].name or targets[0].id).lower()).strip('-')[:40]
    touched = 0
    for p in doc.get('policies', []):
        if p.get('resource') not in (rtype, rtype.removeprefix('aws.')):
            continue
        p['filters'] = [scope, *(p.get('filters') or [])]
        if slug and not p['name'].endswith(slug):
            p['name'] = f"{p['name']}-{slug}"[:120]
        touched += 1
    return yaml.safe_dump(doc, sort_keys=False) if touched else None


def stop_command(resource_type: str, resource_id: str, region: str) -> str | None:
    """What a person runs to do what the rule asked for. Ward never runs it."""
    return {
        'aws.ec2': f'aws ec2 stop-instances --instance-ids {resource_id} --region {region}',
        'aws.rds': f'aws rds stop-db-instance --db-instance-identifier {resource_id} --region {region}',
    }.get(resource_type)
