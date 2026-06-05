"""Event — one recorded trigger (or notable evaluation) for a condition."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)

from backend.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    condition_id = Column(Integer, ForeignKey("conditions.id"), nullable=True)
    camera_id = Column(String, nullable=True)  # which camera fired
    timestamp = Column(DateTime, default=_utcnow)
    detected = Column(Boolean, default=False)
    confidence = Column(Float, default=0.0)
    reason = Column(String, default="")
    action_taken = Column(String, default="")
    snapshot_path = Column(String, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "condition_id": self.condition_id,
            "camera_id": self.camera_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "detected": self.detected,
            "confidence": self.confidence,
            "reason": self.reason,
            "action_taken": self.action_taken,
            "snapshot_path": self.snapshot_path,
        }
