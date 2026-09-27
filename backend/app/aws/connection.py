"""Cross-account access (SRS §7).

Ward runs in its own AWS account and assumes a read-only role in each connected account. Users hand
over a role ARN, never keys: the credentials this module produces are temporary, held in memory, and
refreshed before they expire. A database breach therefore yields a role ARN and an account number,
neither of which is usable without Ward's own principal.
"""
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.crypto import decrypt
from app.models import Account

log = logging.getLogger('ward')

# Refresh this far before expiry, so a sweep never starts with credentials about to die mid-flight.
REFRESH_MARGIN = timedelta(minutes=5)


class ConnectionError_(Exception):
    """The role could not be assumed. Carries a message fit to show the user."""


@dataclass
class _Cached:
    session: object
    expires_at: datetime


def _default_sts():
    import boto3

    return boto3.client('sts')


class AwsConnection:
    """Hands out a boto3 Session per connected account, assuming that account's role on demand."""

    def __init__(self, sts_factory: Callable[[], object] = _default_sts, session_factory: Callable[..., object] | None = None,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)):
        self._sts_factory = sts_factory
        self._session_factory = session_factory
        self._now = now
        self._cache: dict[str, _Cached] = {}

    def _make_session(self, creds: dict, region: str):
        if self._session_factory is not None:
            return self._session_factory(creds=creds, region=region)
        import boto3

        return boto3.Session(
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
            region_name=region,
        )

    def _assume(self, role_arn: str, external_id: str, session_name: str) -> dict:
        try:
            return self._sts_factory().assume_role(
                RoleArn=role_arn,
                ExternalId=external_id,
                RoleSessionName=session_name[:64],
                DurationSeconds=3600,
            )['Credentials']
        except Exception as exc:  # botocore raises ClientError; keep this importable without botocore
            name = type(exc).__name__
            raise ConnectionError_(
                f'Could not assume {role_arn}. Check the role exists, trusts Ward, and that the '
                f'ExternalId in its trust policy matches the one Ward issued ({name}).'
            ) from exc

    def session(self, account: Account):
        """A session for this account, reusing cached credentials until they are close to expiry."""
        if not account.role_arn:
            raise ConnectionError_(f'Account {account.id} has no role ARN yet — finish onboarding first.')

        cached = self._cache.get(account.id)
        if cached and cached.expires_at - REFRESH_MARGIN > self._now():
            return cached.session

        creds = self._assume(account.role_arn, decrypt(account.external_id_enc), f'ward-{account.id}')
        session = self._make_session(creds, account.region)
        self._cache[account.id] = _Cached(session, _aware(creds['Expiration']))
        log.info('assumed %s for %s', account.role_arn, account.id)
        return session

    def verify(self, role_arn: str, external_id: str, region: str) -> str:
        """Assume the role once and report which AWS account it actually landed in."""
        creds = self._assume(role_arn, external_id, 'ward-verify')
        identity = self._make_session(creds, region).client('sts').get_caller_identity()
        return identity['Account']

    def forget(self, account_id: str) -> None:
        self._cache.pop(account_id, None)

    def identity(self) -> dict:
        """Who Ward itself is — the credentials it will assume customer roles *from*.

        Raises ConnectionError_ when the process has no AWS credentials at all, which is the first
        thing to fix before any account can connect.
        """
        try:
            found = self._sts_factory().get_caller_identity()
        except Exception as exc:
            raise ConnectionError_(
                f'Ward has no AWS credentials of its own ({type(exc).__name__}). Run `aws configure` on the '
                f'machine running the backend, or set AWS_PROFILE, then restart it.'
            ) from exc
        return {'arn': found['Arn'], 'account': found['Account']}

    def principal(self, configured: str | None) -> str | None:
        """The principal customer roles should trust: WARD_PRINCIPAL if set, else Ward's own identity."""
        if configured:
            return configured
        try:
            return trustable(self.identity()['arn'])
        except ConnectionError_:
            return None


def trustable(arn: str) -> str:
    """An identity ARN in the form a trust policy accepts.

    `get_caller_identity` reports a role session as arn:aws:sts::…:assumed-role/Name/session, but a
    trust policy must name the role itself — arn:aws:iam::…:role/Name — or IAM rejects it.
    """
    if ':assumed-role/' in arn:
        prefix, rest = arn.split(':assumed-role/', 1)
        return prefix.replace(':sts::', ':iam::') + ':role/' + rest.split('/', 1)[0]
    return arn


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
