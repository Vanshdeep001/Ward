from functools import lru_cache

from app.config import settings
from app.inventory.sample import SampleInventory
from app.inventory.store import InventoryStore


@lru_cache(maxsize=1)
def get_inventory() -> InventoryStore:
    if settings.inventory_source == 'aws':
        from app.watcher.poller import LiveInventory

        return LiveInventory(settings.region)
    return SampleInventory()
