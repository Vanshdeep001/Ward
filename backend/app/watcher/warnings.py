"""Derive an "approaching the limit" policy from a rule's policy.

Age thresholds are scaled down (6 hours -> 4.5 hours at 75%), so a resource matching the variant but not the
original is getting close. Policies with no age threshold have no warning stage and go straight to Alert.
"""
import copy

import yaml

WARN_AT = 0.75


def warning_variant(policy_yaml: str, ratio: float = WARN_AT) -> str | None:
    data = yaml.safe_load(policy_yaml)
    scaled = False

    def scale(filters):
        nonlocal scaled
        for f in filters or []:
            if not isinstance(f, dict):
                continue
            for op in ('or', 'and', 'not'):
                if op in f:
                    scale(f[op])
            if f.get('type') == 'instance-age' and f.get('op', 'greater-than') in ('greater-than', 'gt', 'gte', 'ge'):
                for unit in ('hours', 'days', 'minutes'):
                    if isinstance(f.get(unit), (int, float)):
                        f[unit] = round(f[unit] * ratio, 3)
                        scaled = True
            if f.get('type') == 'value' and f.get('value_type') == 'age' and f.get('op') in ('greater-than', 'gt', 'gte', 'ge'):
                if isinstance(f.get('value'), (int, float)):
                    f['value'] = round(f['value'] * ratio, 3)
                    scaled = True

    variant = copy.deepcopy(data)
    for p in variant.get('policies', []):
        p['name'] = f"{p['name']}-warning"
        scale(p.get('filters'))
    return yaml.safe_dump(variant, sort_keys=False) if scaled else None
