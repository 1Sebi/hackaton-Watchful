"""/conditions — CRUD + compile preview. Creating a condition compiles its
predicate and hot-reloads the running pipeline."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.pipeline import get_pipeline
from backend.database import get_db
from backend.models import Condition
from backend.predicates.compiler import VLMPredicateCompiler

router = APIRouter(prefix="/conditions", tags=["conditions"])


class ConditionIn(BaseModel):
    text: str
    action: Optional[dict] = None
    enabled: bool = True


class PreviewIn(BaseModel):
    text: str


def _compile(text: str):
    pl = get_pipeline()
    comp = VLMPredicateCompiler(pl.vlm)
    return comp.compile(text, available_zones=list(pl._zones.keys()))


@router.get("")
def list_conditions(db: Session = Depends(get_db)):
    return [c.to_dict() for c in db.query(Condition).order_by(Condition.id).all()]


@router.post("/preview")
def preview(body: PreviewIn):
    """Compile a condition to a predicate without saving (for the editor)."""
    return _compile(body.text).model_dump()


@router.post("")
def create(body: ConditionIn, db: Session = Depends(get_db)):
    pred = _compile(body.text)
    c = Condition(text=body.text, predicate=pred.model_dump(),
                  action=body.action or {"type": "log"}, enabled=body.enabled)
    db.add(c)
    db.commit()
    db.refresh(c)
    get_pipeline().reload()
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
    c.enabled = body.enabled
    db.commit()
    db.refresh(c)
    get_pipeline().reload()
    return c.to_dict()


@router.delete("/{cid}")
def delete(cid: int, db: Session = Depends(get_db)):
    c = db.get(Condition, cid)
    if not c:
        raise HTTPException(status_code=404, detail="condition not found")
    db.delete(c)
    db.commit()
    get_pipeline().reload()
    return {"deleted": cid}
