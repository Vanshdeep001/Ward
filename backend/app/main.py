import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from importlib.metadata import version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import accounts, chat, costs, guardian, resources, rules, search, watch
from app.api.deps import get_channel, get_compiler, get_database, get_inventory
from app.config import settings
from app.engine import custodian
from app.rules_service import seed_starter_rules
from app.watcher.run import run_sweep

log = logging.getLogger('ward')


def sweep_once() -> None:
    with get_database().sessions() as session:
        result = run_sweep(session, get_inventory(), get_channel(), datetime.now(timezone.utc), settings.region)
    log.info('sweep: %d rules, %d resources, %d transitions, %d notifications',
             result.rules, result.evaluated, len(result.transitions), result.notifications)


async def watch_loop(minutes: float) -> None:
    while True:
        try:
            await asyncio.to_thread(sweep_once)
        except Exception:  # one bad sweep must not stop the watcher
            log.exception('sweep failed')
        await asyncio.sleep(minutes * 60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    custodian.warm_up(settings.region)
    get_inventory()
    with get_database().sessions() as session:
        seed_starter_rules(session, settings.region)
    task = asyncio.create_task(watch_loop(settings.poll_minutes)) if settings.poll_minutes > 0 else None
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title='Ward', version='0.2.0', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=['*'],
    allow_headers=['*'],
)
app.include_router(rules.router)
app.include_router(resources.router)
app.include_router(watch.router)
app.include_router(accounts.router)
app.include_router(costs.router)
app.include_router(guardian.router)
app.include_router(chat.router)
app.include_router(search.router)


@app.get('/health')
def health():
    compiler = get_compiler()
    llm = getattr(compiler, 'llm', None)
    return {
        'status': 'ok',
        'inventory': settings.inventory_source,
        'region': settings.region,
        'custodian': version('c7n'),
        'watcher': f'every {settings.poll_minutes:g} min' if settings.poll_minutes > 0 else 'manual',
        'compiler': {
            'mode': compiler.name if llm else 'templates',
            # Only asked when a model is in use; a quick probe, so /health stays fast either way.
            'model': {'url': llm.url, 'name': llm.model, 'reachable': llm.reachable()} if llm else None,
        },
    }
