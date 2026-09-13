from pydantic import BaseModel


class FixtureResult(BaseModel):
    id: str
    kind: str
    description: str
    resource_id: str
    expected: bool
    actual: bool | None  # None when the policy never ran
    correct: bool | None


class Rates(BaseModel):
    """SRS §9.9 — positive pass catches violations, negative pass avoids false alarms."""
    positive_pass: float | None
    negative_pass: float | None
    edge_pass: float | None


class VerifyReport(BaseModel):
    passed: bool
    expected: list[str]  # resource ids the rule must flag
    actual: list[str]  # resource ids the policy did flag
    error: str | None = None
    fixtures: list[FixtureResult]
    rates: Rates
    duration_ms: float
