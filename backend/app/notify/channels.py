"""Delivery channels: Telegram and/or email when configured; otherwise messages are only recorded, never
silently dropped."""
from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass
class Delivery:
    channel: str
    delivered: bool
    error: str | None = None


class Channel(Protocol):
    def send(self, text: str) -> Delivery: ...


class LogChannel:
    """No channel configured: keep the message so the UI can show what would have been sent."""

    def send(self, text: str) -> Delivery:
        return Delivery(channel='log', delivered=False, error='No notification channel configured.')


class TelegramChannel:
    def __init__(self, token: str, chat_id: str, client: httpx.Client | None = None):
        self._url = f'https://api.telegram.org/bot{token}/sendMessage'
        self._chat_id = chat_id
        self._client = client or httpx.Client(timeout=10)

    def send(self, text: str) -> Delivery:
        try:
            res = self._client.post(self._url, json={'chat_id': self._chat_id, 'text': text, 'disable_web_page_preview': True})
            body = res.json() if res.headers.get('content-type', '').startswith('application/json') else {}
            if res.status_code == 200 and body.get('ok'):
                return Delivery('telegram', True)
            return Delivery('telegram', False, body.get('description') or f'HTTP {res.status_code}')
        except httpx.HTTPError as e:
            return Delivery('telegram', False, f'{type(e).__name__}: {e}')


class EmailChannel:
    """Alerts by email, over SMTP (Gmail, Outlook, SES, any provider).

    Port 465 speaks TLS from the first byte; any other port (587 is the usual one) upgrades with STARTTLS.
    Recipients are looked up at send time, so a new administrator starts getting alerts without a restart.
    """

    def __init__(self, host: str, port: int, username: str | None, password: str | None, sender: str,
                 recipients, timeout: float = 15, smtp_factory=None):
        self.host, self.port, self.username, self.password, self.sender = host, port, username, password, sender
        self._recipients = recipients if callable(recipients) else (lambda: list(recipients))
        self.timeout = timeout
        self._smtp_factory = smtp_factory  # tests pass a fake; None means the real smtplib

    def send(self, text: str) -> Delivery:
        import smtplib
        import ssl
        from email.message import EmailMessage

        to = [r for r in self._recipients() if r]
        if not to:
            return Delivery('email', False, 'No one to email: set WARD_ALERT_EMAILS, or make someone an administrator.')

        msg = EmailMessage()
        msg['Subject'] = _subject(text)
        msg['From'] = self.sender
        msg['To'] = ', '.join(to)
        msg.set_content(f'{text}\n\n—\nWard only watches and warns: it has not changed anything in your AWS account.\n'
                        f'Open Ward’s Alerts page to snooze or see the details.')
        try:
            if self._smtp_factory is not None:
                server = self._smtp_factory(self.host, self.port)
            elif self.port == 465:
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=ssl.create_default_context())
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            with server:
                if self._smtp_factory is None and self.port != 465:
                    server.starttls(context=ssl.create_default_context())
                if self.username:
                    server.login(self.username, self.password or '')
                server.send_message(msg)
            return Delivery('email', True)
        except (smtplib.SMTPException, OSError) as e:
            return Delivery('email', False, f'{type(e).__name__}: {e}')


def _subject(text: str) -> str:
    """'🚨 ml-training (g5.xlarge)… Broke your rule …' → 'Ward alert: ml-training (g5.xlarge), running 14h'."""
    first = text.strip().split('. ')[0].lstrip('🚨⚠️ ').strip()
    kind = 'alert' if text.lstrip().startswith('🚨') else 'warning' if text.lstrip().startswith('⚠') else 'notice'
    return f'Ward {kind}: {first}'[:150]


class FanOut:
    """Every configured channel. Delivered if any of them delivered; the errors of the others are kept."""

    def __init__(self, channels: list):
        self.channels = channels

    def send(self, text: str) -> Delivery:
        results = [c.send(text) for c in self.channels]
        errors = [f'{r.channel}: {r.error}' for r in results if not r.delivered and r.error]
        return Delivery('+'.join(r.channel for r in results)[:16], any(r.delivered for r in results),
                        '; '.join(errors) or None)


def _admin_emails() -> list[str]:
    from sqlalchemy import select

    from app.api.deps import get_database
    from app.models import User

    with get_database().sessions() as session:
        return list(session.scalars(select(User.email).where(User.role == 'admin')))


def from_settings(settings) -> Channel:
    channels = []
    if settings.telegram_token and settings.telegram_chat_id:
        channels.append(TelegramChannel(settings.telegram_token, settings.telegram_chat_id))
    if settings.smtp_host:
        recipients = settings.alert_emails or _admin_emails
        channels.append(EmailChannel(settings.smtp_host, settings.smtp_port, settings.smtp_username, settings.smtp_password,
                                     settings.smtp_from or settings.smtp_username or 'ward@localhost', recipients))
    if not channels:
        return LogChannel()
    return channels[0] if len(channels) == 1 else FanOut(channels)
