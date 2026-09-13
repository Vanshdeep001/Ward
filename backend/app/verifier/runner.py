"""verify(policy_yaml, fixtures) -> VerifyReport. No AWS calls; typically well under a second."""
from time import perf_counter

from app.engine.custodian import PolicyError, load_policies, resource_id, run_filters
from app.verifier.fixtures import Fixture
from app.verifier.report import FixtureResult, Rates, VerifyReport


def verify(policy_yaml: str, fixtures: list[Fixture], region: str = 'ap-south-1') -> VerifyReport:
    started = perf_counter()
    expected = sorted(resource_id(f.resource_type, f.resource) for f in fixtures if f.expected)

    def done(flagged: set[str] | None, error: str | None) -> VerifyReport:
        results = []
        for f in fixtures:
            rid = resource_id(f.resource_type, f.resource)
            actual = None if flagged is None else rid in flagged
            results.append(FixtureResult(
                id=f.id, kind=f.kind, description=f.description, resource_id=rid,
                expected=f.expected, actual=actual, correct=None if actual is None else actual == f.expected,
            ))
        passed = error is None and all(r.correct for r in results)
        return VerifyReport(
            passed=passed,
            expected=expected,
            actual=sorted(flagged or []),
            error=error,
            fixtures=results,
            rates=_rates(results),
            duration_ms=round((perf_counter() - started) * 1000, 1),
        )

    if not fixtures:
        return done(None, 'No fixtures to verify against.')

    try:
        policies = load_policies(policy_yaml, region)
    except PolicyError as e:
        return done(None, str(e))

    fixture_types = {f.resource_type for f in fixtures}
    relevant = [p for p in policies if p.resource_type in fixture_types]
    if not relevant:
        targets = ', '.join(sorted({p.resource_type for p in policies}))
        return done(None, f"Policy targets {targets}, but this rule is about {', '.join(sorted(fixture_types))}.")

    flagged: set[str] = set()
    try:
        for policy in relevant:
            candidates = [f.resource for f in fixtures if f.resource_type == policy.resource_type]
            matched, _ = run_filters(policy, candidates)
            flagged.update(resource_id(policy.resource_type, r) for r in matched)
    except Exception as e:  # a policy that crashes Custodian on realistic resources is a failed policy, not a server error
        return done(None, f'Policy raised {type(e).__name__} while evaluating fixtures: {e}')

    return done(flagged, None)


def _rates(results: list[FixtureResult]) -> Rates:
    def rate(kind: str) -> float | None:
        group = [r for r in results if r.kind == kind and r.correct is not None]
        return round(sum(r.correct for r in group) / len(group), 3) if group else None

    return Rates(positive_pass=rate('positive'), negative_pass=rate('negative'), edge_pass=rate('edge'))
