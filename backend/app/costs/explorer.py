"""Real spend for a connected account, from Cost Explorer (SRS §14).

Pricing what the inventory shows is right for the demo account, but for a real one it only knows
what Ward has seen since it connected — a day's worth on the first day. Cost Explorer knows the whole
bill. The role already grants ce:GetCostAndUsage (SRS §7), so this reads it through the same
assumed-role session as everything else.

Two costs of calling it are handled here: each request is billed ($0.01), and the data only changes a
few times a day — so results are cached per account for three hours.
"""
import time
from datetime import date, datetime, timedelta, timezone

CACHE_SECONDS = 3 * 3600

_cache: dict[str, tuple[float, list[dict], str]] = {}


class CostExplorerUnavailable(Exception):
    """Cost Explorer could not answer — not enabled yet, no permission, or no data. Carries why."""


def daily_spend(session, account_id: str, *, days: int = 60, usd_to_inr: float, today: date | None = None) -> tuple[list[dict], str]:
    """Daily unblended cost in rupees, oldest first, and the unit the bill was actually in."""
    key = f'{account_id}:{days}'
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1], hit[2]

    today = today or datetime.now(timezone.utc).date()
    end = today + timedelta(days=1)  # Cost Explorer's End is exclusive; include today's partial day
    start = end - timedelta(days=days)
    ce = session.client('ce', region_name='us-east-1')  # Cost Explorer only answers in us-east-1

    rows, unit, token = [], 'USD', None
    try:
        while True:
            kwargs = {'TimePeriod': {'Start': start.isoformat(), 'End': end.isoformat()},
                      'Granularity': 'DAILY', 'Metrics': ['UnblendedCost']}
            if token:
                kwargs['NextPageToken'] = token
            resp = ce.get_cost_and_usage(**kwargs)
            for period in resp['ResultsByTime']:
                amount = period['Total']['UnblendedCost']
                unit = amount['Unit']
                inr = float(amount['Amount']) * (usd_to_inr if unit == 'USD' else 1.0)
                day = date.fromisoformat(period['TimePeriod']['Start'])
                rows.append({'date': datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
                             'amount': round(inr, 2)})
            token = resp.get('NextPageToken')
            if not token:
                break
    except Exception as exc:
        raise CostExplorerUnavailable(_why(exc)) from exc

    _cache[key] = (time.monotonic(), rows, unit)
    return rows, unit


def forget(account_id: str) -> None:
    for key in [k for k in _cache if k.startswith(f'{account_id}:')]:
        del _cache[key]


def _why(exc: Exception) -> str:
    text = str(exc)
    if 'DataUnavailable' in text or 'not enabled' in text.lower():
        return 'Cost Explorer is not enabled on this account yet — enable it in Billing, and data arrives within 24 hours.'
    if 'AccessDenied' in text or 'not authorized' in text:
        return 'The WardReadOnly role cannot call ce:GetCostAndUsage — redeploy the stack from the latest template.'
    return f'Cost Explorer did not answer ({type(exc).__name__}).'
