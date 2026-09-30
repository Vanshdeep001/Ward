"""Sign-in with access and refresh tokens, enforcement on (every other test file runs as a local admin —
see conftest.py)."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import admin, auth
from app.api.deps import get_database, get_inventory
from app.main import app
from app.models import RefreshToken, User


@pytest.fixture
def client(sample, monkeypatch):
    monkeypatch.delenv('WARD_AUTH_DISABLED', raising=False)
    auth.throttle = auth.Throttle()
    with get_database().sessions() as s:  # a clean slate of people for every test
        s.query(RefreshToken).delete()
        s.query(User).delete()
        s.commit()
    app.dependency_overrides[get_inventory] = lambda: sample
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def signup(c, email='asha@example.com', password='hunter2-long', name='Asha'):
    return c.post('/auth/signup', json={'name': name, 'email': email, 'password': password})


def login(c, email='asha@example.com', password='hunter2-long'):
    return c.post('/auth/login', json={'email': email, 'password': password})


def drop_access(c):
    """As the browser does when the 15-minute access cookie expires: the refresh cookie stays."""
    c.cookies.delete(auth.ACCESS_COOKIE)


# ─── Passwords ───────────────────────────────────────────────────────────────

def test_passwords_are_hashed_salted_and_verified():
    h = auth.hash_password('correct horse 9')
    assert 'correct horse' not in h and h.startswith('scrypt$')
    assert h != auth.hash_password('correct horse 9'), 'a fresh salt every time'
    assert auth.verify_password('correct horse 9', h)
    assert not auth.verify_password('correct horse 8', h)
    assert not auth.verify_password('x', 'not-a-hash')


@pytest.mark.parametrize('password, ok', [('short1', False), ('onlyletters', False), ('12345678', False), ('letters+1s', True)])
def test_password_rules(password, ok):
    assert (auth.password_problem(password) is None) == ok


# ─── Access tokens ───────────────────────────────────────────────────────────

def test_access_tokens_are_signed_short_lived_and_tamper_proof():
    user = User(id='user_1', email='a@b.co', name='A', role='user')
    now = datetime.now(timezone.utc)
    token, expires = auth.issue_access(user, 'fam', now)
    assert auth.read_access(token)['sub'] == 'user_1'
    assert expires - now == timedelta(minutes=15)
    assert auth.read_access(token, now + timedelta(minutes=16)) is None, 'expired'
    body, sig = token.split('.')
    forged = auth._b64(auth.json.dumps({**auth.read_access(token), 'role': 'admin'}).encode())
    assert auth.read_access(f'{forged}.{sig}') is None, 'changing a claim breaks the signature'
    assert auth.read_access('garbage') is None


# ─── Sign-up, sign-in, and the two cookies ───────────────────────────────────

def test_every_sign_up_is_an_ordinary_user_and_is_signed_in(client):
    assert client.get('/auth/status').json() == {'signupOpen': True}
    response = signup(client)
    assert response.status_code == 201 and response.json()['role'] == 'user'
    assert {auth.ACCESS_COOKIE, auth.REFRESH_COOKIE} <= set(response.cookies)
    cookies = response.headers.get_list('set-cookie')
    assert all('httponly' in c.lower() and 'samesite=lax' in c.lower() for c in cookies)


def test_emails_are_unique_and_case_insensitive(client):
    signup(client, email='Asha@Example.com')
    assert signup(client, email='asha@example.COM').status_code == 409


@pytest.mark.parametrize('body', [
    {'name': 'A', 'email': 'not-an-email', 'password': 'letters+1s'},
    {'name': 'A', 'email': 'a@b.co', 'password': 'short1'},
    {'name': '   ', 'email': 'a@b.co', 'password': 'letters+1s'},
])
def test_bad_sign_ups_are_refused_with_a_reason(client, body):
    response = client.post('/auth/signup', json=body)
    assert response.status_code == 422 and response.json()['detail']


def test_a_wrong_password_and_an_unknown_email_look_the_same(client):
    signup(client)
    client.cookies.clear()
    wrong, nobody = login(client, password='wrong-pass-1'), login(client, email='nobody@example.com', password='wrong-pass-1')
    assert wrong.status_code == nobody.status_code == 401 and wrong.json() == nobody.json()


def test_repeated_failures_are_throttled(client):
    signup(client)
    client.cookies.clear()
    for _ in range(5):
        login(client, password='wrong-pass-1')
    blocked = login(client)
    assert blocked.status_code == 429 and 'Retry-After' in blocked.headers, 'even the right password waits'


# ─── Staying signed in: refresh and rotation ─────────────────────────────────

def test_an_expired_access_token_is_renewed_by_the_refresh_token(client):
    signup(client)
    drop_access(client)
    assert client.get('/auth/me').status_code == 401, 'no access token, no entry'
    refreshed = client.post('/auth/refresh')
    assert refreshed.status_code == 200 and refreshed.json()['email'] == 'asha@example.com'
    assert client.get('/auth/me').status_code == 200, 'signed in again, without a password'


def test_every_refresh_rotates_the_refresh_token(client):
    signup(client)
    first = client.cookies[auth.REFRESH_COOKIE]
    client.post('/auth/refresh')
    second = client.cookies[auth.REFRESH_COOKIE]
    assert first != second


def test_a_reused_refresh_token_revokes_the_whole_sign_in(client):
    signup(client)
    stolen = client.cookies[auth.REFRESH_COOKIE]
    client.post('/auth/refresh')                 # the real user refreshes; `stolen` is now used
    current = client.cookies[auth.REFRESH_COOKIE]

    client.cookies.set(auth.REFRESH_COOKIE, stolen)
    assert client.post('/auth/refresh').status_code == 401, 'a used token is refused'
    client.cookies.set(auth.REFRESH_COOKIE, current)
    assert client.post('/auth/refresh').status_code == 401, '…and the real user’s token went with it'


def test_a_sign_in_lasts_the_refresh_window_and_no_longer(client):
    signup(client)
    with get_database().sessions() as s:
        row = s.scalars(select(RefreshToken)).one()
        assert row.expires_at - row.created_at == timedelta(days=7)
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)  # a week has passed
        s.commit()
    drop_access(client)
    assert client.post('/auth/refresh').status_code == 401


def test_rotation_does_not_extend_the_week(client):
    signup(client)
    with get_database().sessions() as s:
        original_end = s.scalars(select(RefreshToken)).one().expires_at
    client.post('/auth/refresh')
    with get_database().sessions() as s:
        newest = s.scalars(select(RefreshToken).where(RefreshToken.used_at.is_(None))).one()
    assert newest.expires_at == original_end


def test_only_hashes_of_refresh_tokens_are_stored(client):
    token = signup(client).cookies[auth.REFRESH_COOKIE]
    with get_database().sessions() as s:
        stored = s.scalars(select(RefreshToken.token_hash)).all()
    assert token not in stored and len(stored) == 1


def test_sign_out_ends_the_sign_in(client):
    signup(client)
    refresh = client.cookies[auth.REFRESH_COOKIE]
    assert client.post('/auth/logout').status_code == 204
    assert client.get('/auth/me').status_code == 401
    client.cookies.set(auth.REFRESH_COOKIE, refresh)
    assert client.post('/auth/refresh').status_code == 401, 'the refresh token was revoked, not just forgotten'


# ─── What is protected ───────────────────────────────────────────────────────

def test_the_app_needs_a_signed_in_user(client):
    assert client.get('/resources').status_code == 401
    assert client.get('/health').status_code == 200, 'the liveness check stays open'
    signup(client)
    assert client.get('/resources').status_code == 200


def test_admins_are_made_on_the_server_and_only_they_see_internal_pages(client):
    signup(client)
    assert client.get('/evals/rag').status_code == 403, 'a new account is a user'
    assert 'now an administrator' in admin.set_role('ASHA@example.com', 'admin')
    client.post('/auth/refresh')  # the role is in the access token: a fresh one carries it
    assert client.get('/auth/me').json()['role'] == 'admin'
    assert client.get('/evals/rag').status_code == 200
    with pytest.raises(SystemExit):
        admin.set_role('nobody@example.com', 'admin')


def test_the_command_line_can_create_an_admin_and_warns_about_a_weak_password(client):
    message = admin.create_user('Boss@Example.com', 'Boss', 'onlyletters', admin=True)
    assert 'administrator' in message and 'weak password' in message
    assert login(client, email='boss@example.com', password='onlyletters').json()['role'] == 'admin'
