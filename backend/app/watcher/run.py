"""Running a sweep against the account Ward is watching, and recording that it happened.

Both the background loop and `POST /watcher/sweep` come through here, so the connected account's
`last_sweep_at` and `last_error` are always true — a sweep that fails (an expired or deleted role,
say) is written down where the user can see it, rather than only in a log.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.inventory.store import InventoryStore
from app.models import Account
from app.notify.channels import Channel
from app.watcher.evaluator import SweepResult, sweep


def active_account(session: Session) -> Account | None:
    """The account the watcher sweeps. One connected account for now; multi-tenant scoping is next."""
    return session.scalars(
        select(Account).where(Account.status == 'connected').order_by(Account.connected_at).limit(1)
    ).first()


def run_sweep(session: Session, inventory: InventoryStore, channel: Channel, now: datetime, region: str) -> SweepResult:
    account = active_account(session)
    try:
        result = sweep(session, inventory.latest(), channel, now, region)
    except Exception as exc:
        if account is not None:
            account.last_error = f'Sweep failed: {exc}'
            session.commit()
        raise

    if account is not None:
        account.last_sweep_at = now
        account.last_error = '; '.join(result.errors) or None
        session.commit()
    return result
