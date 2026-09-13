from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import resources, rules
from app.api.deps import get_inventory
from app.config import settings
from app.engine import custodian


@asynccontextmanager
async def lifespan(_: FastAPI):
    custodian.warm_up(settings.region)
    get_inventory()
    yield


app = FastAPI(title='Ward', version='0.1.0', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=['*'],
    allow_headers=['*'],
)
app.include_router(rules.router)
app.include_router(resources.router)


@app.get('/health')
def health():
    return {
        'status': 'ok',
        'inventory': settings.inventory_source,
        'region': settings.region,
        'custodian': version('c7n'),
    }
