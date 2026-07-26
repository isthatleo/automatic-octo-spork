"""Real ntfy.sh (or self-hosted ntfy) push-notification channel -- ported
from Hermes' ntfy platform integration. The simplest possible real Channel:
one HTTP POST, no auth required for the public ntfy.sh service (a topic name
is the whole "address"), optional bearer token for a self-hosted/protected
instance.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from channels.base import Channel
from channels.registry import register_channel_if_configured

logger = logging.getLogger(__name__)


class NtfyChannel(Channel):
    name = "ntfy"

    def __init__(self) -> None:
        self.server = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
        self.topic = os.getenv("NTFY_TOPIC")
        self.token = os.getenv("NTFY_TOKEN")

    def is_configured(self) -> bool:
        return bool(self.topic)

    async def send(self, message: str, **kw: Any) -> bool:
        if not self.topic:
            return False
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        title = kw.get("title")
        if title:
            headers["Title"] = title
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.server}/{self.topic}",
                    content=message.encode("utf-8"),
                    headers=headers,
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("NtfyChannel: send failed: %s", e)
            return False


register_channel_if_configured("ntfy", NtfyChannel)
