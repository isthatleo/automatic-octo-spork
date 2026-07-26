"""Real ClickClack channel -- ported from OpenClaw's ClickClack extension.
Claim-code onboarding (a one-time code exchanged for a durable API key,
matching ClickClack's own pairing flow) plus a real send API once paired.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

from channels.base import Channel
from channels.registry import register_channel_if_configured

logger = logging.getLogger(__name__)

CLICKCLACK_API_BASE = os.getenv("CLICKCLACK_API_BASE", "https://api.clickclack.chat")


async def claim_device(claim_code: str) -> Optional[str]:
    """Exchanges a one-time claim code (obtained from the ClickClack app/UI)
    for a durable API key -- the real onboarding flow, not a stub. Returns
    the key on success so the caller can persist it as CLICKCLACK_API_KEY;
    returns None on any failure."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{CLICKCLACK_API_BASE}/v1/claim", json={"code": claim_code})
            resp.raise_for_status()
            return resp.json().get("api_key")
    except Exception as e:
        logger.warning("clickclack claim_device failed: %s", e)
        return None


class ClickClackChannel(Channel):
    name = "clickclack"

    def __init__(self) -> None:
        self.api_key = os.getenv("CLICKCLACK_API_KEY")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def send(self, message: str, **kw: Any) -> bool:
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{CLICKCLACK_API_BASE}/v1/messages",
                    json={"text": message},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("ClickClackChannel: send failed: %s", e)
            return False


register_channel_if_configured("clickclack", ClickClackChannel)
