from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_channel, get_inventory, get_session
from app.config import settings
from app.inventory.store import InventoryStore
from app.models import Alert, Notification
from app.notify.channels import Channel
from app.watcher.evaluator import snooze
from app.watcher.run import run_sweep

router = APIRouter(tags=['watcher'])


@router.post('/watcher/sweep')
def sweep_now(session: Session = Depends(get_session), inventory: InventoryStore = Depends(get_inventory),
              channel: Channel = Depends(get_channel)):
    """Run one sweep now. The background loop does this every WARD_POLL_MINUTES."""
    result = run_sweep(session, inventory, channel, datetime.now(timezone.utc), settings.region)
    return asdict(result)


def alert_out(alert: Alert) -> dict:
    """The shape the frontend's Alerts and Dashboard pages read."""
    return {
        'id': alert.id,
        'ruleId': alert.rule_id,
        'resourceId': alert.resource_id,
        'level': alert.level,
        'status': alert.status,
        'message': alert.message,
        'at': alert.created_at.isoformat(),
        'resolvedAt': alert.resolved_at.isoformat() if alert.resolved_at else None,
        'snoozedUntil': alert.snoozed_until.isoformat() if alert.snoozed_until else None,
        'projectedMonthly': round(alert.cost_per_day * 30) if alert.cost_per_day else None,
        'resource': {'id': alert.resource_id, 'name': alert.resource_name, 'type': alert.resource_type},
        'rule': {'id': alert.rule_id, 'english': alert.rule.english},
    }


@router.get('/alerts')
def list_alerts(status: str | None = None, session: Session = Depends(get_session)):
    query = select(Alert).order_by(Alert.created_at.desc())
    if status:
        query = query.where(Alert.status == status)
    return [alert_out(a) for a in session.scalars(query)]


class SnoozeRequest(BaseModel):
    hours: float = Field(gt=0, le=24 * 14)


@router.post('/alerts/{alert_id}/snooze')
def snooze_alert(alert_id: str, req: SnoozeRequest, session: Session = Depends(get_session)):
    """The user says it's intentional: stay silent until the timer runs out."""
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, f'No alert {alert_id}')
    if alert.status == 'resolved':
        raise HTTPException(409, 'That alert is already resolved.')
    return alert_out(snooze(session, alert, req.hours, datetime.now(timezone.utc)))


@router.get('/notifications')
def list_notifications(limit: int = 50, session: Session = Depends(get_session)):
    rows = session.scalars(select(Notification).order_by(Notification.sent_at.desc()).limit(min(limit, 500)))
    return [
        {'id': n.id, 'alertId': n.alert_id, 'channel': n.channel, 'text': n.text, 'delivered': n.delivered,
         'error': n.error, 'sentAt': n.sent_at.isoformat()}
        for n in rows
    ]
