"""Database CRUD test against a throwaway SQLite file.

Create / read / update / delete for Condition, Zone, Event (incl. JSON columns
and FK). Usage:  python scripts/test_db.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# point the DB at a temp file BEFORE importing backend.database
_tmp = os.path.join(tempfile.gettempdir(), "watchful_test.db")
if os.path.exists(_tmp):
    os.remove(_tmp)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}"

from backend.database import SessionLocal, engine, init_db  # noqa: E402
from backend.models import Condition, Event, Zone  # noqa: E402


def main() -> int:
    init_db()
    db = SessionLocal()
    checks = {}

    # CREATE
    c = Condition(text="more than 3 people in the pool",
                  predicate={"type": "COUNT_GT", "params": {"value": 3}, "evaluator": "yolo"},
                  action={"type": "webhook", "url": "https://ntfy.sh/demo"})
    z = Zone(name="jacuzzi", polygon=[[0, 0], [100, 0], [100, 100], [0, 100]])
    db.add_all([c, z])
    db.commit()
    db.refresh(c)
    db.refresh(z)
    e = Event(condition_id=c.id, detected=True, confidence=0.91,
              reason="count 4 > 3", action_taken="webhook")
    db.add(e)
    db.commit()
    db.refresh(e)
    checks["create_ids"] = c.id is not None and z.id is not None and e.id is not None

    # READ (incl. JSON round-trip + FK)
    got = db.get(Condition, c.id)
    checks["json_roundtrip"] = got.predicate["params"]["value"] == 3 and got.action["type"] == "webhook"
    checks["zone_json"] = db.get(Zone, z.id).polygon[2] == [100, 100]
    checks["fk_event"] = db.query(Event).filter_by(condition_id=c.id).count() == 1

    # UPDATE
    got.enabled = False
    db.commit()
    checks["update"] = db.get(Condition, c.id).enabled is False

    # DELETE
    db.delete(e)
    db.commit()
    checks["delete"] = db.query(Event).count() == 0

    db.close()
    engine.dispose()
    try:
        os.remove(_tmp)
    except OSError:
        pass

    passed = 0
    for k, v in checks.items():
        print(f"   [{'OK' if v else 'XX'}] {k}")
        passed += bool(v)
    print(f"RESULT: {passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
