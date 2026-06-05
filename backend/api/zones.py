"""/zones — named polygon regions for zone-scoped predicates. Zones are per-camera
(polygons are in that camera's pixel coords)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.camera_manager import get_manager
from backend.database import get_db
from backend.models import Zone

router = APIRouter(prefix="/zones", tags=["zones"])


class ZoneIn(BaseModel):
    name: str
    polygon: List[list]  # [[x, y], ...]
    camera_id: Optional[str] = None


def _active_id() -> Optional[str]:
    return get_manager().active_id


@router.get("")
def list_zones(camera_id: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Zone)
    if camera_id is not None:
        q = q.filter((Zone.camera_id == camera_id) | (Zone.camera_id.is_(None)))
    return [z.to_dict() for z in q.order_by(Zone.id).all()]


@router.post("")
def create(body: ZoneIn, db: Session = Depends(get_db)):
    cam = body.camera_id or _active_id()
    existing = db.query(Zone).filter_by(name=body.name, camera_id=cam).first()
    if existing:
        existing.polygon = body.polygon
        db.commit()
        db.refresh(existing)
        get_manager().reload(cam)
        return existing.to_dict()
    z = Zone(name=body.name, polygon=body.polygon, camera_id=cam)
    db.add(z)
    db.commit()
    db.refresh(z)
    get_manager().reload(cam)
    return z.to_dict()


@router.delete("/{zid}")
def delete(zid: int, db: Session = Depends(get_db)):
    z = db.get(Zone, zid)
    if not z:
        raise HTTPException(status_code=404, detail="zone not found")
    cam = z.camera_id
    db.delete(z)
    db.commit()
    get_manager().reload(cam)
    return {"deleted": zid}
