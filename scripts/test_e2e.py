"""End-to-end: add a condition -> the agent fires it -> it shows up in the log.

Uses an "absence" condition ("no one present for 2 seconds") so the trigger
fires on an empty scene with no person required. Proves the full chain:
NL -> compile -> pipeline eval -> anti-false-positive -> DB event -> /events
(the same /events + /ws/events the frontend EventLog reads).

Usage:  python scripts/test_e2e.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmp = os.path.join(tempfile.gettempdir(), "watchful_e2e.db")
if os.path.exists(_tmp):
    os.remove(_tmp)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}"

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


def main() -> int:
    checks = {}
    with TestClient(app) as client:
        r = client.post("/conditions",
                        json={"text": "no one is present for 2 seconds", "action": {"type": "log"}})
        pred = r.json().get("predicate", {})
        print(f"compiled: {pred.get('type')} via {pred.get('evaluator')} params={pred.get('params')}")
        checks["compiled_absence"] = pred.get("type") == "ABSENCE_FOR_DURATION"

        # wait for the agent to fire it (empty scene -> ~2s + debounce)
        got = None
        for _ in range(30):
            evs = client.get("/events").json()
            if evs:
                got = evs[0]
                break
            time.sleep(0.5)
        print(f"event: {got}")
        checks["trigger_logged"] = got is not None and got.get("detected") is True

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
