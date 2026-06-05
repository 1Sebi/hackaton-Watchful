"""Condition — a user's natural-language rule + its compiled predicate + action."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String

from backend.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Condition(Base):
    __tablename__ = "conditions"

    id = Column(Integer, primary_key=True)
    camera_id = Column(String, nullable=True)      # which camera this rule watches
    text = Column(String, nullable=False)          # the NL condition
    predicate = Column(JSON, nullable=True)        # compiled Predicate dict
    action = Column(JSON, nullable=True)           # action config dict
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "camera_id": self.camera_id,
            "text": self.text,
            "predicate": self.predicate,
            "action": self.action,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
