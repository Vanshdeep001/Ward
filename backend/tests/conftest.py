import pytest

from app.engine import custodian
from app.inventory.sample import SampleInventory

REGION = 'ap-south-1'


@pytest.fixture(scope='session', autouse=True)
def warm_custodian():
    custodian.warm_up(REGION)


@pytest.fixture(scope='session')
def sample():
    # Hourly snapshots, so short sessions are seen the way a 15-minute watcher would see them.
    return SampleInventory(days=30, every_hours=1)
