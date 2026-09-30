"""Generate labelled test resources for a rule intent (SRS Phase 1).

Every intent yields at least two positives (must be flagged), two negatives (must not be) and one edge case.
Edge cases target the mistakes generated policies actually make: forgetting the running-state check,
case-sensitive tag keys, and IPv6.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from app.inventory import shapes
from app.inventory.shapes import hours_ago
from app.verifier.intents import (
    Ec2RuntimeIntent, EbsUnattachedIntent, InstanceTypeIntent, OpenPortIntent, RdsPublicIntent, RegionIntent,
    RequireTagIntent,
)

FixtureKind = Literal['positive', 'negative', 'edge']


@dataclass
class Fixture:
    id: str
    kind: FixtureKind
    description: str
    resource_type: str
    resource: dict
    expected: bool  # True when the rule must flag this resource


def generate(intent, now: datetime | None = None) -> list[Fixture]:
    now = now or datetime.now(timezone.utc)
    builder = _BUILDERS[type(intent)]
    fixtures = builder(intent, now)
    return _scoped(fixtures, intent.targets) if intent.targets else fixtures


def _scoped(fixtures: list[Fixture], targets) -> list[Fixture]:
    """A rule about one resource must still get the shape right *and* catch nothing else.

    Every shape fixture is re-pointed at the target, so the policy is tested on the resource it is about.
    Then each positive gets a twin: identical in every way except its ID. The twin must not be flagged —
    it is what a rule that forgot its scope would catch, i.e. somebody else's server.
    """
    from app.engine.custodian import ID_KEYS

    out = []
    for f in fixtures:
        target = next((t for t in targets if t.resource_type == f.resource_type), None)
        if target is None:
            out.append(f)
            continue
        key = ID_KEYS[f.resource_type]
        out.append(Fixture(f.id, f.kind, f'{f.description} — {target.name or target.id} itself', f.resource_type,
                           {**f.resource, key: target.id}, f.expected))
        if f.expected:
            out.append(Fixture(f'twin-{f.id}', 'negative', f'{f.description}, but a different resource — outside the scope',
                               f.resource_type, {**f.resource, key: f'{f.resource[key]}-twin'}, False))
    return out


def _ec2_runtime(intent: Ec2RuntimeIntent, now: datetime) -> list[Fixture]:
    h = intent.hours
    target, other = ('g5.xlarge', 'p3.2xlarge') if intent.gpu_only else ('t3.small', 'm5.large')
    young = max(h * 0.5, 0.25)
    fx = [
        Fixture('pos-over-limit', 'positive', f'{target} running {h * 1.5 + 1:g}h', 'aws.ec2',
                shapes.ec2('i-pos1', target, launched=hours_ago(now, h * 1.5 + 1)), True),
        Fixture('pos-just-over', 'positive', f'{other} running {h + 2:g}h', 'aws.ec2',
                shapes.ec2('i-pos2', other, launched=hours_ago(now, h + 2)), True),
        Fixture('neg-under-limit', 'negative', f'{target} running {young:g}h', 'aws.ec2',
                shapes.ec2('i-neg1', target, launched=hours_ago(now, young)), False),
        Fixture('edge-stopped', 'edge', f'{target} launched {h * 2:g}h ago but stopped — not costing compute', 'aws.ec2',
                shapes.ec2('i-edge1', target, launched=hours_ago(now, h * 2), running=False), False),
    ]
    if intent.gpu_only:
        fx.append(Fixture('neg-not-gpu', 'negative', f't3.micro running {h * 3:g}h — not a GPU', 'aws.ec2',
                          shapes.ec2('i-neg2', 't3.micro', launched=hours_ago(now, h * 3)), False))
    else:
        fx.append(Fixture('neg-well-under', 'negative', f'{other} running {young / 2:g}h', 'aws.ec2',
                          shapes.ec2('i-neg2', other, launched=hours_ago(now, young / 2)), False))
    if intent.exempt_tag:
        fx.append(Fixture('edge-exempt', 'edge', f'{target} running {h * 2:g}h but tagged {intent.exempt_tag}', 'aws.ec2',
                          shapes.ec2('i-edge2', target, launched=hours_ago(now, h * 2), tags={intent.exempt_tag: 'production'}), False))
    return fx


def _require_tag(intent: RequireTagIntent, now: datetime) -> list[Fixture]:
    tag = intent.tag
    lower = tag.lower() if tag.lower() != tag else tag.upper()
    if intent.resource == 'ebs':
        make = lambda rid, tags: shapes.ebs(rid, created=hours_ago(now, 48), tags=tags)
        rtype = 'aws.ebs'
    else:
        itype = 'g5.xlarge' if intent.gpu_only else 't3.micro'
        make = lambda rid, tags: shapes.ec2(rid, itype, launched=hours_ago(now, 3), tags=tags)
        rtype = 'aws.ec2'

    fx = [
        Fixture('pos-no-tags', 'positive', 'no tags at all', rtype, make('i-pos1' if rtype == 'aws.ec2' else 'vol-pos1', None), True),
        # The filler tag must not be the tag under test, or "must have a Project tag" is handed a
        # resource that already has one and told to flag it.
        Fixture('pos-other-tags', 'positive', f'carries another tag but no {tag}', rtype,
                make('i-pos2' if rtype == 'aws.ec2' else 'vol-pos2',
                     {'Project' if tag != 'Project' else 'Service': 'attendance'}), True),
        Fixture('neg-tagged', 'negative', f'{tag}=riya', rtype, make('i-neg1' if rtype == 'aws.ec2' else 'vol-neg1', {tag: 'riya'}), False),
        Fixture('neg-tagged-plus', 'negative', f'{tag}=team plus other tags', rtype,
                make('i-neg2' if rtype == 'aws.ec2' else 'vol-neg2', {tag: 'team', 'Project': 'x'}), False),
        Fixture('edge-wrong-case', 'edge', f"tag key '{lower}' — AWS tag keys are case-sensitive, so {tag} is still missing", rtype,
                make('i-edge1' if rtype == 'aws.ec2' else 'vol-edge1', {lower: 'riya'}), True),
    ]
    if intent.gpu_only and rtype == 'aws.ec2':
        fx.append(Fixture('neg-untagged-cpu', 'negative', f't3.micro with no {tag} — not a GPU', 'aws.ec2',
                          shapes.ec2('i-neg3', 't3.micro', launched=hours_ago(now, 3)), False))
    return fx


def _ebs_unattached(intent: EbsUnattachedIntent, now: datetime) -> list[Fixture]:
    d = intent.min_age_days
    old = (d + 3) * 24
    fx = [
        Fixture('pos-unattached-old', 'positive', f'unattached for {d + 3} days', 'aws.ebs', shapes.ebs('vol-pos1', created=hours_ago(now, old)), True),
        Fixture('pos-unattached-large', 'positive', f'200 GB, unattached for {d + 10} days', 'aws.ebs',
                shapes.ebs('vol-pos2', created=hours_ago(now, (d + 10) * 24), size_gb=200), True),
        Fixture('neg-attached', 'negative', 'attached to a running instance', 'aws.ebs',
                shapes.ebs('vol-neg1', created=hours_ago(now, old), attached_to='i-web'), False),
        Fixture('neg-attached-new', 'negative', 'attached, created an hour ago', 'aws.ebs',
                shapes.ebs('vol-neg2', created=hours_ago(now, 1), attached_to='i-api'), False),
    ]
    if d > 0:
        fx.append(Fixture('edge-unattached-young', 'edge', f'unattached but only {max(d - 1, 0) * 24 + 12}h old — inside the grace period', 'aws.ebs',
                          shapes.ebs('vol-edge1', created=hours_ago(now, max(d - 1, 0) * 24 + 12)), False))
    else:
        fx.append(Fixture('edge-root-volume', 'edge', 'boot volume of a stopped instance — still attached', 'aws.ebs',
                          shapes.ebs('vol-edge1', created=hours_ago(now, old * 2), attached_to='i-stopped'), False))
    return fx


def _rds_public(_: RdsPublicIntent, now: datetime) -> list[Fixture]:
    created = hours_ago(now, 24 * 5)
    return [
        Fixture('pos-public', 'positive', 'db.t3.micro, publicly accessible', 'aws.rds', shapes.rds('db-pos1', 'db.t3.micro', created=created, public=True), True),
        Fixture('pos-public-large', 'positive', 'db.t3.medium, publicly accessible', 'aws.rds', shapes.rds('db-pos2', 'db.t3.medium', created=created, public=True), True),
        Fixture('neg-private', 'negative', 'private database', 'aws.rds', shapes.rds('db-neg1', 'db.t3.micro', created=created), False),
        Fixture('neg-private-large', 'negative', 'private, larger class', 'aws.rds', shapes.rds('db-neg2', 'db.r5.large', created=created), False),
        Fixture('edge-stopped-public', 'edge', 'stopped, but configured public — exposed the moment it starts', 'aws.rds',
                shapes.rds('db-edge1', 'db.t3.micro', created=created, public=True, status='stopped'), True),
    ]


def _sg_open_port(intent: OpenPortIntent, _: datetime) -> list[Fixture]:
    p = intent.port
    other = 443 if p != 443 else 8443
    sg = shapes.security_group
    return [
        Fixture('pos-ipv4-open', 'positive', f'port {p} open to 0.0.0.0/0', 'aws.security-group',
                sg('sg-pos1', 'launch-wizard-1', rules=[shapes.ingress(p, ipv4=('0.0.0.0/0',))]), True),
        Fixture('pos-all-ports', 'positive', 'every port open to 0.0.0.0/0', 'aws.security-group',
                sg('sg-pos2', 'wide-open', rules=[shapes.ingress(0, 65535, ipv4=('0.0.0.0/0',))]), True),
        Fixture('neg-private-cidr', 'negative', f'port {p} open only inside the VPC', 'aws.security-group',
                sg('sg-neg1', 'internal', rules=[shapes.ingress(p, ipv4=('10.0.0.0/16',))]), False),
        Fixture('neg-other-port', 'negative', f'only port {other} is public', 'aws.security-group',
                sg('sg-neg2', 'web', rules=[shapes.ingress(other, ipv4=('0.0.0.0/0',))]), False),
        Fixture('edge-ipv6-open', 'edge', f'port {p} open to ::/0 — the whole internet over IPv6', 'aws.security-group',
                sg('sg-edge1', 'ipv6-only', rules=[shapes.ingress(p, ipv6=('::/0',))]), True),
    ]


def _instance_type(intent: InstanceTypeIntent, now: datetime) -> list[Fixture]:
    allowed = intent.allowed[0]
    banned = 'm5.4xlarge' if allowed != 'm5.4xlarge' else 'c5.9xlarge'
    return [
        Fixture('pos-banned-type', 'positive', f'{banned} running — not on the allowlist', 'aws.ec2',
                shapes.ec2('i-pos1', banned, launched=hours_ago(now, 3)), True),
        Fixture('pos-large-gpu', 'positive', 'p3.2xlarge running — not on the allowlist', 'aws.ec2',
                shapes.ec2('i-pos2', 'p3.2xlarge', launched=hours_ago(now, 1)), True),
        Fixture('neg-allowed-type', 'negative', f'{allowed} running — allowed', 'aws.ec2',
                shapes.ec2('i-neg1', allowed, launched=hours_ago(now, 30)), False),
        Fixture('neg-allowed-again', 'negative', f'another {allowed}, long-running but allowed', 'aws.ec2',
                shapes.ec2('i-neg2', allowed, launched=hours_ago(now, 400)), False),
        # The mistake this catches: matching on a prefix, so t3.micro accidentally permits t3.2xlarge.
        Fixture('edge-same-family', 'edge', 'a larger instance in an allowed family', 'aws.ec2',
                shapes.ec2('i-edge1', f'{allowed.split(".")[0]}.2xlarge', launched=hours_ago(now, 5)),
                f'{allowed.split(".")[0]}.2xlarge' not in intent.allowed),
    ]


def _region(intent: RegionIntent, now: datetime) -> list[Fixture]:
    home, away = intent.region, 'us-east-1' if intent.region != 'us-east-1' else 'eu-west-1'
    return [
        Fixture('pos-other-region', 'positive', f'instance running in {away}', 'aws.ec2',
                shapes.ec2('i-pos1', 't3.small', launched=hours_ago(now, 5), region=away), True),
        Fixture('pos-far-region', 'positive', 'instance running in sa-east-1', 'aws.ec2',
                shapes.ec2('i-pos2', 't3.micro', launched=hours_ago(now, 30), region='sa-east-1'), True),
        Fixture('neg-home-region', 'negative', f'instance running in {home}', 'aws.ec2',
                shapes.ec2('i-neg1', 't3.small', launched=hours_ago(now, 5), region=home), False),
        Fixture('neg-home-region-old', 'negative', f'long-running instance in {home}', 'aws.ec2',
                shapes.ec2('i-neg2', 'm5.large', launched=hours_ago(now, 400), region=home), False),
        # The mistake this catches: flagging a stopped instance elsewhere, which costs storage, not compute.
        Fixture('edge-stopped-elsewhere', 'edge', f'stopped instance in {away}', 'aws.ec2',
                shapes.ec2('i-edge1', 't3.small', launched=hours_ago(now, 100), running=False, region=away), False),
    ]


_BUILDERS = {
    Ec2RuntimeIntent: _ec2_runtime,
    InstanceTypeIntent: _instance_type,
    RegionIntent: _region,
    RequireTagIntent: _require_tag,
    EbsUnattachedIntent: _ebs_unattached,
    RdsPublicIntent: _rds_public,
    OpenPortIntent: _sg_open_port,
}
