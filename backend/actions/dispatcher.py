"""ActionDispatcher — async coordinator that routes an action config to an effect.

Action config (stored per Condition) looks like:
    {"type": "relay",   "port": 1, "state": "high", "duration": 3}
    {"type": "webhook", "url": "https://ntfy.sh/...", "kind": "ntfy", "message": "..."}
    {"type": "log",     "message": "..."}

Blocking HTTP (requests) is run in a thread so the agent loop never stalls.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from backend.actions.hikvision import HikvisionClient
from backend.actions.logger import EventLogger
from backend.actions.webhook import WebhookSender


class ActionDispatcher:
    def __init__(
        self,
        hikvision: Optional[HikvisionClient] = None,
        webhook: Optional[WebhookSender] = None,
        logger: Optional[EventLogger] = None,
    ) -> None:
        self.hikvision = hikvision
        self.webhook = webhook
        self.logger = logger or EventLogger()

    async def dispatch(self, action: Optional[dict], context: Optional[dict] = None) -> dict:
        action = action or {"type": "log"}
        kind = (action.get("type") or "log").lower()
        ctx = context or {}
        message = action.get("message") or ctx.get("reason") or "Watchful trigger"
        try:
            if kind == "relay":
                hv = self.hikvision or HikvisionClient()
                ok = await asyncio.to_thread(
                    hv.relay_set, int(action.get("port", 1)),
                    action.get("state", "high"), action.get("duration"),
                )
                return {"type": "relay", "ok": ok}
            if kind == "webhook":
                wh = self.webhook or WebhookSender(url=action.get("url"), kind=action.get("kind", "generic"))
                ok = await asyncio.to_thread(wh.send, message, action.get("title", "Watchful"), action.get("url"))
                return {"type": "webhook", "ok": ok}
            # default: structured log
            record = self.logger.log({"event": message, **ctx})
            return {"type": "log", "ok": True, "record": record}
        except Exception as e:  # noqa: BLE001
            return {"type": kind, "ok": False, "error": str(e)}
