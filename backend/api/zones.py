"""/zones — named polygon regions for zone-scoped predicates."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.pipeline import get_pipeline
from backend.database import get_db
from backend.models import Zone

router = APIRouter(prefix="/zones", tags=["zones"])


class ZoneIn(BaseModel):
    name: str
    polygon: List[list]  # [[x, y], ...]


@router.get("")
def list_zones(db: Session = Depends(get_db)):
    return [z.to_dict() for z in db.query(Zone).order_by(Zone.id).all()]


@router.post("")
def create(body: ZoneIn, db: Session = Depends(get_db)):
    existing = db.query(Zone).filter_by(name=body.name).first()
    if existing:
        existing.polygon = body.polygon
        db.commit()
        db.refresh(existing)
        get_pipeline().reload()
        return existing.to_dict()
    z = Zone(name=body.name, polygon=body.polygon)
    db.add(z)
    db.commit()
    db.refresh(z)
    get_pipeline().reload()
    return z.to_dict()


@router.delete("/{zid}")
def delete(zid: int, db: Session = Depends(get_db)):
    z = db.get(Zone, zid)
    if not z:
        raise HTTPException(status_code=404, detail="zone not found")
    db.delete(z)
    db.commit()
    get_pipeline().reload()
    return {"deleted": zid}
