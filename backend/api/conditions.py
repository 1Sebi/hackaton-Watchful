"""/conditions — CRUD + compile preview. A condition belongs to a camera; creating
or changing one hot-reloads that camera's worker."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.actions.capabilities import (
    action_capabilities,
    normalize_action,
    validate_action,
)
from backend.core.camera_manager import get_manager
from backend.core.pipeline import get_pipeline
from backend.database import get_db
from backend.models import Condition, Event
from backend.predicates.compiler import VLMPredicateCompiler
from backend.predicates.describe import describe_predicate

router = APIRouter(prefix="/conditions", tags=["conditions"])


class ConditionIn(BaseModel):
    text: str
    action: Optional[dict] = None
    enabled: bool = True
    camera_id: Optional[str] = None
    count: Optional[int] = None  # override the people threshold (COUNT_* predicates)


class PreviewIn(BaseModel):
    text: str
    action: Optional[dict] = None
    count: Optional[int] = None


_COUNT_TYPES = {"COUNT_GT", "COUNT_LT", "COUNT_EQ"}


def _compile(text: str, count: Optional[int] = None):
    pl = get_pipeline()
    comp = VLMPredicateCompiler(pl.vlm)
    pred = comp.compile(text, available_zones=list(pl._zones.keys()))
    # let the editor set the people threshold directly instead of relying on the
    # number parsed from the text (e.g. drag "more than 10" up to 25 with a slider)
    if count is not None and str(pred.type) in _COUNT_TYPES:
        pred.params = {**pred.params, "value": int(count)}
    return pred


def _active_id() -> Optional[str]:
    return get_manager().active_id


@router.get("")
def list_conditions(camera_id: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Condition)
    if camera_id is not None:
        # include global/legacy (null-camera) rules — they run on every camera
        q = q.filter((Condition.camera_id == camera_id) | (Condition.camera_id.is_(None)))
    return [c.to_dict() for c in q.order_by(Condition.id).all()]


@router.get("/capabilities")
def capabilities():
    """Which actions the editor can offer + whether each is wired up right now."""
    return {"actions": action_capabilities()}


@router.post("/preview")
def preview(body: PreviewIn):
    """Compile + explain a condition without saving (drives the editor's live preview).

    Returns the raw predicate plus a plain-language ``explain`` block (summary +
    reliability tier + warnings) and, if an action was supplied, its validation —
    so the user sees exactly what their text and action will do before saving.
    """
    pred = _compile(body.text, body.count)
    out = pred.model_dump()
    out["explain"] = describe_predicate(pred)
    if body.action is not None:
        out["action_check"] = validate_action(normalize_action(body.action))
    return out


@router.post("")
def create(body: ConditionIn, db: Session = Depends(get_db)):
    action = normalize_action(body.action or {"type": "log"})
    check = validate_action(action)
    if not check["ok"]:
        raise HTTPException(status_code=422, detail=check["error"])
    pred = _compile(body.text, body.count)
    cam = body.camera_id or _active_id()
    c = Condition(text=body.text, predicate=pred.model_dump(),
                  action=action, enabled=body.enabled, camera_id=cam)
    db.add(c)
    db.commit()
    db.refresh(c)
    get_manager().reload(cam)
    out = c.to_dict()
    out["warnings"] = check["warnings"]  # non-blocking "won't fire until configured"
    return out


@router.put("/{cid}")
def update(cid: int, body: ConditionIn, db: Session = Depends(get_db)):
    c = db.get(Condition, cid)
    if not c:
        raise HTTPException(status_code=404, detail="condition not found")
    if (body.text and body.text != c.text) or body.count is not None:
        c.text = body.text or c.text
        c.predicate = _compile(c.text, body.count).model_dump()
    if body.action is not None:
        action = normalize_action(body.action)
        check = validate_action(action)
        if not check["ok"]:
            raise HTTPException(status_code=422, detail=check["error"])
        c.action = action
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
    # also drop this rule's event history so deleting a rule doesn't leave orphan
    # alerts lingering in the Live Activity feed
    db.query(Event).filter_by(condition_id=cid).delete()
    db.delete(c)
    db.commit()
    get_manager().reload(cam)
    return {"deleted": cid}
