"""Search: ask the inventory a question and get an answer grounded in real resources (RAG).

POST /search          {query, history?} → {answer, sources, retriever, generator, notice}
GET  /search/status   which retriever and answer model are in use, and what is indexed
POST /search/reindex  drop what was sent and index the account again from scratch
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_inventory, get_search, get_session
from app.config import settings
from app.guardian import findings as finder
from app.inventory.store import InventoryStore
from app.models import Alert
from app.rag.documents import Doc, build_documents
from app.rag.service import SearchService
from app.rag.stores import StoreUnavailable
from app.watcher.run import active_account

router = APIRouter(tags=['search'])


class Turn(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(max_length=4000)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    history: list[Turn] = Field(default_factory=list, max_length=12)
    # Resource ids to ask about. Empty: the whole account.
    scope: list[str] = Field(default_factory=list, max_length=200)


def namespace_for(session: Session) -> str:
    """One namespace per account, so a shared index never mixes two accounts' resources."""
    account = active_account(session)
    if account is not None:
        return f'acct-{account.aws_account_id or account.id}'
    return 'sample' if settings.inventory_source != 'aws' else 'default'


def documents_for(session: Session, inventory: InventoryStore) -> list[Doc]:
    snapshot = inventory.latest()
    alerts = [
        {'resourceId': a.resource_id, 'rule': a.rule.english, 'level': a.level, 'status': a.status}
        for a in session.scalars(select(Alert).where(Alert.status.in_(('open', 'snoozed'))))
    ]
    return build_documents(snapshot, alerts, finder.find_all(snapshot), settings.region)


def run_search(query: str, history: list[dict], session: Session, inventory: InventoryStore,
               search: SearchService, scope: list[str] | None = None) -> dict:
    return search.ask(query, namespace_for(session), documents_for(session, inventory), history, scope)


@router.post('/search')
def search_inventory(req: SearchRequest, session: Session = Depends(get_session),
                     inventory: InventoryStore = Depends(get_inventory), search: SearchService = Depends(get_search)):
    return run_search(req.query, [t.model_dump() for t in req.history], session, inventory, search, req.scope)


@router.get('/search/status')
def search_status(search: SearchService = Depends(get_search)):
    return search.status()


@router.post('/search/reindex')
def reindex(session: Session = Depends(get_session), inventory: InventoryStore = Depends(get_inventory),
            search: SearchService = Depends(get_search)):
    namespace = namespace_for(session)
    search.forget(namespace)
    try:
        stats = search.sync(namespace, documents_for(session, inventory))
    except StoreUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return {'namespace': namespace, 'retriever': search.store.name, **stats}
