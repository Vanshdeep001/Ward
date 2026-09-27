import re
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, TypeAdapter, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_inventory, get_session
from app.compiler import clarify
from app.compiler.service import compile_rule, draft_for
from app.config import settings
from app.engine.custodian import SUPPORTED_RESOURCES, PolicyError, load_policies
from app.guardian import quality
from app.inventory.store import InventoryStore
from app.models import Rule
from app.rules_service import VerificationFailed, create_rule
from app.simulator.dryrun import simulate_now, simulate_policy
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


# ─── Rule storage ─────────────────────────────────────────────────────────────


class CreateRuleRequest(BaseModel):
    """`policy_yaml` and `intent` are optional: given only English, Ward compiles it first."""
    english: str = Field(min_length=3, max_length=500)
    policy_yaml: str | None = None
    intent: Intent | None = None

    @model_validator(mode='after')
    def both_or_neither(self):
        if (self.policy_yaml is None) != (self.intent is None):
            raise ValueError('Send policy_yaml and intent together, or neither to compile from English.')
        return self


class CompileRequest(BaseModel):
    english: str = Field(min_length=3, max_length=500)
    skip_clarify: bool = Field(default=False, alias='skipClarify')
    choices: dict[str, str] | None = Field(default=None, description='Answers to clarifier questions, by term.')

    model_config = {'populate_by_name': True}


class WhatIfRequest(BaseModel):
    """Sweep one parameter of a rule to see how the alert volume responds (SRS §16.4)."""
    english: str = Field(min_length=3, max_length=500)
    param: str = Field(examples=['hours'])
    values: list[float] = Field(min_length=1, max_length=12)


class UpdateRuleRequest(BaseModel):
    status: Literal['active', 'paused']


def rule_out(rule: Rule, now: datetime | None = None, scored: dict | None = None) -> dict:
    """The shape the frontend's Guardrails table reads."""
    now = now or datetime.now(timezone.utc)
    recent = [a for a in rule.alerts if a.created_at >= now - timedelta(days=30)]
    acted_on = [a for a in recent if a.resolved_at and a.resolved_at - a.created_at <= timedelta(hours=2)]
    return {
        'id': rule.id,
        'english': rule.english,
        'status': rule.status,
        'verified': rule.verified,
        'createdAt': rule.created_at.isoformat(),
        'firesLast30d': len(recent),
        'actedOn': len(acted_on),
        # What this rule prevented: the daily cost of what it caught and someone acted on (SRS §17).
        'savings30d': round(sum(a.cost_per_day or 0 for a in acted_on), 2),
        'quality': (scored or {}).get('quality'),  # None until the rule leaves the provisional window
        'breakdown': (scored or {}).get('breakdown'),
        'improvementTip': (scored or {}).get('improvementTip'),
        'yaml': rule.policy_yaml,
        'intent': rule.intent,
    }


@router.get('')
def list_rules(inventory: InventoryStore = Depends(get_inventory), session: Session = Depends(get_session)):
    rules = session.scalars(select(Rule).order_by(Rule.created_at)).all()
    snapshot = inventory.latest()
    return [rule_out(r, scored=quality.score(r, snapshot, settings.region)) for r in rules]


@router.post('/compile')
def compile_rule_endpoint(req: CompileRequest, inventory: InventoryStore = Depends(get_inventory)):
    """English in, verified policy out — or a question, or an honest failure. Never an HTTP error."""
    english = clarify.apply_choices(req.english, req.choices) if req.choices else req.english
    return compile_rule(english, inventory, settings.region, skip_clarify=req.skip_clarify or bool(req.choices))


@router.post('/whatif')
def what_if(req: WhatIfRequest, inventory: InventoryStore = Depends(get_inventory)):
    """How many resources each threshold would catch, so a limit is chosen against evidence."""
    draft = draft_for(req.english)
    if draft is None or req.param not in draft.params:
        raise HTTPException(422, f'Cannot vary “{req.param}” for this rule.')

    snapshot = inventory.latest()
    out = []
    for value in req.values:
        variant = draft_for(_restate(draft, req.param, value))
        if variant is None:
            continue
        sims = simulate_now(variant.policy_yaml, snapshot, settings.region)
        matched = sum(len(s.matched) for s in sims)
        out.append({
            'value': value,
            'matched': matched,
            'costPerDay': round(sum(s.cost_per_day for s in sims), 2),
            'breadth': sims[0].breadth if sims else 'none',
        })
    return {'param': req.param, 'results': out}


def _restate(draft, param: str, value: float) -> str:
    """Rewrite the sentence with a new threshold, so the sweep goes back through the compiler."""
    if param == 'hours':
        return re.sub(r'\d+(?:\.\d+)?\s*(hours?|hrs?|h)\b', f'{value:g} hours', draft.english, count=1, flags=re.IGNORECASE)
    if param == 'days':
        return re.sub(r'\d+(?:\.\d+)?\s*(days?|d)\b', f'{value:g} days', draft.english, count=1, flags=re.IGNORECASE)
    return draft.english


@router.post('', status_code=201)
def add_rule(req: CreateRuleRequest, inventory: InventoryStore = Depends(get_inventory),
             session: Session = Depends(get_session)):
    """Store a rule — only if its policy passes the verifier for the stated intent."""
    policy_yaml, intent = req.policy_yaml, req.intent
    if policy_yaml is None:
        result = compile_rule(req.english, inventory, settings.region, skip_clarify=True)
        if result['status'] != 'compiled':
            raise HTTPException(422, {'message': 'Ward could not compile that rule, so nothing was saved.',
                                      'result': result})
        policy_yaml, intent = result['yaml'], TypeAdapter(Intent).validate_python(result['intent'])

    try:
        rule = create_rule(session, req.english, policy_yaml, intent, settings.region)
    except VerificationFailed as e:
        raise HTTPException(422, {'message': 'Policy failed verification, so it was not saved.', 'report': e.report.model_dump()}) from e
    return rule_out(rule)


@router.patch('/{rule_id}')
def update_rule(rule_id: str, req: UpdateRuleRequest, session: Session = Depends(get_session)):
    rule = session.get(Rule, rule_id) or _missing(rule_id)
    rule.status = req.status
    session.commit()
    return rule_out(rule)


@router.delete('/{rule_id}', status_code=204)
def delete_rule(rule_id: str, session: Session = Depends(get_session)):
    rule = session.get(Rule, rule_id) or _missing(rule_id)
    session.delete(rule)
    session.commit()
    return Response(status_code=204)


def _missing(rule_id: str):
    raise HTTPException(404, f'No rule {rule_id}')
