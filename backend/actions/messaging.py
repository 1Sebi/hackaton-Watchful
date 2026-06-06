"""Messaging actions — Telegram (Bot API) and WhatsApp (CallMeBot).

Both are simple HTTP calls and run inside the dispatcher's thread pool. They are
config-driven (token/chat id / phone+apikey from .env) and fail soft: if not
configured, they return a clear error instead of raising, so a misconfigured
notification never breaks the agent loop.
"""
from __future__ import annotations

from urllib.parse import quote

import requests

from backend.config import settings

_TIMEOUT = 6.0


def send_telegram(text: str, token: str = "", chat_id: str = "") -> dict:
    """Send a Telegram message via the Bot API.

    token/chat_id default to settings (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID).
    """
    token = token or settings.TELEGRAM_BOT_TOKEN
    chat_id = chat_id or settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return {"ok": False, "error": "telegram not configured (TELEGRAM_BOT_TOKEN/CHAT_ID)"}
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=_TIMEOUT,
        )
        return {"ok": r.status_code == 200, "status": r.status_code}
    except requests.RequestException as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


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
