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
    Ec2RuntimeIntent, EbsUnattachedIntent, OpenPortIntent, RdsPublicIntent, RequireTagIntent,
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
    return builder(intent, now)


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
        Fixture('pos-other-tags', 'positive', f'has Project tag but no {tag}', rtype,
                make('i-pos2' if rtype == 'aws.ec2' else 'vol-pos2', {'Project': 'attendance'}), True),
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


_BUILDERS = {
    Ec2RuntimeIntent: _ec2_runtime,
    RequireTagIntent: _require_tag,
    EbsUnattachedIntent: _ebs_unattached,
    RdsPublicIntent: _rds_public,
    OpenPortIntent: _sg_open_port,
}
