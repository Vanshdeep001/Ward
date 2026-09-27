"""Delivery channels. Telegram when configured; otherwise messages are only recorded, never silently dropped."""
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


def from_settings(settings) -> Channel:
    if settings.telegram_token and settings.telegram_chat_id:
        return TelegramChannel(settings.telegram_token, settings.telegram_chat_id)
    return LogChannel()
