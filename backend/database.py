"""SQLAlchemy + SQLite storage for conditions, events, and zones."""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DB_URL = os.environ.get("DATABASE_URL", "sqlite:///watchful.db")

_connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}
engine = create_engine(DB_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def init_db() -> None:
    """Create all tables (idempotent). Imports models to register them."""
    import backend.models  # noqa: F401  (registers Condition/Event/Zone on Base)

    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
