"""Append-only JSONL event logger (local, thread-safe)."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Union


class EventLogger:
    def __init__(self, path: Union[str, Path] = "events.jsonl") -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def log(self, event: dict) -> dict:
        record = {"ts": datetime.now(timezone.utc).isoformat(), **event}
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return record
