"""What a rule is supposed to do, stated structurally.

Fixtures are generated from the intent — never from the candidate policy — so a wrong policy cannot
grade itself. In the compile pipeline the intent comes from the rule family a seed rule belongs to (SRS §9.3).
"""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class Ec2RuntimeIntent(BaseModel):
    """No instance runs longer than `hours`."""
    kind: Literal['ec2-runtime'] = 'ec2-runtime'
    hours: float = Field(gt=0, le=24 * 30)
    gpu_only: bool = False
    exempt_tag: str | None = Field(default=None, description='Instances carrying this tag key are exempt, e.g. Environment.')


class RequireTagIntent(BaseModel):
    """Flag resources that lack a tag key."""
    kind: Literal['require-tag'] = 'require-tag'
    tag: str = 'Owner'
    resource: Literal['ec2', 'ebs'] = 'ec2'
    gpu_only: bool = False


class EbsUnattachedIntent(BaseModel):
    """Flag volumes not attached to any instance, optionally only once older than `min_age_days`."""
    kind: Literal['ebs-unattached'] = 'ebs-unattached'
    min_age_days: int = Field(default=0, ge=0, le=365)


class RdsPublicIntent(BaseModel):
    """Flag databases that accept connections from the internet."""
    kind: Literal['rds-public'] = 'rds-public'


class OpenPortIntent(BaseModel):
    """Flag security groups exposing `port` to the whole internet, over IPv4 or IPv6."""
    kind: Literal['sg-open-port'] = 'sg-open-port'
    port: int = Field(default=22, ge=0, le=65535)


Intent = Annotated[
    Union[Ec2RuntimeIntent, RequireTagIntent, EbsUnattachedIntent, RdsPublicIntent, OpenPortIntent],
    Field(discriminator='kind'),
]
