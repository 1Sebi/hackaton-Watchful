"""/conditions — CRUD + compile preview. A condition belongs to a camera; creating
or changing one hot-reloads that camera's worker."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.camera_manager import get_manager
from backend.core.pipeline import get_pipeline
from backend.database import get_db
from backend.models import Condition
from backend.predicates.compiler import VLMPredicateCompiler

router = APIRouter(prefix="/conditions", tags=["conditions"])


class ConditionIn(BaseModel):
    text: str
    action: Optional[dict] = None
    enabled: bool = True
    camera_id: Optional[str] = None


class PreviewIn(BaseModel):
    text: str


def _compile(text: str):
    pl = get_pipeline()
    comp = VLMPredicateCompiler(pl.vlm)
    return comp.compile(text, available_zones=list(pl._zones.keys()))


def _active_id() -> Optional[str]:
    return get_manager().active_id


@router.get("")
def list_conditions(camera_id: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Condition)
    if camera_id is not None:
        q = q.filter(Condition.camera_id == camera_id)
    return [c.to_dict() for c in q.order_by(Condition.id).all()]


@router.post("/preview")
def preview(body: PreviewIn):
    """Compile a condition to a predicate without saving (for the editor)."""
    return _compile(body.text).model_dump()


@router.post("")
def create(body: ConditionIn, db: Session = Depends(get_db)):
    pred = _compile(body.text)
    cam = body.camera_id or _active_id()
    c = Condition(text=body.text, predicate=pred.model_dump(),
                  action=body.action or {"type": "log"}, enabled=body.enabled,
                  camera_id=cam)
    db.add(c)
    db.commit()
    db.refresh(c)
    get_manager().reload(cam)
    return c.to_dict()


@router.put("/{cid}")
def update(cid: int, body: ConditionIn, db: Session = Depends(get_db)):
    c = db.get(Condition, cid)
    if not c:
        raise HTTPException(status_code=404, detail="condition not found")
    if body.text and body.text != c.text:
        c.text = body.text
        c.predicate = _compile(body.text).model_dump()
    if body.action is not None:
        c.action = body.action
    if body.camera_id is not None:
        c.camera_id = body.camera_id
    c.enabled = body.enabled
    db.commit()
    db.refresh(c)
    get_manager().reload()  # reload all: the rule may have moved between cameras
    return c.to_dict()


@router.delete("/{cid}")
def delete(cid: int, db: Session = Depends(get_db)):
    c = db.get(Condition, cid)
    if not c:
        raise HTTPException(status_code=404, detail="condition not found")
    cam = c.camera_id
    db.delete(c)
    db.commit()
    get_manager().reload(cam)
    return {"deleted": cid}
