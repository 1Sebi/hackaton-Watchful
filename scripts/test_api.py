"""End-to-end API test via FastAPI TestClient (starts the real pipeline).

Exercises REST CRUD, MJPEG + snapshot, and WebSocket state. Uses a throwaway DB
so it doesn't touch your real watcher.db. Needs a camera (VIDEO_SOURCE).

Usage:  python scripts/test_api.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# isolate DB before importing the app
_tmp = os.path.join(tempfile.gettempdir(), "watcher_api_test.db")
if os.path.exists(_tmp):
    os.remove(_tmp)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}"

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


def main() -> int:
    checks = {}
    with TestClient(app) as client:  # triggers lifespan -> pipeline.start()
        checks["root"] = client.get("/").status_code == 200
        checks["docs"] = client.get("/docs").status_code == 200
        checks["openapi"] = client.get("/openapi.json").status_code == 200

        r = client.post("/conditions/preview", json={"text": "someone raises their hand"})
        checks["preview_pose"] = r.status_code == 200 and r.json()["evaluator"] == "pose"

        r = client.post("/conditions", json={"text": "more than 0 people", "action": {"type": "log"}})
        checks["create_yolo"] = r.status_code == 200 and r.json()["predicate"]["evaluator"] == "yolo"
        cid = r.json()["id"]

        checks["list_conditions"] = len(client.get("/conditions").json()) >= 1
        checks["zone"] = client.post("/zones", json={"name": "door", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]}).status_code == 200
        checks["events"] = client.get("/events").status_code == 200

        # snapshot once the pipeline has a frame
        snap = False
        for _ in range(30):
            s = client.get("/stream/snapshot.jpg")
            if s.status_code == 200 and len(s.content) > 1000 and s.content[:2] == b"\xff\xd8":
                snap = True
                break
            time.sleep(0.5)
        checks["snapshot_jpeg"] = snap

        # MJPEG route registered (live byte stream verified separately against a
        # real uvicorn server — TestClient blocks on the infinite generator, so we
        # don't consume it here; snapshot.jpg above already proves real JPEG frames).
        checks["mjpeg_route"] = any(getattr(r, "path", "") == "/stream/live.mjpg" for r in app.routes)

        # WebSocket state
        with client.websocket_connect("/ws/state") as ws:
            msg = ws.receive_json()
            checks["ws_state"] = msg.get("running") is True and "fps" in msg

        checks["delete"] = client.delete(f"/conditions/{cid}").status_code == 200

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
