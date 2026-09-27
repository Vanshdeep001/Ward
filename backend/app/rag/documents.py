"""Step 1 of the pipeline: turn the inventory into documents a retriever can search.

One document per resource, written as plain English rather than a JSON dump, because both retrievers —
Pinecone's embedding model and the local keyword index — match meaning and words, not field names. So an
EC2 instance says it is a "virtual server", a volume says it is "storage", and a missing Owner tag is
spelled out as "no owner", which is how people ask.

A resource's document also carries what Ward knows *about* it — the guardrails it is breaking and any
security finding — so "what's wrong with algobench?" is answerable from one retrieval.

One more document summarises the whole account. Retrieval is good at "which resource…" and bad at "how
many…", because a count lives in no single resource; the overview holds the totals.
"""
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime

from app.engine.custodian import resource_id
from app.inventory.pricing import hourly_cost
from app.inventory.store import Snapshot
from app.rag.guardrails import REMOVED, clean

OVERVIEW_ID = 'account-overview'

KIND = {
    'aws.ec2': ('ec2', 'EC2 instance', 'virtual server / VM / compute'),
    'aws.ebs': ('ebs', 'EBS volume', 'block storage / disk'),
    'aws.rds': ('rds', 'RDS database', 'managed database'),
    'aws.security-group': ('sg', 'security group', 'firewall rules'),
    'aws.nat-gateway': ('nat', 'NAT gateway', 'network gateway'),
}

REGION_NAMES = {
    'ap-south-1': 'Mumbai', 'ap-south-2': 'Hyderabad', 'us-east-1': 'N. Virginia', 'us-east-2': 'Ohio',
    'us-west-1': 'N. California', 'us-west-2': 'Oregon', 'eu-west-1': 'Ireland', 'eu-central-1': 'Frankfurt',
    'ap-southeast-1': 'Singapore', 'ap-northeast-1': 'Tokyo',
}


@dataclass(frozen=True)
class Doc:
    id: str
    text: str
    # Flat metadata stored beside the text: shown on source cards and usable as filters. Pinecone accepts
    # strings, numbers, booleans and lists of strings — never None — so empty values are left out.
    fields: dict = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha1(self.text.encode()).hexdigest()


def build_documents(snapshot: Snapshot, alerts: list[dict], findings: list[dict], home_region: str) -> list[Doc]:
    """alerts: open/snoozed alerts as {resourceId, rule, level, status}; findings: guardian findings."""
    breaking: dict[str, list[dict]] = {}
    for a in alerts:
        breaking.setdefault(a['resourceId'], []).append(a)
    flagged: dict[str, list[dict]] = {}
    for f in findings:
        for rid in f.get('resourceIds', []):
            flagged.setdefault(rid, []).append(f)

    docs = [
        _resource_doc(rtype, r, snapshot.taken_at, home_region, breaking.get(resource_id(rtype, r), []),
                      flagged.get(resource_id(rtype, r), []))
        for rtype, resources in snapshot.resources.items() if rtype in KIND
        for r in resources
    ]
    docs.append(_overview(docs, snapshot.taken_at, home_region))
    return docs


def _resource_doc(rtype: str, r: dict, now: datetime, home: str, alerts: list[dict], findings: list[dict]) -> Doc:
    short, label, plain = KIND[rtype]
    rid = resource_id(rtype, r)
    # Tags and names are written by whoever can tag the resource: untrusted text, cleaned before the model reads it.
    tags = {clean(t['Key']): clean(t['Value']) for t in r.get('Tags', [])}
    name = tags.get('Name') or clean(r.get('GroupName') or r.get('DBInstanceIdentifier') or rid)
    region = _region(r)
    per_day = round((hourly_cost(rtype, r) or 0) * 24, 2)
    running = _running(rtype, r)

    parts = [f'{label} "{name}" ({rid}), a {plain}.']
    detail = r.get('InstanceType') or r.get('DBInstanceClass')
    if detail:
        gpu = rtype == 'aws.ec2' and re.match(r'(p|g|inf|trn|dl)\d', detail)
        parts.append(f'Type {detail}' + (', a GPU / accelerator instance (expensive).' if gpu else '.'))
    if rtype == 'aws.rds':
        parts.append(f"Engine {r.get('Engine', 'unknown')}; "
                     f"{'PUBLICLY ACCESSIBLE from the internet' if r.get('PubliclyAccessible') else 'not publicly accessible'}.")
    if rtype == 'aws.ebs':
        attached = bool(r.get('Attachments'))
        parts.append(f"{r.get('Size', '?')} GB {r.get('VolumeType', '')}, "
                     f"{'attached to an instance (in use, not idle)' if attached else 'unattached (idle, not attached to anything)'}.")
    if rtype == 'aws.security-group':
        parts.append(_ports(r))

    state = _state_words(rtype, r, running)
    if state:
        parts.append(state)
    age = _age_days(r, now)
    if running and rtype == 'aws.ec2' and age is not None:
        parts.append(f'Running for {_days(age)}.')
    elif age is not None:
        parts.append(f'Created {_days(age)} ago.')

    if region:
        where = f'Region {region} ({REGION_NAMES.get(region, region)})'
        parts.append(where + ('.' if region == home else f', outside the home region {home}.'))
    parts.append(f'Costs ₹{per_day:,.2f} a day (about ₹{per_day * 30:,.0f} a month).' if per_day else 'Costs nothing right now.')

    other = {k: v for k, v in tags.items() if k not in ('Name',)}
    parts.append(f"Owner: {tags['Owner']}." if 'Owner' in tags else 'No owner — the Owner tag is missing.')
    if other:
        parts.append('Tags: ' + ', '.join(f'{k}={v}' for k, v in other.items()) + '.')
    else:
        parts.append('No tags.')

    if any(REMOVED in v for v in [name, *tags.keys(), *tags.values()]):
        parts.append('Warning: a tag on this resource contained instruction-like text, which was removed.')
    for a in alerts:
        verb = 'snoozed alert' if a['status'] == 'snoozed' else ('breaking' if a['level'] == 'alert' else 'close to breaking')
        parts.append(f'Guardrail {verb}: "{a["rule"]}".')
    for f in findings:
        if len(f.get('resourceIds', [])) > 3:
            continue  # account-wide findings ("9 resources have no Owner tag") belong in the overview, not here
        parts.append(f"Security/waste finding ({f.get('severity', 'info')}): {f['title']}.")

    fields = {
        'name': name, 'type': short, 'region': region, 'running': running, 'costPerDay': per_day,
        'owner': tags.get('Owner'), 'alerts': len(alerts), 'detail': detail or (f"{r['Size']} GB" if 'Size' in r else None),
    }
    return Doc(id=rid, text=' '.join(parts), fields={k: v for k, v in fields.items() if v is not None})


def _overview(docs: list[Doc], now: datetime, home: str) -> Doc:
    resources = [d for d in docs if d.id != OVERVIEW_ID]
    by_type: dict[str, int] = {}
    for d in resources:
        by_type[d.fields['type']] = by_type.get(d.fields['type'], 0) + 1
    labels = {short: label for short, label, _ in KIND.values()}
    total = sum(d.fields.get('costPerDay', 0) for d in resources)
    running = [d for d in resources if d.fields.get('running')]
    ownerless = [d for d in resources if 'owner' not in d.fields]
    away = [d for d in resources if d.fields.get('region') and d.fields['region'] != home]
    alerted = [d for d in resources if d.fields.get('alerts')]
    priciest = sorted((d for d in resources if d.fields.get('costPerDay')), key=lambda d: -d.fields['costPerDay'])[:5]

    def names(ds):
        return ', '.join(f"{d.fields['name']} ({d.id})" for d in ds) or 'none'

    text = ' '.join([
        f'Account overview as of {now:%d %b %Y}: {len(resources)} resources in total —',
        '; '.join(f'{n} {labels[t]}{"s" if n != 1 else ""}' for t, n in sorted(by_type.items())) + '.',
        f'Together they cost ₹{total:,.2f} a day (about ₹{total * 30:,.0f} a month).',
        f'{len(running)} running: {names(running)}.',
        f'Most expensive: ' + ', '.join(f"{d.fields['name']} ₹{d.fields['costPerDay']:,.2f}/day" for d in priciest) + '.' if priciest else 'Nothing costs money right now.',
        f'{len(ownerless)} have no Owner tag: {names(ownerless)}.',
        f'{len(away)} are outside the home region {home}: {names(away)}.',
        f'{len(alerted)} are breaking a guardrail: {names(alerted)}.',
    ])
    return Doc(id=OVERVIEW_ID, text=text, fields={'name': 'Account overview', 'type': 'overview', 'costPerDay': round(total, 2)})


def _running(rtype: str, r: dict) -> bool:
    if rtype == 'aws.ec2':
        return r.get('State', {}).get('Name') == 'running'
    if rtype == 'aws.rds':
        return r.get('DBInstanceStatus') == 'available'
    if rtype == 'aws.nat-gateway':
        return r.get('State') == 'available'
    return False


def _state_words(rtype: str, r: dict, running: bool) -> str | None:
    if rtype == 'aws.ec2':
        return 'Currently running.' if running else f"Currently {r.get('State', {}).get('Name', 'stopped')} (not running)."
    if rtype in ('aws.rds', 'aws.nat-gateway'):
        return 'Currently available (running).' if running else 'Currently not running.'
    return None


def _ports(r: dict) -> str:
    rules = []
    for p in r.get('IpPermissions', []):
        sources = [x['CidrIp'] for x in p.get('IpRanges', [])] + [x['CidrIpv6'] for x in p.get('Ipv6Ranges', [])]
        port = 'all ports' if p.get('IpProtocol') == '-1' else (
            f"port {p.get('FromPort')}" if p.get('FromPort') == p.get('ToPort') else f"ports {p.get('FromPort')}-{p.get('ToPort')}")
        for src in sources or ['other groups']:
            world = src in ('0.0.0.0/0', '::/0')
            rules.append(f"{port} open to {'the whole internet' if world else src}"
                         + (' (SSH)' if p.get('FromPort') == 22 else '') + (' (RDP)' if p.get('FromPort') == 3389 else ''))
    return ('Inbound: ' + '; '.join(rules) + '.') if rules else 'No inbound rules.'


def _region(r: dict) -> str | None:
    az = r.get('Placement', {}).get('AvailabilityZone') or r.get('AvailabilityZone') or ''
    return az[:-1] or None


def _age_days(r: dict, now: datetime) -> float | None:
    at = r.get('LaunchTime') or r.get('CreateTime') or r.get('InstanceCreateTime')
    return None if at is None else (now - at).total_seconds() / 86400


def _days(days: float) -> str:
    # Whole days, so a document's text — and so its fingerprint — changes once a day, not every sweep.
    if days < 1:
        return 'less than a day'
    n = int(days)
    return f'{n} day{"s" if n != 1 else ""}'
