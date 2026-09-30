"""What a rule is supposed to do, stated structurally.

Fixtures are generated from the intent — never from the candidate policy — so a wrong policy cannot
grade itself. In the compile pipeline the intent comes from the rule family a seed rule belongs to (SRS §9.3).
"""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class Target(BaseModel):
    """One named resource a rule is about, pinned by its ID — a name can be reused, the ID cannot."""
    id: str
    name: str | None = None
    resource_type: str


class _Scoped(BaseModel):
    """Every rule family can be narrowed to particular resources ("stop my algobench server …").

    Empty `targets` means the rule is about every resource of its type. `stop_requested` records that
    the sentence asked Ward to act; Ward is read-only, so it alerts and hands over the command instead.
    """
    targets: list[Target] = []
    stop_requested: bool = False


class Ec2RuntimeIntent(_Scoped):
    """No instance runs longer than `hours`."""
    kind: Literal['ec2-runtime'] = 'ec2-runtime'
    hours: float = Field(gt=0, le=24 * 30)
    gpu_only: bool = False
    exempt_tag: str | None = Field(default=None, description='Instances carrying this tag key are exempt, e.g. Environment.')


class RequireTagIntent(_Scoped):
    """Flag resources that lack a tag key."""
    kind: Literal['require-tag'] = 'require-tag'
    tag: str = 'Owner'
    resource: Literal['ec2', 'ebs'] = 'ec2'
    gpu_only: bool = False


class EbsUnattachedIntent(_Scoped):
    """Flag volumes not attached to any instance, optionally only once older than `min_age_days`."""
    kind: Literal['ebs-unattached'] = 'ebs-unattached'
    min_age_days: int = Field(default=0, ge=0, le=365)


class RdsPublicIntent(_Scoped):
    """Flag databases that accept connections from the internet."""
    kind: Literal['rds-public'] = 'rds-public'


class OpenPortIntent(_Scoped):
    """Flag security groups exposing `port` to the whole internet, over IPv4 or IPv6."""
    kind: Literal['sg-open-port'] = 'sg-open-port'
    port: int = Field(default=22, ge=0, le=65535)


class InstanceTypeIntent(_Scoped):
    """Only these instance types may run — the allowlist that keeps a lab account off large hardware."""
    kind: Literal['instance-type'] = 'instance-type'
    allowed: list[str] = Field(min_length=1, examples=[['t3.micro', 't2.micro']])


class RegionIntent(_Scoped):
    """Flag running instances outside the region the account is supposed to use."""
    kind: Literal['region'] = 'region'
    region: str = 'ap-south-1'


Intent = Annotated[
    Union[Ec2RuntimeIntent, RequireTagIntent, EbsUnattachedIntent, RdsPublicIntent, OpenPortIntent, RegionIntent,
          InstanceTypeIntent],
    Field(discriminator='kind'),
]
