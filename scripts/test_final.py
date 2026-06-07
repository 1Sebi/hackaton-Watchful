"""Final webcam check — two conditions behave correctly on the live feed:

  1. "no one is present for 2 seconds"  -> SHOULD fire on an empty scene
  2. "more than 0 people"               -> should NOT fire on an empty scene

Proves the agent fires the right rule and stays quiet on the other (no false
trigger). Usage:  python scripts/test_final.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmp = os.path.join(tempfile.gettempdir(), "watcher_final.db")
if os.path.exists(_tmp):
    os.remove(_tmp)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}"

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


def main() -> int:
    checks = {}
    with TestClient(app) as client:
        a = client.post("/conditions", json={"text": "no one is present for 2 seconds",
                                             "action": {"type": "log"}}).json()
        b = client.post("/conditions", json={"text": "more than 0 people",
                                             "action": {"type": "log"}}).json()
        print(f"absence -> {a['predicate']['type']}/{a['predicate']['evaluator']}")
        print(f"count   -> {b['predicate']['type']}/{b['predicate']['evaluator']}")

        fired_ids = set()
        for _ in range(30):
            for ev in client.get("/events").json():
                fired_ids.add(ev["condition_id"])
            if a["id"] in fired_ids:
                break
            time.sleep(0.5)

        checks["absence_fired"] = a["id"] in fired_ids        # empty scene -> should fire
        checks["count_quiet"] = b["id"] not in fired_ids      # empty scene -> no false trigger
        print(f"fired condition ids: {sorted(fired_ids)}")

    try:
        os.remove(_tmp)
    except OSError:
        pass

    passed = sum(checks.values())
    for k, v in checks.items():
        print(f"   [{'OK' if v else 'XX'}] {k}")
    print(f"RESULT: {passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
