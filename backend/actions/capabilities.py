"""Action capabilities + validation — the other half of "make it doable".

A rule that compiles perfectly is still useless if its ACTION can't fire: pick
"Telegram" with no token in .env, or "Relay" with no NVR, and the agent triggers
into the void. This module:

  * ``action_capabilities()`` — lists every action the editor can offer and whether
    it is actually wired up RIGHT NOW (creds present), with a setup hint if not.
  * ``validate_action()`` — checks one action config before save: hard-errors on a
    broken action (unknown type, webhook with no URL), soft-warns on a not-yet-
    configured one (saves, but tells you it won't fire until you add the creds).

The UI shows these so you can never pick a dead action without knowing.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from backend.config import settings


def _relay_configured() -> bool:
    # the relay fires through HikvisionClient(), which reads HIKVISION_IP/PASS
    return bool(os.environ.get("HIKVISION_IP") and os.environ.get("HIKVISION_PASS"))


def _telegram_configured() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)


def _whatsapp_configured() -> bool:
    return bool(settings.WHATSAPP_PHONE and settings.WHATSAPP_APIKEY)


def _ntfy_configured() -> bool:
    return bool(settings.NTFY_TOPIC)


def _webhook_configured() -> bool:
    return bool(os.environ.get("WEBHOOK_URL"))


# field specs let the editor render the right inputs per action
_RELAY_FIELDS = [
    {"key": "port", "label": "Relay port", "type": "number", "default": 1},
    {"key": "mode", "label": "Action", "type": "select", "default": "on",
     "options": [
         {"value": "on", "label": "Turn ON (high)"},
         {"value": "off", "label": "Turn OFF (low)"},
         {"value": "pulse", "label": "Pulse for N seconds"},
     ]},
    {"key": "duration", "label": "Pulse seconds", "type": "number", "default": 3,
     "when": {"mode": "pulse"}},
]


def action_capabilities() -> List[Dict[str, Any]]:
    """Every selectable action + whether it can fire now (for the editor)."""
    return [
        {"type": "log", "label": "Log only", "configured": True, "always": True,
         "hint": "Records the event in the activity feed. Always works.",
         "fields": []},
        {"type": "ntfy", "label": "Phone push (ntfy)", "configured": _ntfy_configured(),
         "hint": "Free phone notification. Set NTFY_TOPIC in .env and subscribe to it "
                 "in the ntfy app.",
         "fields": []},
        {"type": "telegram", "label": "Telegram", "configured": _telegram_configured(),
         "hint": "Set TELEGRAM_BOT_TOKEN (@BotFather) and TELEGRAM_CHAT_ID (@userinfobot) "
                 "in .env.",
         "fields": []},
        {"type": "whatsapp", "label": "WhatsApp", "configured": _whatsapp_configured(),
         "hint": "Set WHATSAPP_PHONE and WHATSAPP_APIKEY in .env (free via callmebot.com).",
         "fields": []},
        {"type": "relay", "label": "Relay (door / light / siren)", "configured": _relay_configured(),
         "hint": "Switches a Hikvision relay output. Needs HIKVISION_IP / HIKVISION_PASS in .env.",
         "fields": _RELAY_FIELDS},
        {"type": "webhook", "label": "Webhook (Discord / custom)", "configured": _webhook_configured(),
         "hint": "POSTs to any URL. Provide a URL on the rule or set WEBHOOK_URL in .env.",
         "fields": [{"key": "url", "label": "URL", "type": "text", "default": ""}]},
    ]


def normalize_action(action: Dict[str, Any] | None) -> Dict[str, Any]:
    """Canonicalize an editor action into the dispatcher's expected shape.

    The editor sends relay as {type:'relay', port, mode, duration}; the dispatcher
    speaks {type:'relay', port, state, duration}. Translate mode -> state here so
    both ends stay simple.
    """
    a = dict(action or {"type": "log"})
    kind = (a.get("type") or "log").lower()
    a["type"] = kind
    if kind == "relay":
        mode = (a.pop("mode", None) or "on").lower()
        a["port"] = int(a.get("port", 1) or 1)
        if mode == "off":
            a["state"] = "low"
            a.pop("duration", None)
        elif mode == "pulse":
            a["state"] = "high"
            a["duration"] = int(a.get("duration", 3) or 3)
        else:  # on
            a["state"] = "high"
            a.pop("duration", None)
    return a


def validate_action(action: Dict[str, Any] | None) -> Dict[str, Any]:
    """Return {ok, error, warnings}. ok=False blocks the save (truly broken action)."""
    a = action or {"type": "log"}
    kind = (a.get("type") or "log").lower()
    known = {c["type"] for c in action_capabilities()} | {"relay_on", "relay_off"}
    if kind not in known:
        return {"ok": False, "error": f"Unknown action '{kind}'.", "warnings": []}

    warnings: List[str] = []
    if kind in ("relay", "relay_on", "relay_off") and not _relay_configured():
        warnings.append("Relay not configured (HIKVISION_IP/PASS) — the rule saves, "
                        "but the relay won't switch until you set the credentials.")
    elif kind == "telegram" and not _telegram_configured() and not a.get("token"):
        warnings.append("Telegram not configured — set TELEGRAM_BOT_TOKEN/CHAT_ID in "
                        ".env, or this rule won't send.")
    elif kind == "whatsapp" and not _whatsapp_configured() and not a.get("phone"):
        warnings.append("WhatsApp not configured — set WHATSAPP_PHONE/APIKEY in .env, "
                        "or this rule won't send.")
    elif kind == "ntfy" and not _ntfy_configured() and not a.get("url"):
        warnings.append("No ntfy topic configured — set NTFY_TOPIC in .env, or this "
                        "rule won't push.")
    elif kind == "webhook" and not a.get("url") and not _webhook_configured():
        return {"ok": False, "error": "Webhook needs a URL (on the rule or WEBHOOK_URL "
                "in .env).", "warnings": []}
    return {"ok": True, "error": None, "warnings": warnings}
