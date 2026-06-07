"""Messaging actions — Telegram (Bot API) and WhatsApp (CallMeBot).

Both are simple HTTP calls and run inside the dispatcher's thread pool. They are
config-driven (token/chat id / phone+apikey from .env) and fail soft: if not
configured, they return a clear error instead of raising, so a misconfigured
notification never breaks the agent loop.
"""
from __future__ import annotations

import re
from urllib.parse import quote

import requests

from backend.config import settings

_TIMEOUT = 6.0


def send_telegram(text: str, token: str = "", chat_id: str = "") -> dict:
    """Send a Telegram message via the Bot API to one or MORE chats.

    token/chat_id default to settings (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).
    ``chat_id`` may be a comma/space-separated list ("123,456") so the same alert
    reaches several recipients/accounts (a teammate's phone + your laptop account).
    Telegram already syncs one account across its own devices; multiple IDs are for
    multiple *accounts*.
    """
    token = token or settings.TELEGRAM_BOT_TOKEN
    chat_id = chat_id or settings.TELEGRAM_CHAT_ID
    ids = [c.strip() for c in re.split(r"[,\s]+", str(chat_id)) if c.strip()]
    if not token or not ids:
        return {"ok": False, "error": "telegram not configured (TELEGRAM_BOT_TOKEN/CHAT_ID)"}
    results, sent, errors = [], 0, []
    for cid in ids:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": cid, "text": text, "disable_web_page_preview": True},
                timeout=_TIMEOUT,
            )
            ok = r.status_code == 200
            results.append({"chat_id": cid, "ok": ok, "status": r.status_code})
            if ok:
                sent += 1
            else:
                errors.append(f"{cid}:{r.status_code}")
        except requests.RequestException as e:  # noqa: BLE001
            results.append({"chat_id": cid, "ok": False, "error": str(e)})
            errors.append(f"{cid}:{e}")
    # ok if at least one recipient got it; surface per-chat detail for debugging
    out: dict = {"ok": sent > 0, "sent": sent, "recipients": len(ids), "results": results}
    if errors:
        out["error"] = "; ".join(errors)
    return out


def send_telegram_video(path: str, caption: str = "", token: str = "", chat_id: str = "") -> dict:
    """Upload an MP4 to one or more Telegram chats via the Bot API (sendVideo).

    Used by the person-tracking feature to deliver a recorded clip. Multipart upload;
    chat_id may be comma/space-separated for several recipients. The user explicitly
    opted into sending footage here (the default elsewhere is text-only)."""
    token = token or settings.TELEGRAM_BOT_TOKEN
    chat_id = chat_id or settings.TELEGRAM_CHAT_ID
    ids = [c.strip() for c in re.split(r"[,\s]+", str(chat_id)) if c.strip()]
    if not token or not ids:
        return {"ok": False, "error": "telegram not configured (TELEGRAM_BOT_TOKEN/CHAT_ID)"}
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:  # noqa: BLE001
        return {"ok": False, "error": f"clip not readable: {e}"}
    sent, errors = 0, []
    for cid in ids:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendVideo",
                data={"chat_id": cid, "caption": caption[:1024]},
                files={"video": ("track.mp4", data, "video/mp4")},
                timeout=60,
            )
            if r.status_code == 200:
                sent += 1
            else:
                errors.append(f"{cid}:{r.status_code} {r.text[:120]}")
        except requests.RequestException as e:  # noqa: BLE001
            errors.append(f"{cid}:{e}")
    out: dict = {"ok": sent > 0, "sent": sent, "recipients": len(ids)}
    if errors:
        out["error"] = "; ".join(errors)
    return out


def send_whatsapp(text: str, phone: str = "", apikey: str = "") -> dict:
    """Send a WhatsApp message via CallMeBot's free API.

    phone/apikey default to settings (WHATSAPP_PHONE / WHATSAPP_APIKEY). One-time
    setup: message the CallMeBot number to receive your apikey (callmebot.com/whatsapp).
    """
    phone = phone or settings.WHATSAPP_PHONE
    apikey = apikey or settings.WHATSAPP_APIKEY
    if not phone or not apikey:
        return {"ok": False, "error": "whatsapp not configured (WHATSAPP_PHONE/APIKEY)"}
    try:
        r = requests.get(
            "https://api.callmebot.com/whatsapp.php"
            f"?phone={quote(phone)}&text={quote(text)}&apikey={quote(apikey)}",
            timeout=_TIMEOUT,
        )
        return {"ok": r.status_code == 200, "status": r.status_code}
    except requests.RequestException as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
