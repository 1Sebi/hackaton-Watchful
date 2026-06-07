"""Webhook notifications — ntfy.sh, Discord, or a generic JSON POST."""
from __future__ import annotations

import os
from typing import Optional

import requests


class WebhookSender:
    def __init__(self, url: Optional[str] = None, kind: str = "generic", timeout: float = 5.0) -> None:
        self.url = url if url is not None else os.environ.get("WEBHOOK_URL", "")
        self.kind = kind
        self.timeout = timeout

    def send(
        self,
        message: str,
        title: str = "The Watcher",
        url: Optional[str] = None,
        priority: Optional[str] = None,
        tags: Optional[str] = None,
    ) -> bool:
        target = url or self.url
        if not target:
            raise RuntimeError("no webhook url configured")
        kind = self.kind
        try:
            if kind == "discord" or "discord.com" in target:
                resp = requests.post(target, json={"content": f"**{title}**\n{message}"},
                                     timeout=self.timeout)
            elif kind == "ntfy" or "ntfy" in target:
                # HTTP headers must be latin-1; strip emoji/unicode from the Title
                # (the emoji is carried by the Tags header instead).
                safe_title = title.encode("ascii", "ignore").decode().strip() or "The Watcher"
                headers = {"Title": safe_title}
                if priority:  # ntfy: min|low|default|high|urgent
                    headers["Priority"] = priority
                if tags:  # ntfy: comma-separated emoji shortcodes, e.g. "warning"
                    headers["Tags"] = tags
                resp = requests.post(target, data=message.encode("utf-8"),
                                     headers=headers, timeout=self.timeout)
            else:
                resp = requests.post(target, json={"title": title, "message": message},
                                     timeout=self.timeout)
            return resp.status_code < 300
        except requests.RequestException:
            return False
