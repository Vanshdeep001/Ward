from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy.orm import Session

from app.config import settings
from app.db import Database
from app.inventory.sample import SampleInventory
from app.inventory.store import InventoryStore
from app.notify.channels import Channel, from_settings


@lru_cache(maxsize=1)
def get_connection():
    from app.aws.connection import AwsConnection

    return AwsConnection()


@lru_cache(maxsize=1)
def get_inventory() -> InventoryStore:
    """Sample inventory unless a real account is connected.

    A connected account wins over WARD_INVENTORY_SOURCE=aws: sweeping through an assumed role is
    always preferable to whatever ambient credentials the process happens to hold.
    """
    from app.watcher.run import active_account

    with get_database().sessions() as session:
        account = active_account(session)
        if account is not None:
            from app.watcher.poller import LiveInventory

            return LiveInventory(account.region, session_factory=lambda: get_connection().session(account))

    if settings.inventory_source == 'aws':
        from app.watcher.poller import LiveInventory

        return LiveInventory(settings.region)
    return SampleInventory()


def reset_inventory() -> None:
    """Drop the cached inventory so the next request re-resolves it (used after connect/disconnect)."""
    get_inventory.cache_clear()


@lru_cache(maxsize=1)
def get_database() -> Database:
    db = Database(settings.database_url)
    db.create_all()
    return db


def get_session() -> Iterator[Session]:
    yield from get_database().session()


@lru_cache(maxsize=1)
def get_channel() -> Channel:
    return from_settings(settings)
