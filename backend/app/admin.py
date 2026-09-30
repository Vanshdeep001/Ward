"""Make or remove administrators — from the machine Ward runs on, never from the web.

    python -m app.admin promote you@example.com     # sign up in the app first, then run this
    python -m app.admin demote someone@example.com
    python -m app.admin list
    python -m app.admin create you@example.com --name "Your Name" --admin   # asks for the password
    python -m app.admin set-password you@example.com

Sign-up in the app only ever creates ordinary users, so being an administrator can't be claimed by
anyone who reaches the sign-up page: it takes access to the server and its database.
"""
import argparse
import sys

from sqlalchemy import select

from app.api.deps import get_database
from app.models import User


def set_role(email: str, role: str) -> str:
    with get_database().sessions() as session:
        user = session.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None:
            raise SystemExit(f'No account for {email}. Sign up in the app first, then run this again.')
        user.role = role
        session.commit()
        return f'{user.email} is now {"an administrator" if role == "admin" else "an ordinary user"}.'


def create_user(email: str, name: str, password: str, admin: bool) -> str:
    """An account made on the server. Skips the sign-up page's password rule on purpose — the operator
    decides — but warns when the password is one the page would refuse."""
    from datetime import datetime, timezone

    from app.auth import EMAIL, hash_password, password_problem

    email = email.strip().lower()
    if not EMAIL.match(email):
        raise SystemExit(f'{email} is not an email address.')
    with get_database().sessions() as session:
        if session.scalar(select(User).where(User.email == email)) is not None:
            raise SystemExit(f'{email} already has an account — use promote / set-password instead.')
        session.add(User(email=email, name=name.strip() or email.split('@')[0], password_hash=hash_password(password),
                         role='admin' if admin else 'user', created_at=datetime.now(timezone.utc)))
        session.commit()
    warning = password_problem(password)
    note = f'\n  ! weak password: {warning} Change it with: python -m app.admin set-password {email}' if warning else ''
    return f'Created {email} as {"an administrator" if admin else "a user"}.{note}'


def set_password(email: str, password: str) -> str:
    from app.auth import hash_password

    with get_database().sessions() as session:
        user = session.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None:
            raise SystemExit(f'No account for {email}.')
        user.password_hash = hash_password(password)
        session.commit()
    return f'Password changed for {user.email}. Existing sign-ins stay valid until they expire.'


def _read_password(from_stdin: bool) -> str:
    """Never from the command line itself, where it would sit in shell history."""
    if from_stdin:
        return sys.stdin.readline().rstrip('\r\n')
    import getpass

    first = getpass.getpass('Password: ')
    if getpass.getpass('Again: ') != first:
        raise SystemExit('The two passwords don’t match.')
    return first


def list_users() -> str:
    with get_database().sessions() as session:
        users = session.scalars(select(User).order_by(User.created_at)).all()
    if not users:
        return 'No accounts yet.'
    return '\n'.join(f'{u.role:6}  {u.email:40}  {u.name}' for u in users)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command', required=True)
    sub.add_parser('promote', help='make an account an administrator').add_argument('email')
    sub.add_parser('demote', help='make an administrator an ordinary user').add_argument('email')
    sub.add_parser('list', help='every account and its role')
    create = sub.add_parser('create', help='make an account here, without the sign-up page')
    create.add_argument('email')
    create.add_argument('--name', default='')
    create.add_argument('--admin', action='store_true', help='make it an administrator')
    create.add_argument('--password-stdin', action='store_true', help='read the password from standard input')
    reset = sub.add_parser('set-password', help='change an account’s password')
    reset.add_argument('email')
    reset.add_argument('--password-stdin', action='store_true')
    args = ap.parse_args(argv)
    if args.command == 'list':
        print(list_users())
    elif args.command == 'create':
        print(create_user(args.email, args.name, _read_password(args.password_stdin), args.admin))
    elif args.command == 'set-password':
        print(set_password(args.email, _read_password(args.password_stdin)))
    else:
        print(set_role(args.email, 'admin' if args.command == 'promote' else 'user'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
