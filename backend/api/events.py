"""/events — recent trigger history from the database."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Event

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
def list_events(limit: int = 50, db: Session = Depends(get_db)):
    rows = db.query(Event).order_by(Event.id.desc()).limit(limit).all()
    return [e.to_dict() for e in rows]


@router.delete("")
def clear_events(db: Session = Depends(get_db)):
    """Clear the whole event/alert history (e.g. to wipe stale demo alerts)."""
    n = db.query(Event).delete()
    db.commit()
    return {"deleted": n}
