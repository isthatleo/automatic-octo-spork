"""Real Telegram device-pairing flow.

Before this, connecting a Telegram chat meant manually calling getUpdates
and copy-pasting a chat_id into .env by hand (documented in telegram_bot.py's
module docstring). This gives the Pairing page an actual working flow: click
"Start pairing", message a one-time code to the bot, and the backend picks
up the resulting chat_id itself and writes it to .env -- same real
allowlisted-write mechanism /config/keys uses (dotenv.set_key), not a fake
"paired!" response that doesn't persist anything.

Deliberately independent of telegram_bot.py's TelegramNotifier singleton:
that object is constructed once at import time and treats a missing
TELEGRAM_CHAT_ID as a permanent, unrecoverable "not configured" state (by
design, so a stray callback can never message a corrupted config). Pairing
is exactly the case where chat_id is legitimately still unknown, so this
module talks to the Telegram Bot API directly with just the token.
"""

from __future__ import annotations

import logging
import os
import random
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
PAIRING_TTL_S = 300  # 5 minutes to message the code before it expires


class _PairingSession:
    code: Optional[str] = None
    started_at: float = 0.0
    result_chat_id: Optional[str] = None


_session = _PairingSession()


def start_pairing() -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return {"success": False, "error": "TELEGRAM_BOT_TOKEN not set — add it on the Keys page first."}
    code = f"{random.randint(0, 999999):06d}"
    _session.code = code
    _session.started_at = time.time()
    _session.result_chat_id = None
    return {"success": True, "code": code, "expires_in": PAIRING_TTL_S}


async def check_pairing() -> dict:
    """Polls getUpdates once for a message containing the pending code from
    any chat, claims that chat's id, and writes it to .env for real."""
    if not _session.code:
        return {"success": True, "paired": False, "pending": False}

    if time.time() - _session.started_at > PAIRING_TTL_S:
        _session.code = None
        return {"success": True, "paired": False, "pending": False, "expired": True}

    if _session.result_chat_id:
        return {"success": True, "paired": True, "chat_id": _session.result_chat_id}

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return {"success": False, "error": "TELEGRAM_BOT_TOKEN not set"}

    try:
        async with httpx.AsyncClient(base_url=f"{TELEGRAM_API}/bot{token}", timeout=10.0) as client:
            resp = await client.get("/getUpdates", params={"limit": 50})
            data = resp.json()
    except Exception as e:
        logger.warning("Pairing check failed to reach Telegram: %s", e)
        return {"success": True, "paired": False, "pending": True}

    for update in data.get("result", []):
        message = update.get("message") or {}
        text = (message.get("text") or "").strip()
        if text == _session.code:
            chat_id = str(message.get("chat", {}).get("id", ""))
            if not chat_id:
                continue
            from dotenv import set_key
            env_path = Path(__file__).parent / ".env"
            if not env_path.exists():
                env_path.touch()
            set_key(str(env_path), "TELEGRAM_CHAT_ID", chat_id)
            os.environ["TELEGRAM_CHAT_ID"] = chat_id
            _session.result_chat_id = chat_id
            _session.code = None
            logger.info("Telegram pairing succeeded, chat_id saved to .env")
            return {"success": True, "paired": True, "chat_id": chat_id}

    return {"success": True, "paired": False, "pending": True}
