from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy.orm import Session

from app.config import settings
from app.db import Database
from app.inventory.sample import SampleInventory
from app.inventory.store import InventoryStore
from app.notify.channels import Channel, from_settings


@lru_cache(maxsize=1)
def get_compiler():
    """The compiler named by WARD_COMPILER. Anything unrecognised falls back to templates, loudly."""
    from app.compiler.llm import HybridCompiler, LlmCompiler
    from app.compiler.templates import TemplateCompiler

    mode = settings.compiler.lower()
    if mode in ('hybrid', 'llm'):
        llm = LlmCompiler(settings.llm_url, settings.llm_model, settings.llm_timeout)
        return HybridCompiler(llm, prefer_llm=(mode == 'llm'))
    if mode != 'templates':
        import logging

        logging.getLogger('ward').warning('WARD_COMPILER=%r is not templates|hybrid|llm; using templates', mode)
    return TemplateCompiler()


@lru_cache(maxsize=1)
def get_search():
    """The RAG search service: Pinecone when WARD_PINECONE_API_KEY is set, else a local keyword index;
    the answering model when WARD_RAG_LLM_KEY is set, else answers that list the matches."""
    from app.rag.answer import LlmAnswerer
    from app.rag.service import SearchService
    from app.rag.stores import PineconeStore

    store = None
    if settings.pinecone_api_key:
        store = PineconeStore(settings.pinecone_api_key, settings.pinecone_index, settings.pinecone_cloud,
                              settings.pinecone_region, settings.pinecone_embed_model, settings.pinecone_rerank_model)
    answerer = None
    if settings.rag_llm_key:
        answerer = LlmAnswerer(settings.rag_llm_url, settings.rag_llm_key, settings.rag_llm_model)
    return SearchService(store, answerer)


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
