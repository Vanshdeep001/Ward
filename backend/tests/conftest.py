import os

# Before any app import: tests use a throwaway database and never start the background watcher.
os.environ['WARD_DATABASE_URL'] = 'sqlite://'
os.environ['WARD_POLL_MINUTES'] = '0'
os.environ.pop('WARD_TELEGRAM_TOKEN', None)
# Never a developer's real keys: search runs on the local index and the extractive answer unless a test fakes them.
os.environ['WARD_NO_DOTENV'] = '1'
for key in ('WARD_PINECONE_API_KEY', 'WARD_RAG_LLM_KEY'):
    os.environ.pop(key, None)

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
