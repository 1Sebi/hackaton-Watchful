"""Action layer test — Hikvision relay, webhook, logger, dispatcher.

No camera/cloud needed: a local stand-in HTTP server captures requests so we can
verify the exact ISAPI relay URL/body and the webhook POST, fully offline.

Usage:  python scripts/test_hikvision_relay.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.actions.dispatcher import ActionDispatcher  # noqa: E402
from backend.actions.hikvision import HikvisionClient  # noqa: E402
from backend.actions.logger import EventLogger  # noqa: E402
from backend.actions.webhook import WebhookSender  # noqa: E402

_CAPTURED: list[dict] = []


class _Handler(BaseHTTPRequestHandler):
    def _capture(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", "ignore")
        _CAPTURED.append({"method": self.command, "path": self.path, "body": body})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    do_PUT = _capture
    do_POST = _capture

    def log_message(self, *a):  # silence
        pass


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    host = f"127.0.0.1:{server.server_port}"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    checks = {}

    # 1) Hikvision relay -> correct ISAPI URL + body
    hv = HikvisionClient(ip=host, user="admin", password="pass")
    _CAPTURED.clear()
    ok = hv.relay_set(port=1, state="high")
    last = _CAPTURED[-1] if _CAPTURED else {}
    checks["relay_ok"] = ok is True
    checks["relay_url"] = last.get("method") == "PUT" and last.get("path") == "/ISAPI/System/IO/outputs/1/trigger"
    checks["relay_body"] = "<outputState>high</outputState>" in last.get("body", "")
    print(f"[1] relay -> {last.get('method')} {last.get('path')} ok={ok}")

    # 2) Webhook generic POST
    wh = WebhookSender(url=f"http://{host}/hook", kind="generic")
    _CAPTURED.clear()
    wok = wh.send("4 people in pool", title="The Watcher")
    checks["webhook_ok"] = wok is True and _CAPTURED and "4 people in pool" in _CAPTURED[-1]["body"]

    # 3) Logger writes JSONL
    tmp_log = os.path.join(tempfile.gettempdir(), "watcher_events_test.jsonl")
    if os.path.exists(tmp_log):
        os.remove(tmp_log)
    lg = EventLogger(tmp_log)
    rec = lg.log({"event": "test", "confidence": 0.9})
    with open(tmp_log, encoding="utf-8") as f:
        line = f.readline()
    checks["logger"] = '"event": "test"' in line and "ts" in rec
    os.remove(tmp_log)

    # 4) Dispatcher routes all three action types
    disp = ActionDispatcher(
        hikvision=HikvisionClient(ip=host, user="admin", password="pass"),
        webhook=WebhookSender(url=f"http://{host}/hook"),
        logger=EventLogger(os.path.join(tempfile.gettempdir(), "watcher_disp_test.jsonl")),
    )
    _CAPTURED.clear()
    r_relay = asyncio.run(disp.dispatch({"type": "relay", "port": 2}, {"reason": "x"}))
    r_hook = asyncio.run(disp.dispatch({"type": "webhook", "message": "hi"}, {}))
    r_log = asyncio.run(disp.dispatch({"type": "log", "message": "logged"}, {"confidence": 0.8}))
    relay_path_ok = any(c["path"] == "/ISAPI/System/IO/outputs/2/trigger" for c in _CAPTURED)
    checks["dispatch_relay"] = r_relay["ok"] and relay_path_ok
    checks["dispatch_webhook"] = r_hook["ok"]
    checks["dispatch_log"] = r_log["ok"] and r_log["type"] == "log"
    print(f"[4] dispatch relay={r_relay} webhook={r_hook['ok']} log={r_log['ok']}")

    server.shutdown()

    passed = 0
    for k, v in checks.items():
        print(f"   [{'OK' if v else 'XX'}] {k}")
        passed += bool(v)
    print(f"RESULT: {passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
