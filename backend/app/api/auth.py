"""Sign up, sign in, refresh, sign out, and who is signed in.

POST /auth/signup    {name, email, password}  → a user account, signed in: sets the access and refresh cookies
POST /auth/login     {email, password}        → sets the access and refresh cookies
POST /auth/refresh                            → swaps the refresh cookie for a new pair (rotation)
POST /auth/logout                             → revokes this sign-in and clears both cookies
GET  /auth/me                                 → the signed-in user (from the access token), or 401
GET  /auth/status                             → whether sign-up is open

Every account created here is an ordinary user. Administrators are made by whoever runs Ward, directly:
    python -m app.admin promote you@example.com

Errors never say which half of a sign-in was wrong, so the form can't be used to find out who has an account.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.api.deps import get_session
from app.config import settings
from app.models import User

router = APIRouter(prefix='/auth', tags=['auth'])
WRONG = 'That email and password don’t match an account.'


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=200)


def _set_cookies(response: Response, tokens: auth.Tokens) -> None:
    common = {'httponly': True, 'samesite': 'lax', 'secure': settings.cookie_secure, 'path': '/'}
    # Each cookie lives exactly as long as its token, so the browser drops them on time too.
    response.set_cookie(auth.ACCESS_COOKIE, tokens.access, expires=tokens.access_expires, **common)
    response.set_cookie(auth.REFRESH_COOKIE, tokens.refresh, expires=tokens.refresh_expires, **common)


def _clear_cookies(response: Response) -> None:
    for name in (auth.ACCESS_COOKIE, auth.REFRESH_COOKIE):
        response.delete_cookie(name, path='/')


@router.get('/status')
def status():
    return {'signupOpen': settings.allow_signup}


@router.post('/signup', status_code=201)
def signup(req: SignupRequest, request: Request, response: Response, session: Session = Depends(get_session)):
    email = req.email.strip().lower()
    name = req.name.strip()
    if not auth.EMAIL.match(email):
        raise HTTPException(422, 'That doesn’t look like an email address.')
    if not name:
        raise HTTPException(422, 'Tell us your name.')
    if (problem := auth.password_problem(req.password)) is not None:
        raise HTTPException(422, problem)
    if not settings.allow_signup:
        raise HTTPException(403, 'Sign-up is closed on this Ward. Ask an administrator for an account.')
    if session.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(409, 'An account with that email already exists — sign in instead.')

    user = User(email=email, name=name, password_hash=auth.hash_password(req.password),
                role='user', created_at=datetime.now(timezone.utc))
    session.add(user)
    session.commit()
    _set_cookies(response, auth.start_session(session, user, request.headers.get('user-agent')))
    return auth.user_out(user)


@router.post('/login')
def login(req: LoginRequest, request: Request, response: Response, session: Session = Depends(get_session)):
    email = req.email.strip().lower()
    keys = (f'email:{email}', f'ip:{request.client.host if request.client else "?"}')
    wait = auth.throttle.blocked_for(*keys)
    if wait > 0:
        raise HTTPException(429, f'Too many attempts. Try again in {max(1, round(wait / 60))} minutes.',
                            headers={'Retry-After': str(int(wait) + 1)})

    user = session.scalar(select(User).where(User.email == email))
    if not auth.verify_password(req.password, user.password_hash if user else auth._DUMMY_HASH) or user is None:
        auth.throttle.fail(*keys)
        raise HTTPException(401, WRONG)

    auth.throttle.clear(*keys)
    _set_cookies(response, auth.start_session(session, user, request.headers.get('user-agent')))
    return auth.user_out(user)


@router.post('/refresh')
def refresh(request: Request, response: Response, session: Session = Depends(get_session)):
    rotated = auth.rotate(session, request.cookies.get(auth.REFRESH_COOKIE), request.headers.get('user-agent'))
    if rotated is None:
        # Expired, signed out, or a reused token (whose whole sign-in has just been revoked): sign in again.
        failed = Response(status_code=401, content='{"detail":"Your session has ended. Sign in again."}',
                          media_type='application/json')
        _clear_cookies(failed)
        return failed
    user, tokens = rotated
    _set_cookies(response, tokens)
    return auth.user_out(user)


@router.post('/logout', status_code=204)
def logout(request: Request, response: Response, session: Session = Depends(get_session)):
    auth.end_session(session, request.cookies.get(auth.REFRESH_COOKIE))
    _clear_cookies(response)
    response.status_code = 204
    return response


@router.get('/me')
def me(user: auth.Principal = Depends(auth.current_user)):
    return auth.user_out(user)
