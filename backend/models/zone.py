"""Zone — a named polygon region used by zone-scoped predicates."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Integer, String

from backend.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True)
    camera_id = Column(String, nullable=True)  # zones are per-camera (pixel coords)
    name = Column(String, nullable=False)      # unique per camera, not globally
    polygon = Column(JSON, nullable=False)     # [[x, y], ...] in pixel coords
    created_at = Column(DateTime, default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "camera_id": self.camera_id,
            "name": self.name,
            "polygon": self.polygon,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
