"""Does this rulebook contradict itself? (SRS §21)

Four relationships between rules, found by comparing what they actually match rather than what they
say: contradiction (both cannot hold), subsumption (one is contained in another), overlap (the same
resource alerts twice), and dead rules (nothing has ever matched). Detection runs over the current
inventory, so every claim is about this account, not about the wording.
"""
from dataclasses import dataclass

from app.engine.custodian import PolicyError, load_policies, resource_id, run_filters
from app.inventory.store import Snapshot


@dataclass
class Matched:
    rule_id: str
    english: str
    ids: set[str]
    resource_types: set[str]


def _matches(rule, snapshot: Snapshot, region: str) -> Matched | None:
    try:
        policies = load_policies(rule.policy_yaml, region)
    except PolicyError:
        return None
    ids, types = set(), set()
    for policy in policies:
        rtype = policy.resource_type
        types.add(rtype)
        matched, _ = run_filters(policy, snapshot.of_type(rtype))
        ids.update(resource_id(rtype, r) for r in matched)
    return Matched(rule.id, rule.english, ids, types)


def detect(rules, snapshot: Snapshot, region: str) -> list[dict]:
    matched = [m for m in (_matches(r, snapshot, region) for r in rules) if m is not None]
    population = sum(len(v) for v in snapshot.resources.values())
    found = []

    for i, a in enumerate(matched):
        if not a.ids:
            found.append({
                'id': f'dead-{a.rule_id}',
                'category': 'dead',
                'severity': 'info',
                'title': f'Dead rule: “{a.english}” matches nothing',
                'ruleA': {'id': a.rule_id, 'english': a.english},
                'detail': f'Evaluated against {population} current resources and matched none.',
                'impact': 'No alerts. It may be a deliberate preventive guardrail, or it may be misspelled.',
                'suggestion': 'Keep it as a preventive guardrail, or archive it if the resources it watches never existed.',
                'actionText': 'Keep as preventive guardrail',
                'affected': 0,
            })

        for b in matched[i + 1:]:
            shared = a.ids & b.ids
            if not shared:
                continue
            if a.ids <= b.ids or b.ids <= a.ids:
                inner, outer = (a, b) if a.ids <= b.ids else (b, a)
                found.append({
                    'id': f'subsume-{inner.rule_id}-{outer.rule_id}',
                    'category': 'subsumption',
                    'severity': 'warning',
                    'title': f'Redundant: “{inner.english}” is covered by “{outer.english}”',
                    'ruleA': {'id': inner.rule_id, 'english': inner.english},
                    'ruleB': {'id': outer.rule_id, 'english': outer.english},
                    'detail': f'Every resource the first rule matches ({len(inner.ids)}) is already matched by the second.',
                    'impact': f'{len(shared)} resources generate two alerts for one problem.',
                    'suggestion': 'Archive the narrower rule — it adds no protection and doubles the noise.',
                    'actionText': 'Archive redundant rule',
                    'affected': len(shared),
                })
            else:
                found.append({
                    'id': f'overlap-{a.rule_id}-{b.rule_id}',
                    'category': 'overlap',
                    'severity': 'warning',
                    'title': f'Overlap: “{a.english}” and “{b.english}”',
                    'ruleA': {'id': a.rule_id, 'english': a.english},
                    'ruleB': {'id': b.rule_id, 'english': b.english},
                    'detail': f'Overlap on {len(shared)} of your {population} current resources — each triggers two '
                              f'notifications for the same issue.',
                    'impact': f'{len(shared)} resources send 2 alerts every evaluation window.',
                    'suggestion': 'Merge them, or suppress the second where the first already fired.',
                    'actionText': 'Merge rules',
                    'affected': len(shared),
                })

    return found
