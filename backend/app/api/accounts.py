"""Connecting an AWS account: issue an ExternalId, hand over a template, verify the role works."""
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_connection, get_session, reset_inventory
from app.aws import onboarding
from app.aws.connection import AwsConnection, ConnectionError_
from app.config import settings
from app.crypto import encrypt
from app.models import Account

router = APIRouter(prefix='/accounts', tags=['accounts'])


class CreateAccountRequest(BaseModel):
    label: str = Field(min_length=1, max_length=128, examples=['Vansh — lab account'])
    owner_email: str | None = Field(default=None, max_length=256)
    region: str | None = None
    budget_inr: float | None = Field(default=None, gt=0)
    telegram_chat_id: str | None = None


class ConnectRequest(BaseModel):
    role_arn: str = Field(pattern=r'^arn:aws[\w-]*:iam::\d{12}:role/.+', examples=['arn:aws:iam::123456789012:role/WardReadOnly'])


class UpdateAccountRequest(BaseModel):
    label: str | None = None
    budget_inr: float | None = Field(default=None, gt=0)
    telegram_chat_id: str | None = None
    region: str | None = None


def account_out(a: Account) -> dict:
    """The ExternalId is deliberately absent: it is returned once, by the onboarding endpoint."""
    return {
        'id': a.id,
        'label': a.label,
        'ownerEmail': a.owner_email,
        'awsAccountId': a.aws_account_id,
        'roleArn': a.role_arn,
        'region': a.region,
        'budgetInr': a.budget_inr,
        'telegramChatId': a.telegram_chat_id,
        'status': a.status,
        'createdAt': a.created_at,
        'connectedAt': a.connected_at,
        'lastSweepAt': a.last_sweep_at,
        'lastError': a.last_error,
    }


@router.get('/setup')
def setup_status(aws: AwsConnection = Depends(get_connection)):
    """Is Ward itself ready to connect anyone? Step zero, checked before the user deploys anything.

    Two things must be true: the backend has AWS credentials of its own, and there is a principal
    for customer roles to trust — WARD_PRINCIPAL, or failing that the identity those credentials are.
    """
    try:
        identity = aws.identity()
        error = None
    except ConnectionError_ as exc:
        identity, error = None, str(exc)
    principal = aws.principal(settings.ward_principal) if identity or settings.ward_principal else None
    return {
        'ready': identity is not None and principal is not None,
        'identity': identity,
        'principal': principal,
        'principalSource': 'WARD_PRINCIPAL' if settings.ward_principal else ('detected' if principal else None),
        'error': error,
    }


@router.get('')
def list_accounts(session: Session = Depends(get_session)):
    accounts = session.scalars(select(Account).order_by(Account.created_at)).all()
    return {'items': [account_out(a) for a in accounts]}


@router.post('', status_code=201)
def create_account(req: CreateAccountRequest, session: Session = Depends(get_session)):
    """Step 1. Ward issues the ExternalId; the user never invents it."""
    account = Account(
        label=req.label,
        owner_email=req.owner_email,
        region=req.region or settings.region,
        budget_inr=req.budget_inr or settings.budget_inr,
        telegram_chat_id=req.telegram_chat_id,
        external_id_enc=encrypt(secrets.token_urlsafe(24)),
        status='pending',
        created_at=datetime.now(timezone.utc),
    )
    session.add(account)
    session.commit()
    return account_out(account)


@router.get('/{account_id}/onboarding')
def onboarding_instructions(account_id: str, session: Session = Depends(get_session),
                            aws: AwsConnection = Depends(get_connection)):
    """Step 2. The template to deploy, with this account's ExternalId already in it."""
    from app.crypto import decrypt

    account = _get(session, account_id)
    principal = aws.principal(settings.ward_principal)
    return {'account': account_out(account), **onboarding.instructions(decrypt(account.external_id_enc), principal)}


@router.post('/{account_id}/connect')
def connect_account(account_id: str, req: ConnectRequest, session: Session = Depends(get_session),
                    aws: AwsConnection = Depends(get_connection)):
    """Step 3. Prove the role is assumable before trusting it, and record which account it landed in."""
    from app.crypto import decrypt

    account = _get(session, account_id)
    try:
        aws_account_id = aws.verify(req.role_arn, decrypt(account.external_id_enc), account.region)
    except ConnectionError_ as exc:
        account.status = 'error'
        account.last_error = str(exc)
        session.commit()
        raise HTTPException(400, str(exc)) from exc

    account.role_arn = req.role_arn
    account.aws_account_id = aws_account_id
    account.status = 'connected'
    account.connected_at = datetime.now(timezone.utc)
    account.last_error = None
    session.commit()
    aws.forget(account.id)
    reset_inventory()  # the next sweep should read this account, not the sample one
    return account_out(account)


@router.patch('/{account_id}')
def update_account(account_id: str, req: UpdateAccountRequest, session: Session = Depends(get_session)):
    account = _get(session, account_id)
    for field_name, value in req.model_dump(exclude_none=True).items():
        setattr(account, field_name, value)
    session.commit()
    return account_out(account)


@router.delete('/{account_id}', status_code=204)
def disconnect_account(account_id: str, session: Session = Depends(get_session),
                       aws: AwsConnection = Depends(get_connection)):
    account = _get(session, account_id)
    session.delete(account)
    session.commit()
    aws.forget(account_id)
    reset_inventory()


def _get(session: Session, account_id: str) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(404, f'No account {account_id}')
    return account
