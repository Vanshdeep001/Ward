import os

# Before any app import: tests use a throwaway database and never start the background watcher.
os.environ['WARD_DATABASE_URL'] = 'sqlite://'
os.environ['WARD_POLL_MINUTES'] = '0'
os.environ.pop('WARD_TELEGRAM_TOKEN', None)

import pytest  # noqa: E402

from app.db import Database  # noqa: E402
from app.engine import custodian  # noqa: E402
from app.inventory.sample import SampleInventory  # noqa: E402

REGION = 'ap-south-1'


@pytest.fixture(scope='session', autouse=True)
def warm_custodian():
    custodian.warm_up(REGION)


@pytest.fixture(scope='session')
def sample():
    return SampleInventory(days=30, every_hours=1)


@pytest.fixture
def session():
    db = Database('sqlite://')
    db.create_all()
    with db.sessions() as s:
        yield s
