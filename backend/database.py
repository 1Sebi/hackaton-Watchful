"""SQLAlchemy + SQLite storage for conditions, events, and zones."""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DB_URL = os.environ.get("DATABASE_URL", "sqlite:///watcher.db")

_connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def _migrate_camera_id() -> None:
    """Add the ``camera_id`` column to pre-existing tables (SQLite, idempotent)."""
    if not DB_URL.startswith("sqlite"):
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        for table in ("conditions", "events", "zones"):
            try:
                cols = [row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))]
                if cols and "camera_id" not in cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN camera_id VARCHAR"))
            except Exception:
                pass


def init_db() -> None:
    """Create all tables (idempotent). Imports models to register them."""
    import backend.models  # noqa: F401  (registers Condition/Event/Zone on Base)

    Base.metadata.create_all(bind=engine)
    _migrate_camera_id()


def get_db():
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
