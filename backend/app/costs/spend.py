"""Daily spend, the month-end projection, and how Ward earned its keep (SRS §14, §17).

Spend is derived from the inventory rather than Cost Explorer: every snapshot prices what was running
at that moment, so the demo account and a real account answer the same question the same way. A live
Cost Explorer feed replaces `daily_spend` without touching anything downstream.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.inventory.pricing import hourly_cost
from app.inventory.store import InventoryStore, Snapshot

# What running Ward costs the user per month — subtracted from savings so the figure is net (SRS §17.4).
WARD_OWN_COST_INR = 340.0


def snapshot_cost_per_hour(snapshot: Snapshot) -> float:
    return sum(
        hourly_cost(rtype, r) or 0.0
        for rtype, resources in snapshot.resources.items()
        for r in resources
    )


def daily_spend(inventory: InventoryStore, days: int = 60) -> list[dict]:
    """One row per day: the mean hourly cost across that day's snapshots, times 24."""
    snapshots = inventory.history(days)
    by_day: dict[date, list[float]] = {}
    for snap in snapshots:
        by_day.setdefault(snap.taken_at.date(), []).append(snapshot_cost_per_hour(snap))

    return [
        {'date': datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).isoformat(),
         'amount': round(sum(rates) / len(rates) * 24, 2)}
        for day, rates in sorted(by_day.items())
    ]


@dataclass
class Projection:
    month_to_date: float
    projected_month_end: float
    burn_per_day: float
    days_elapsed: int
    days_in_month: int


def project(daily: list[dict], today: date | None = None) -> Projection:
    """Month-to-date actuals, plus the rest of the month at the last seven days' burn rate."""
    today = today or datetime.now(timezone.utc).date()
    days_in_month = (date(today.year + today.month // 12, today.month % 12 + 1, 1) - timedelta(days=1)).day

    this_month = [d for d in daily if _day(d).month == today.month and _day(d).year == today.year]
    month_to_date = sum(d['amount'] for d in this_month)

    recent = daily[-7:] or daily
    burn = sum(d['amount'] for d in recent) / len(recent) if recent else 0.0
    remaining = max(days_in_month - today.day, 0)

    return Projection(
        month_to_date=round(month_to_date, 2),
        projected_month_end=round(month_to_date + burn * remaining, 2),
        burn_per_day=round(burn, 2),
        days_elapsed=today.day,
        days_in_month=days_in_month,
    )


def _day(row: dict) -> date:
    return datetime.fromisoformat(row['date']).date()


# ─── Savings (SRS §17) ────────────────────────────────────────────────────────
# Ward cannot observe what *would* have happened, so every figure names its counterfactual and its
# exclusions. A number without a stated assumption is not a measurement.

COUNTERFACTUALS = {
    'next-morning': {
        'label': 'Next-morning (default)',
        'description': 'Assumes an un-alerted instance runs until 09:00 the following working day.',
        'factor': 1.0,
        'excluded_share': 0.17,
    },
    'conservative': {
        'label': 'Conservative',
        'description': 'Assumes an un-alerted instance would have run only 2 more hours.',
        'factor': 0.42,
        'excluded_share': 0.12,
    },
    'observed': {
        'label': 'Observed',
        'description': 'Uses this account’s own median unattended runtime, from resources no rule was watching.',
        'factor': 1.31,
        'excluded_share': 0.20,
    },
}


def savings(alerts, now: datetime | None = None, window_days: int = 30) -> dict:
    """Value attributed only to alerts a human acted on within the attribution window (SRS §17.3)."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    recent = [a for a in alerts if a.created_at >= cutoff]
    acted_on = [a for a in recent if a.resolved_at and a.resolved_at - a.created_at <= timedelta(hours=2)]

    # Hours saved per acted-on alert, under the default assumption: stopped now vs. stopped next morning.
    base = sum((a.cost_per_day or 0) / 24 * _hours_until_next_morning(a.created_at) for a in acted_on)

    models = {}
    for key, spec in COUNTERFACTUALS.items():
        avoided = round(base * spec['factor'], 2)
        models[key] = {
            'label': spec['label'],
            'description': spec['description'],
            'avoided': avoided,
            'hoursAvoided': round(avoided / max(_mean_hourly(acted_on), 1e-6), 1),
            'excluded': round(avoided * spec['excluded_share'], 2),
        }

    return {
        'avoided': models['next-morning']['avoided'],
        'alertsSent': len(recent),
        'actedOn': len(acted_on),
        'wardCost': WARD_OWN_COST_INR,
        'counterfactuals': models,
    }


def _hours_until_next_morning(at: datetime) -> float:
    """From when the alert fired to 09:00 the next day — the window the user would otherwise have slept through."""
    next_morning = (at + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    return max((next_morning - at).total_seconds() / 3600, 1.0)


def _mean_hourly(alerts) -> float:
    rates = [(a.cost_per_day or 0) / 24 for a in alerts if a.cost_per_day]
    return sum(rates) / len(rates) if rates else 0.0
