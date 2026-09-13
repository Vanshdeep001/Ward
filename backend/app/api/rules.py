from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.config import settings
from app.engine.custodian import SUPPORTED_RESOURCES, PolicyError, load_policies
from app.inventory.store import InventoryStore
from app.api.deps import get_inventory
from app.simulator.dryrun import simulate_policy
from app.simulator.models import SimulationResult
from app.simulator.timetravel import replay
from app.verifier import fixtures as fixture_gen
from app.verifier.intents import Intent
from app.verifier.report import VerifyReport
from app.verifier.runner import verify

router = APIRouter(prefix='/rules', tags=['rules'])


class CustomFixture(BaseModel):
    id: str
    resource_type: str = Field(examples=['aws.ec2'])
    resource: dict
    expected: bool
    kind: str = 'custom'
    description: str = ''


class VerifyRequest(BaseModel):
    policy_yaml: str
    intent: Intent | None = None
    fixtures: list[CustomFixture] | None = None

    @model_validator(mode='after')
    def one_source(self):
        if (self.intent is None) == (self.fixtures is None):
            raise ValueError('Provide exactly one of intent (generated fixtures) or fixtures (your own).')
        return self


class FixturePreviewRequest(BaseModel):
    intent: Intent


@router.post('/verify', response_model=VerifyReport)
def verify_policy(req: VerifyRequest) -> VerifyReport:
    """Run a candidate policy against labelled fixtures. An invalid policy is a failed report, not an HTTP error."""
    if req.intent is not None:
        fixtures = fixture_gen.generate(req.intent)
    else:
        unsupported = {f.resource_type for f in req.fixtures} - set(SUPPORTED_RESOURCES)
        if unsupported:
            raise HTTPException(422, f"Unsupported fixture resource_type: {', '.join(sorted(unsupported))}")
        fixtures = [fixture_gen.Fixture(f.id, f.kind, f.description, f.resource_type, f.resource, f.expected) for f in req.fixtures]
    return verify(req.policy_yaml, fixtures, settings.region)


@router.post('/verify/fixtures')
def preview_fixtures(req: FixturePreviewRequest):
    """The fixtures an intent generates — for inspecting what a rule family is tested against."""
    return [
        {'id': f.id, 'kind': f.kind, 'description': f.description, 'resource_type': f.resource_type, 'expected': f.expected, 'resource': f.resource}
        for f in fixture_gen.generate(req.intent)
    ]


class SimulateRequest(BaseModel):
    policy_yaml: str
    history_days: int = Field(default=30, ge=0, le=90, description='0 skips the historical replay.')


@router.post('/simulate', response_model=SimulationResult)
def simulate(req: SimulateRequest, inventory: InventoryStore = Depends(get_inventory)) -> SimulationResult:
    """Dry-run a policy against current inventory and replay it over stored history. Nothing is activated."""
    try:
        policies = load_policies(req.policy_yaml, settings.region)
    except PolicyError as e:
        raise HTTPException(422, str(e)) from e

    latest = inventory.latest()
    history = None
    if req.history_days:
        history = replay(policies, inventory.history(req.history_days), req.history_days)
    return SimulationResult(
        inventory_as_of=latest.taken_at,
        policies=[simulate_policy(p, latest) for p in policies],
        history=history,
    )
