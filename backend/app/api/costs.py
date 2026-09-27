"""Spend, the month-end projection, prediction accuracy, and the Detective."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_connection, get_inventory, get_session
from app.aws.connection import AwsConnection, ConnectionError_
from app.config import settings
from app.costs import detective, explorer, spend
from app.watcher.run import active_account
from app.inventory.store import InventoryStore
from app.models import Alert, Prediction, Rule

router = APIRouter(prefix='/costs', tags=['costs'])


def _daily(inventory: InventoryStore, session: Session, aws: AwsConnection) -> dict:
    """Daily spend from the best source available, always saying which one it came from.

    A connected account reads Cost Explorer — the real bill. The demo account, or a connected one whose
    Cost Explorer can't answer, is priced from inventory snapshots, and the note says so rather than
    presenting a partial figure as the bill.
    """
    account = active_account(session)
    if account is None:
        return {'daily': spend.daily_spend(inventory), 'source': 'inventory', 'budget': settings.budget_inr,
                'note': 'Demo account — priced from inventory snapshots.'}
    try:
        daily, unit = explorer.daily_spend(aws.session(account), account.id, usd_to_inr=settings.usd_to_inr)
        note = (f'Cost Explorer, converted from USD at ₹{settings.usd_to_inr:g}/USD' if unit == 'USD'
                else f'Cost Explorer, billed in {unit}')
        return {'daily': daily, 'source': 'cost-explorer', 'budget': account.budget_inr, 'note': note}
    except (explorer.CostExplorerUnavailable, ConnectionError_) as exc:
        return {'daily': spend.daily_spend(inventory), 'source': 'inventory', 'budget': account.budget_inr,
                'note': f'{exc} Until then, priced from what Ward has seen since it connected.'}


@router.get('')
def costs(inventory: InventoryStore = Depends(get_inventory), session: Session = Depends(get_session),
          aws: AwsConnection = Depends(get_connection)):
    """The dashboard's headline: what you are spending, and where the month lands."""
    source = _daily(inventory, session, aws)
    projection = spend.project(source['daily'])
    alerts = session.scalars(select(Alert)).all()
    saved = spend.savings(alerts)
    saved['topRule'] = _top_rule(session, alerts)
    return {
        'budget': source['budget'],
        'daily': source['daily'],
        'monthToDate': projection.month_to_date,
        'projectedMonthEnd': projection.projected_month_end,
        'burnPerDay': projection.burn_per_day,
        'source': source['source'],
        'sourceNote': source['note'],
        'savings': saved,
    }


@router.get('/investigate')
def investigate(window: str = Query('7d', pattern=r'^\d{1,2}d$'),
                inventory: InventoryStore = Depends(get_inventory),
                session: Session = Depends(get_session)):
    alerts = session.scalars(select(Alert)).all()
    return detective.investigate(inventory, window_days=int(window.rstrip('d')), alerts=alerts)


@router.get('/predictions')
def predictions(inventory: InventoryStore = Depends(get_inventory), session: Session = Depends(get_session),
                aws: AwsConnection = Depends(get_connection)):
    """Forecasts Ward made, graded against what actually happened (SRS Phase 5).

    The current month is shown ungraded: a prediction is only honest once the month it describes is over.
    """
    projection = spend.project(_daily(inventory, session, aws)['daily'])
    today = datetime.now(timezone.utc).date()
    stored = session.scalars(select(Prediction).order_by(Prediction.month)).all()

    # One row per month, newest last — the shape the accuracy table reads. The current month carries
    # actual: null, because a forecast is only honest once the month it describes has ended.
    rows = [
        {
            'month': p.month.strftime('%b %Y'),
            'madeOn': p.made_on.isoformat(),
            'predicted': round(p.predicted, 2),
            'actual': p.actual,
            'method': p.method,
        }
        for p in stored if p.month.month != today.month or p.month.year != today.year
    ]
    rows.append({
        'month': today.strftime('%b %Y'),
        'madeOn': today.isoformat(),
        'predicted': projection.projected_month_end,
        'actual': None,
        'method': 'linear-7d',
    })
    return rows


def record_prediction(session: Session, projection: spend.Projection, today: date | None = None) -> Prediction | None:
    """Store today's forecast once per day, so accuracy can be graded later rather than claimed now."""
    today = today or datetime.now(timezone.utc).date()
    month = today.replace(day=1)
    existing = session.scalar(select(Prediction).where(Prediction.month == month, Prediction.made_on == today))
    if existing:
        return existing
    prediction = Prediction(month=month, made_on=today, predicted=projection.projected_month_end, method='linear-7d')
    session.add(prediction)
    _grade_finished_months(session, today)
    session.commit()
    return prediction


def _grade_finished_months(session: Session, today: date) -> None:
    """A month that has ended can be scored against its own final month-to-date figure."""
    this_month = today.replace(day=1)
    for p in session.scalars(select(Prediction).where(Prediction.month < this_month, Prediction.actual.is_(None))):
        final = session.scalar(
            select(Prediction.predicted)
            .where(Prediction.month == p.month)
            .order_by(Prediction.made_on.desc())
            .limit(1)
        )
        if final is None:
            continue
        p.actual = final
        p.error_pct = round((p.predicted - final) / final * 100, 1) if final else None


def _top_rule(session: Session, alerts) -> dict | None:
    """The rule that has prevented the most spend — by the cost of what it caught and got acted on."""
    by_rule: dict[str, float] = {}
    for a in alerts:
        if a.resolved_at and a.resolved_at - a.created_at <= timedelta(hours=2):
            by_rule[a.rule_id] = by_rule.get(a.rule_id, 0.0) + (a.cost_per_day or 0.0)
    if not by_rule:
        return None
    rule_id, total = max(by_rule.items(), key=lambda kv: kv[1])
    rule = session.get(Rule, rule_id)
    return {'id': rule_id, 'english': rule.english if rule else rule_id, 'savings30d': round(total, 2)}
