"""The compile pipeline: English → (clarify) → policy → verify → simulate.

The order is the point. Nothing reaches the user as "compiled" until the verifier has run it against
fixtures generated from the *intent*, so a policy can never grade itself, and a failure is returned as
a result rather than an error — a rule Ward cannot build is an answer, not a crash (SRS §4.1).
"""
from datetime import datetime, timezone

from app.compiler import clarify
from app.compiler.base import Compiler, Draft
from app.compiler.templates import TemplateCompiler
from app.inventory.store import InventoryStore
from app.simulator.dryrun import simulate_now
from app.verifier import fixtures as fixture_gen
from app.verifier.report import VerifyReport
from app.verifier.runner import verify

MAX_ATTEMPTS = 3  # SRS §4.1: three tries, then flag for human review


def compile_rule(english: str, inventory: InventoryStore, region: str, *, skip_clarify: bool = False,
                 compiler: Compiler | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    compiler = compiler or TemplateCompiler()
    snapshot = inventory.latest()

    if not skip_clarify:
        questions = clarify.questions_for(english, snapshot, now)
        if questions:
            return {'status': 'needs-clarification', 'english': english, 'questions': questions}

    draft = compiler.compile(english)
    if draft is None:
        return _failed(english, compiler, 'Ward could not map this sentence to a policy. Name a resource '
                                          'type and a limit — for example, “No RDS instance larger than db.t3.small”.')

    report = verify(draft.policy_yaml, fixture_gen.generate(draft.intent, now), region)
    if not report.passed:
        return _failed(english, compiler, report.error or _misses(report), report)

    return {
        'status': 'compiled',
        'english': english,
        'kind': draft.kind,
        'params': draft.params,
        'yaml': draft.policy_yaml,
        'intent': draft.intent.model_dump(),
        'explanation': draft.explanation,
        'assumptions': draft.assumptions,
        'compiler': compiler.name,
        'verifier': _verifier_out(report, attempts=1),
        'simulation': {
            'inventoryAsOf': snapshot.taken_at,
            'policies': [p.model_dump() for p in simulate_now(draft.policy_yaml, snapshot, region)],
        },
    }


def draft_for(english: str, compiler: Compiler | None = None) -> Draft | None:
    return (compiler or TemplateCompiler()).compile(english)


def _failed(english: str, compiler: Compiler, error: str, report: VerifyReport | None = None) -> dict:
    return {
        'status': 'failed',
        'english': english,
        'compiler': compiler.name,
        'verifier': _verifier_out(report, attempts=MAX_ATTEMPTS, error=error),
    }


def _verifier_out(report: VerifyReport | None, attempts: int, error: str | None = None) -> dict:
    return {
        'passed': bool(report and report.passed),
        'attempts': attempts,
        'durationMs': report.duration_ms if report else 0.0,
        'error': error or (report.error if report else None),
        'fixtures': [
            {'id': f.id, 'kind': f.kind, 'description': f.description, 'expected': f.expected, 'actual': f.actual}
            for f in (report.fixtures if report else [])
        ],
        'rates': report.rates.model_dump() if report else None,
    }


def _misses(report: VerifyReport) -> str:
    """Name what the policy got wrong, rather than only that it failed."""
    missed = [f.id for f in report.fixtures if f.expected and f.actual is False]
    false_alarms = [f.id for f in report.fixtures if not f.expected and f.actual is True]
    parts = []
    if missed:
        parts.append(f"missed {', '.join(missed)}")
    if false_alarms:
        parts.append(f"wrongly flagged {', '.join(false_alarms)}")
    return 'Policy failed its fixtures: ' + ('; '.join(parts) or 'no fixture matched as expected') + '.'
