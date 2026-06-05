"""Configuration: camera credentials (from .env) and conditions (from YAML)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class CameraConfig:
    ip: str
    user: str
    password: str
    rtsp_port: int = 554
    # 101 = main stream (high res), 102 = substream (smaller/faster -> use this)
    channel: str = "102"

    @property
    def rtsp_url(self) -> str:
        return (
            f"rtsp://{self.user}:{self.password}@{self.ip}:{self.rtsp_port}"
            f"/Streaming/Channels/{self.channel}"
        )

    @property
    def isapi_base(self) -> str:
        return f"http://{self.ip}"

    @classmethod
    def from_env(cls) -> "CameraConfig":
        ip = os.environ.get("CAM_IP")
        if not ip:
            raise RuntimeError("CAM_IP not set. Copy .env.example to .env and fill it in.")
        return cls(
            ip=ip,
            user=os.environ.get("CAM_USER", "admin"),
            password=os.environ.get("CAM_PASS", ""),
            rtsp_port=int(os.environ.get("CAM_RTSP_PORT", "554")),
            channel=os.environ.get("CAM_CHANNEL", "102"),
        )


@dataclass
class Action:
    type: str  # "relay" | "notify" | "log"
    # relay
    port: int | None = None
    state: str = "on"  # "on" | "off"
    duration_seconds: int | None = None
    # notify / log
    message: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Condition:
    id: str
    prompt: str                     # the natural-language thing to watch for
    actions: list[Action]
    confidence_min: float = 0.7     # ignore weak detections
    hits_needed: int = 3            # consecutive positive checks before firing (debounce)
    cooldown_seconds: int = 30      # min gap between fires
    enabled: bool = True


def load_conditions(path: str | Path = "conditions.yaml") -> list[Condition]:
    data = yaml.safe_load(Path(path).read_text())
    conditions: list[Condition] = []
    for c in data.get("conditions", []):
        actions = [Action(**a) for a in c.get("actions", [])]
        conditions.append(
            Condition(
                id=c["id"],
                prompt=c["prompt"],
                actions=actions,
                confidence_min=c.get("confidence_min", 0.7),
                hits_needed=c.get("hits_needed", 3),
                cooldown_seconds=c.get("cooldown_seconds", 30),
                enabled=c.get("enabled", True),
            )
        )
    return conditions


def save_conditions(conditions: list[Condition], path: str | Path = "conditions.yaml") -> None:
    out = {"conditions": []}
    for c in conditions:
        out["conditions"].append(
            {
                "id": c.id,
                "prompt": c.prompt,
                "confidence_min": c.confidence_min,
                "hits_needed": c.hits_needed,
                "cooldown_seconds": c.cooldown_seconds,
                "enabled": c.enabled,
                "actions": [
                    {k: v for k, v in vars(a).items() if v not in (None, "", {})}
                    for a in c.actions
                ],
            }
        )
    Path(path).write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True))
