"""Sign-in: passwords, access and refresh tokens, and the checks every protected endpoint runs.

Passwords are hashed with scrypt from the standard library — salted, memory-hard, and stored as a
self-describing string (`scrypt$n$r$p$salt$hash`) so the cost can be raised later without breaking old
hashes. The password itself is never stored or logged.

A sign-in gives two tokens, both in HttpOnly cookies that page JavaScript can't read:

  access token    short-lived (WARD_ACCESS_MINUTES, 15). Signed with HMAC-SHA256 and carrying who you are and
                  your role, so every request is checked without touching the database.
  refresh token   long-lived (WARD_SESSION_DAYS, 7 — fixed from sign-in, not extended). Random; the database
                  keeps only its SHA-256. POST /auth/refresh swaps it for a new access token *and a new
                  refresh token*; the old one is marked used. Presenting a used one again means it was
                  copied, and every token from that sign-in is revoked at once.

So a sign-in lasts a week or until sign-out. An access token can't be recalled, which is why it lives only
minutes: a sign-out, or a role change, fully applies within that window. SameSite=Lax keeps both cookies
off cross-site posts.

Failed sign-ins are counted per email and per address; too many in a window and further attempts are
refused for a while, so a password can't be guessed at speed.

Every app router depends on `current_user`; the internal ones on `require_admin`. Sign-up only ever makes
ordinary users; an administrator is made by whoever runs Ward, from the command line (app/admin.py).

Tests set WARD_AUTH_DISABLED=1, which makes `current_user` return a local admin so the hundreds of
existing endpoint tests don't each need to sign in; the auth tests unset it.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.crypto import _key as _encryption_key
from app.models import RefreshToken, User

ACCESS_COOKIE = 'ward_access'
REFRESH_COOKIE = 'ward_refresh'
SCRYPT = {'n': 2 ** 14, 'r': 8, 'p': 1}
EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
MIN_PASSWORD = 8

# ─── Passwords ───────────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, maxmem=64 * 1024 * 1024, **SCRYPT)
    return f'scrypt${SCRYPT["n"]}${SCRYPT["r"]}${SCRYPT["p"]}${salt.hex()}${digest.hex()}'


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split('$')
        if scheme != 'scrypt':
            return False
        candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                                   dklen=len(digest) // 2, maxmem=64 * 1024 * 1024)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate.hex(), digest)  # constant time: no timing hint about how close a guess was


# A real hash of nothing, checked when the email is unknown, so "no such user" takes as long as "wrong
# password" and response time doesn't reveal which emails have accounts.
_DUMMY_HASH = hash_password(secrets.token_hex(16))


def password_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD:
        return f'Use at least {MIN_PASSWORD} characters.'
    if len(password) > 200:
        return 'That password is too long.'
    if password.isdigit() or password.isalpha():
        return 'Mix letters with numbers or symbols.'
    return None


# ─── Throttling ──────────────────────────────────────────────────────────────

class Throttle:
    """At most `limit` failures per key in `window` seconds. In memory: enough for one server process."""

    def __init__(self, limit: int = 5, window: float = 15 * 60):
        self.limit, self.window = limit, window
        self._failures: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque:
        q = self._failures[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def blocked_for(self, *keys: str) -> float:
        """Seconds until a sign-in may be tried again; 0 when it may be tried now."""
        now = time.monotonic()
        with self._lock:
            waits = [self.window - (now - q[0]) for k in keys if len(q := self._recent(k, now)) >= self.limit]
        return max(waits, default=0.0)

    def fail(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for k in keys:
                self._recent(k, now).append(now)

    def clear(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._failures.pop(k, None)


throttle = Throttle()


# ─── Access tokens: signed, short-lived, checked without the database ───────

def _signing_key() -> bytes:
    # Derived from Ward's encryption key (app/crypto.py) rather than stored beside it: one secret to guard.
    return hmac.new(_encryption_key(), b'ward-access-token-v1', hashlib.sha256).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


def issue_access(user: User, family_id: str, now: datetime) -> tuple[str, datetime]:
    expires = now + timedelta(minutes=settings.access_minutes)
    claims = {'sub': user.id, 'email': user.email, 'name': user.name, 'role': user.role, 'sid': family_id,
              'iat': int(now.timestamp()), 'exp': int(expires.timestamp())}
    body = _b64(json.dumps(claims, separators=(',', ':')).encode())
    signature = _b64(hmac.new(_signing_key(), body.encode(), hashlib.sha256).digest())
    return f'{body}.{signature}', expires


def read_access(token: str | None, now: datetime | None = None) -> dict | None:
    """The claims of a valid, unexpired access token — or None."""
    if not token or token.count('.') != 1:
        return None
    body, signature = token.split('.')
    expected = _b64(hmac.new(_signing_key(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        claims = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if claims.get('exp', 0) <= (now or datetime.now(timezone.utc)).timestamp():
        return None
    return claims


# ─── Refresh tokens: random, stored hashed, rotated on every use ────────────

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class Tokens:
    access: str
    access_expires: datetime
    refresh: str
    refresh_expires: datetime


def _new_refresh(session: Session, user: User, family_id: str, expires: datetime, user_agent: str | None,
                 now: datetime) -> str:
    token = secrets.token_urlsafe(32)
    session.add(RefreshToken(token_hash=_token_hash(token), family_id=family_id, user_id=user.id, created_at=now,
                             expires_at=expires, user_agent=(user_agent or '')[:200] or None))
    return token


def start_session(session: Session, user: User, user_agent: str | None, now: datetime | None = None) -> Tokens:
    """A sign-in: a new family, a refresh token that ends it WARD_SESSION_DAYS from now, and an access token."""
    now = now or datetime.now(timezone.utc)
    family = secrets.token_hex(16)
    refresh_expires = now + timedelta(days=settings.session_days)
    refresh = _new_refresh(session, user, family, refresh_expires, user_agent, now)
    user.last_login_at = now
    session.commit()
    access, access_expires = issue_access(user, family, now)
    return Tokens(access, access_expires, refresh, refresh_expires)


def rotate(session: Session, refresh: str | None, user_agent: str | None, now: datetime | None = None) -> tuple[User, Tokens] | None:
    """Swap a refresh token for a fresh pair. None when it is unknown, expired, revoked — or already used,
    in which case it was copied, and the whole sign-in is revoked."""
    now = now or datetime.now(timezone.utc)
    if not refresh:
        return None
    row = session.get(RefreshToken, _token_hash(refresh))
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        return None
    if row.used_at is not None:
        revoke_family(session, row.family_id, now)
        return None
    row.used_at = now
    new_refresh = _new_refresh(session, row.user, row.family_id, row.expires_at, user_agent, now)
    session.commit()
    access, access_expires = issue_access(row.user, row.family_id, now)
    return row.user, Tokens(access, access_expires, new_refresh, row.expires_at)


def revoke_family(session: Session, family_id: str, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    for row in session.scalars(select(RefreshToken).where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))):
        row.revoked_at = now
    session.commit()


def end_session(session: Session, refresh: str | None) -> None:
    """Sign out: every refresh token from this sign-in stops working now."""
    if refresh:
        row = session.get(RefreshToken, _token_hash(refresh))
        if row is not None:
            revoke_family(session, row.family_id)


def token_from(request: Request) -> str | None:
    """The access token: its cookie, or a Bearer header for scripts and tests that aren't a browser."""
    token = request.cookies.get(ACCESS_COOKIE)
    if token:
        return token
    header = request.headers.get('authorization', '')
    return header[7:].strip() if header.lower().startswith('bearer ') else None


def user_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(User)) or 0


# ─── What protected endpoints depend on ──────────────────────────────────────

def enforced() -> bool:
    return os.getenv('WARD_AUTH_DISABLED') != '1'


@dataclass
class Principal:
    """Who is making a request, as the access token says. No database read: that's the point of it."""
    id: str
    email: str
    name: str
    role: str
    session: str | None = None
    created_at: datetime | None = None


LOCAL_ADMIN = Principal(id='local', email='local@ward', name='Local', role='admin')


def current_user(request: Request) -> Principal:
    if not enforced():
        return LOCAL_ADMIN
    claims = read_access(token_from(request))
    if claims is None:
        # Expired or missing: the client refreshes (POST /auth/refresh) and retries.
        raise HTTPException(401, 'Sign in to use Ward.', headers={'WWW-Authenticate': 'Bearer'})
    return Principal(id=claims['sub'], email=claims['email'], name=claims['name'], role=claims['role'], session=claims.get('sid'))


def require_admin(user: Principal = Depends(current_user)) -> Principal:
    if user.role != 'admin':
        raise HTTPException(403, 'This page is for Ward’s administrators.')
    return user


def user_out(user) -> dict:
    return {'id': user.id, 'email': user.email, 'name': user.name, 'role': user.role,
            'createdAt': user.created_at.isoformat() if getattr(user, 'created_at', None) else None}
