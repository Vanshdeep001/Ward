"""Copilot: questions answered from this account's own data (SRS §19).

Deliberately not a language model. Every answer here is computed from the inventory, the rules and the
alerts, so it cannot invent a number — and intent routing is the part a fine-tuned model replaces
later, leaving these handlers as the tools it calls.

The most important branch is REFUSE: Ward holds read-only credentials, so when it is asked to change
something it says so and hands over the exact command instead of pretending it acted.
"""
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_inventory, get_session
from app.compiler.service import compile_rule
from app.config import settings
from app.costs import detective, spend
from app.engine.custodian import resource_id
from app.guardian import findings as finder
from app.inventory.pricing import hourly_cost
from app.inventory.store import InventoryStore, Snapshot
from app.models import Alert, Rule
from app.simulator.dryrun import summarise

router = APIRouter(tags=['copilot'])

WRITE = re.compile(r'\b(delete|terminate|stop|kill|shut ?down|remove|resize|restart)\b', re.I)
MAKE_RULE = re.compile(r'\b(create|make|add|set ?up|write)\b.*\b(rule|guardrail)\b|prevent this|again', re.I)
COST = re.compile(r'\b(cost|costing|spend|spending|bill|expensive|burn|budget)\b', re.I)
WHY = re.compile(r'\b(why|increase|increased|went up|rose|changed|jump)\b', re.I)
RUNNING = re.compile(r'\b(running|up|on right now|what.?s on)\b', re.I)
RISK = re.compile(r'\b(risk|risky|security|exposed|public|insecure|wrong|problem)\b', re.I)
RULES = re.compile(r'\b(rules?|guardrails?|watching)\b', re.I)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    state: dict = Field(default_factory=dict)


def _reply(intent: str, text: str, state: dict, **extra) -> dict:
    return {'message': {'id': str(uuid.uuid4()), 'role': 'ward', 'intent': intent, 'text': text, **extra}, 'state': state}


@router.post('/chat')
def chat(req: ChatRequest, inventory: InventoryStore = Depends(get_inventory), session: Session = Depends(get_session)):
    text = req.message
    snapshot = inventory.latest()
    now = datetime.now(timezone.utc)
    state = dict(req.state)
    referent = _find_resource(snapshot, text) or _by_id(snapshot, state.get('referentId'))

    if WRITE.search(text):
        return _refuse(text, referent, state)

    if MAKE_RULE.search(text):
        return _draft_rule(referent, inventory, state)

    if WHY.search(text) and COST.search(text):
        return _explain_bill(inventory, state)

    if COST.search(text):
        return _spend_summary(inventory, snapshot, state, now)

    if RISK.search(text):
        return _risks(snapshot, state)

    if RUNNING.search(text):
        return _running(snapshot, state, now)

    if RULES.search(text):
        return _rules(session, state)

    return _reply(
        'ANSWER',
        'Ask me about spend (“what is costing the most?”), a change (“why did my bill go up?”), risk '
        '(“what is exposed?”), or say “create a rule for that” after we talk about a resource.',
        state,
    )


def _refuse(text: str, referent, state) -> dict:
    """Read-only is a design decision, so this is an explanation, not an apology."""
    target = referent['id'] if referent else '<instance-id>'
    return _reply(
        'REFUSE',
        'Ward has read-only access to your account by design — it can warn you, but it cannot change '
        'anything. Here is the command that does it:',
        state,
        command=f'aws ec2 stop-instances --instance-ids {target} --region {settings.region}',
        consoleUrl=f'https://console.aws.amazon.com/ec2/home?region={settings.region}#Instances:',
    )


def _draft_rule(referent, inventory, state) -> dict:
    if referent is None:
        return _reply('ACT', 'Which resource should the rule be about? Ask me about one first — for example '
                             '“what is costing me the most?” — then say “create a rule for that”.', state)

    english = _rule_for(referent)
    result = compile_rule(english, inventory, settings.region, skip_clarify=True)
    if result['status'] != 'compiled':
        return _reply('ACT', f'I could not build a verified policy for “{english}” yet.', state)

    matched = sum(len(p['matched']) for p in result['simulation']['policies'])
    return _reply(
        'ACT',
        f'“{english}” — verified, and it matches {matched} resource{"s" if matched != 1 else ""} in your account right now.',
        state,
        draft={'english': english, 'yaml': result['yaml'], 'explanation': result['explanation'],
               'assumptions': result['assumptions'], 'matched': matched},
    )


def _spend_summary(inventory, snapshot, state, now) -> dict:
    daily = spend.daily_spend(inventory)
    projection = spend.project(daily)
    ranked = sorted(
        ((rtype, r, (hourly_cost(rtype, r) or 0) * 24) for rtype, rs in snapshot.resources.items() for r in rs),
        key=lambda x: x[2], reverse=True,
    )
    top = [(rtype, r, cost) for rtype, r, cost in ranked if cost > 0][:3]
    lines = [
        {'id': resource_id(rtype, r), 'name': summarise(rtype, r, now).name, 'costPerDay': round(cost, 2)}
        for rtype, r, cost in top
    ]
    state['referentId'] = lines[0]['id'] if lines else None
    biggest = f"{lines[0]['name'] or lines[0]['id']} at ₹{lines[0]['costPerDay']:,.0f}/day" if lines else 'nothing'
    return _reply(
        'ANSWER',
        f'You are spending about ₹{projection.burn_per_day:,.0f} a day, on track for ₹{projection.projected_month_end:,.0f} '
        f'this month against a ₹{settings.budget_inr:,.0f} budget. The biggest single line is {biggest}.',
        state,
        table=lines,
    )


def _explain_bill(inventory, state) -> dict:
    result = detective.investigate(inventory, window_days=7)
    if not result['changes']:
        return _reply('ANSWER', 'Nothing moved much in the last 7 days — spend is flat.', state)
    top = result['changes'][0]
    state['referentId'] = top['id']
    direction = 'up' if result['delta'] > 0 else 'down'
    return _reply(
        'ANSWER',
        f'Spend went {direction} by ₹{abs(result["delta"]):,.0f}/day versus the previous 7 days. The biggest single '
        f'mover is {top["name"] or top["id"]}: ₹{top["before"]:,.0f} → ₹{top["after"]:,.0f} per day. {top["reason"]}',
        state,
        table=[{'id': c['id'], 'name': c['name'], 'costPerDay': c['delta']} for c in result['changes'][:3]],
        suggestedRule=result['suggestedRule'],
    )


def _risks(snapshot, state) -> dict:
    found = finder.find_all(snapshot)
    urgent = [f for f in found if f['severity'] == 'urgent'] or found
    if not found:
        return _reply('ANSWER', 'Nothing is exposed right now — no public databases, no open SSH.', state)
    top = urgent[0]
    state['referentId'] = top['resourceIds'][0] if top['resourceIds'] else None
    return _reply('ANSWER', f'{top["title"]}. {top["detail"]}', state, command=top['fix'],
                  suggestedRule={'english': top['suggestedRule'], 'because': top['title']})


def _running(snapshot, state, now) -> dict:
    instances = [r for r in snapshot.of_type('aws.ec2') if r.get('State', {}).get('Name') == 'running']
    lines = [
        {'id': r['InstanceId'], 'name': summarise('aws.ec2', r, now).name,
         'costPerDay': round((hourly_cost('aws.ec2', r) or 0) * 24, 2)}
        for r in sorted(instances, key=lambda r: hourly_cost('aws.ec2', r) or 0, reverse=True)[:5]
    ]
    return _reply('ANSWER', f'{len(instances)} instances are running right now. The most expensive:', state, table=lines)


def _rules(session, state) -> dict:
    rules = session.scalars(select(Rule).where(Rule.status == 'active')).all()
    open_alerts = session.scalars(select(Alert).where(Alert.status == 'open')).all()
    listed = '\n'.join(f'• {r.english}' for r in rules[:6])
    return _reply(
        'ANSWER',
        f'{len(rules)} guardrails are active and {len(open_alerts)} alerts are open.\n{listed}',
        state,
    )


def _rule_for(referent) -> str:
    rtype, r = referent['type'], referent['resource']
    if rtype == 'aws.ebs':
        return 'Flag EBS volumes unattached for more than 7 days'
    if rtype == 'aws.rds':
        return 'No database may be publicly accessible'
    if str(r.get('InstanceType', '')).split('.')[0] in ('p2', 'p3', 'p4', 'g4', 'g4dn', 'g5', 'inf1'):
        return 'No GPU instance runs more than 6 hours'
    return 'Nothing runs longer than 6 hours unattended'


def _find_resource(snapshot: Snapshot, text: str) -> dict | None:
    """Match a resource the user named, by id or by Name tag."""
    lowered = text.lower()
    for rtype, resources in snapshot.resources.items():
        for r in resources:
            rid = resource_id(rtype, r)
            name = {t['Key']: t['Value'] for t in r.get('Tags', [])}.get('Name')
            if rid.lower() in lowered or (name and name.lower() in lowered):
                return {'id': rid, 'type': rtype, 'resource': r}
    return None


def _by_id(snapshot: Snapshot, rid: str | None) -> dict | None:
    if not rid:
        return None
    for rtype, resources in snapshot.resources.items():
        for r in resources:
            if resource_id(rtype, r) == rid:
                return {'id': rid, 'type': rtype, 'resource': r}
    return None
