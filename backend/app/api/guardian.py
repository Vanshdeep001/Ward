"""Guardian: findings nobody wrote a rule for, and conflicts between the rules they did write."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_inventory, get_session
from app.config import settings
from app.guardian import conflicts as conflict_detector
from app.guardian import findings as finder
from app.inventory.store import InventoryStore
from app.models import Rule

router = APIRouter(tags=['guardian'])


@router.get('/guardian/findings')
def list_findings(inventory: InventoryStore = Depends(get_inventory)):
    return finder.find_all(inventory.latest())


@router.get('/rules/conflicts')
def list_conflicts(inventory: InventoryStore = Depends(get_inventory), session: Session = Depends(get_session)):
    rules = session.scalars(select(Rule).where(Rule.status == 'active')).all()
    return conflict_detector.detect(rules, inventory.latest(), settings.region)
