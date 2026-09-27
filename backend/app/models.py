import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _id(prefix: str):
    return lambda: f'{prefix}_{uuid.uuid4().hex[:12]}'


class Account(Base):
    """A connected AWS account.

    Ward stores how to *assume a role* in the account, never credentials for it. The ExternalId is
    the one secret here — it, plus Ward's own principal, is what satisfies the customer's trust
    policy — so it is encrypted at rest (see app/crypto.py). The temporary credentials returned by
    sts:AssumeRole live in memory only and are never written to this table.
    """
    __tablename__ = 'accounts'

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id('acct'))
    label: Mapped[str] = mapped_column(String(128))
    owner_email: Mapped[str | None] = mapped_column(String(256))
    # Discovered from sts:GetCallerIdentity when the connection is verified, not typed by the user.
    aws_account_id: Mapped[str | None] = mapped_column(String(12))
    role_arn: Mapped[str | None] = mapped_column(String(2048))
    external_id_enc: Mapped[str] = mapped_column(Text)
    region: Mapped[str] = mapped_column(String(32))
    budget_inr: Mapped[float] = mapped_column(Float)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default='pending')  # pending | connected | error
    created_at: Mapped[datetime]
    connected_at: Mapped[datetime | None]
    last_sweep_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)


class Rule(Base):
    __tablename__ = 'rules'

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id('rule'))
    english: Mapped[str] = mapped_column(Text)
    policy_yaml: Mapped[str] = mapped_column(Text)
    intent: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default='active')  # active | paused
    verified: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime]

    watches: Mapped[list['Watch']] = relationship(back_populates='rule', cascade='all, delete-orphan')
    alerts: Mapped[list['Alert']] = relationship(back_populates='rule', cascade='all, delete-orphan')


class Watch(Base):
    """The state machine position of one resource under one rule (SRS §4.3)."""
    __tablename__ = 'watches'
    __table_args__ = (UniqueConstraint('rule_id', 'resource_id'),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey('rules.id', ondelete='CASCADE'))
    resource_id: Mapped[str] = mapped_column(String(128))
    resource_type: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(16))  # discovered | watched | warning | alert | snoozed | resolved
    since: Mapped[datetime]
    last_seen: Mapped[datetime]
    snoozed_until: Mapped[datetime | None]

    rule: Mapped[Rule] = relationship(back_populates='watches')


class Alert(Base):
    __tablename__ = 'alerts'

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id('alert'))
    rule_id: Mapped[str] = mapped_column(ForeignKey('rules.id', ondelete='CASCADE'))
    resource_id: Mapped[str] = mapped_column(String(128))
    resource_type: Mapped[str] = mapped_column(String(32))
    resource_name: Mapped[str | None] = mapped_column(String(256))
    level: Mapped[str] = mapped_column(String(16))  # warning | alert
    status: Mapped[str] = mapped_column(String(16), default='open')  # open | snoozed | resolved
    message: Mapped[str] = mapped_column(Text)
    cost_per_day: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime]
    resolved_at: Mapped[datetime | None]
    snoozed_until: Mapped[datetime | None]

    rule: Mapped[Rule] = relationship(back_populates='alerts')


class Notification(Base):
    """Every message Ward sent, or would have sent when no channel is configured."""
    __tablename__ = 'notifications'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    alert_id: Mapped[str | None] = mapped_column(ForeignKey('alerts.id', ondelete='SET NULL'))
    channel: Mapped[str] = mapped_column(String(16))  # telegram | log
    text: Mapped[str] = mapped_column(Text)
    delivered: Mapped[bool]
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime]


class Prediction(Base):
    """A month-end forecast, stored the day it was made so it can be graded later (SRS Phase 5)."""
    __tablename__ = 'predictions'
    __table_args__ = (UniqueConstraint('month', 'made_on'),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    month: Mapped[date] = mapped_column(Date)  # first day of the forecast month
    made_on: Mapped[date] = mapped_column(Date)
    predicted: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(32), default='linear-7d')
    actual: Mapped[float | None] = mapped_column(Float)
    error_pct: Mapped[float | None] = mapped_column(Float)
