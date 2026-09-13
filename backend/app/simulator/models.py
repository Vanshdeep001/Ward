from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class MatchedResource(BaseModel):
    id: str
    name: str | None
    detail: str | None  # instance type, DB class, volume size
    region: str | None
    running_hours: float | None
    cost_per_day: float | None


class FunnelStepOut(BaseModel):
    filter: str
    remaining: int


class PolicySimulation(BaseModel):
    policy: str
    resource_type: str
    resource_label: str
    population: int
    matched: list[MatchedResource]
    funnel: list[FunnelStepOut]
    breadth: Literal['none', 'normal', 'broad']
    zero_reason: str | None
    cost_per_day: float  # combined daily cost of everything matched right now


class FireEvent(BaseModel):
    at: datetime
    resource_id: str
    name: str | None
    policy: str


class History(BaseModel):
    days: int
    snapshots: int
    fires: int
    events: list[FireEvent]
    quiet_days: int
    alerts_per_week: float
    caveats: list[str]


class SimulationResult(BaseModel):
    inventory_as_of: datetime
    policies: list[PolicySimulation]
    history: History | None
