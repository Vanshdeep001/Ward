"""Asking rather than guessing (SRS §20).

A vague word is not an error — it is a question Ward has not asked yet. Each option carries how many
of *your* resources it would match right now, so the choice is made against consequences instead of
wording. Nothing is resolved silently: the rewritten sentence goes back to the user before it compiles.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.inventory.pricing import hourly_cost
from app.inventory.store import Snapshot

GPU_FAMILIES = ('p2', 'p3', 'p4', 'p5', 'g4', 'g4dn', 'g5', 'g6', 'inf1', 'inf2')


@dataclass(frozen=True)
class Option:
    label: str
    value: str  # the phrase that replaces the vague term in the rewritten sentence
    test: object  # (resource, now) -> bool


@dataclass(frozen=True)
class VagueTerm:
    term: str
    question: str
    default_index: int
    options: tuple[Option, ...]


def _running(r: dict) -> bool:
    return r.get('State', {}).get('Name') == 'running'


def _runtime_hours(r: dict, now: datetime) -> float:
    launched = r.get('LaunchTime')
    return (now - launched).total_seconds() / 3600 if launched else 0.0


def _is_gpu(r: dict) -> bool:
    return str(r.get('InstanceType', '')).split('.')[0] in GPU_FAMILIES


def _costs_more_than(limit: float):
    return lambda r, now: _running(r) and (hourly_cost('aws.ec2', r) or 0) * 24 > limit


VAGUE = (
    VagueTerm(
        term='expensive',
        question='"expensive" means',
        default_index=0,
        options=(
            Option('costs more than ₹50/day', 'costing more than ₹50/day', _costs_more_than(50)),
            Option('costs more than ₹200/day', 'costing more than ₹200/day', _costs_more_than(200)),
            Option('any GPU instance', 'GPU', lambda r, now: _is_gpu(r) and _running(r)),
        ),
    ),
    VagueTerm(
        term='too long',
        question='"too long" means',
        default_index=1,
        options=(
            Option('more than 2 hours', 'more than 2 hours', lambda r, now: _runtime_hours(r, now) > 2),
            Option('more than 6 hours', 'more than 6 hours', lambda r, now: _runtime_hours(r, now) > 6),
            Option('more than 24 hours', 'more than 24 hours', lambda r, now: _runtime_hours(r, now) > 24),
        ),
    ),
)


def questions_for(english: str, snapshot: Snapshot, now: datetime | None = None) -> list[dict]:
    """Every vague term in the sentence, each option counted against the current inventory."""
    now = now or datetime.now(timezone.utc)
    text = english.lower()
    instances = snapshot.of_type('aws.ec2')
    out = []
    for vague in VAGUE:
        if vague.term not in text:
            continue
        out.append({
            'term': vague.term,
            'question': vague.question,
            'defaultIndex': vague.default_index,
            'options': [
                {
                    'label': o.label,
                    'value': o.value,
                    'matches': sum(1 for r in instances if o.test(r, now)),
                }
                for o in vague.options
            ],
        })
    return out


def apply_choices(english: str, choices: dict[str, str]) -> str:
    """Rewrite the sentence with the chosen phrases, so the user sees exactly what will be compiled."""
    rewritten = english
    for term, value in choices.items():
        if term not in rewritten.lower():
            continue
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        # "GPU" is a noun where the vague word was an adjective: "anything GPU" reads wrong.
        replacement = 'GPU instance' if value == 'GPU' and term == 'expensive' else value
        rewritten = pattern.sub(replacement, rewritten, count=1)
    return rewritten


def unresolved(english: str) -> list[str]:
    text = english.lower()
    return [v.term for v in VAGUE if v.term in text]


__all__ = ['questions_for', 'apply_choices', 'unresolved', 'VAGUE']
