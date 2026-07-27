"""Real WhatsApp channel -- Meta's actual WhatsApp Business Cloud API
(graph.facebook.com/{version}/{phone_number_id}/messages), the free-tier,
no-vendor-lock-in path Meta itself documents for developers (as opposed to
a paid BSP like Twilio). Requires a real Meta developer app with the
WhatsApp product added (developers.facebook.com), which provides a test
phone_number_id and access token during development.

Honesty note: the Cloud API's 24-hour customer-service window means a
free-form text message like this only delivers if the recipient has
messaged your WhatsApp number within the last 24 hours -- outside that
window Meta requires a pre-approved template message instead. This sends
the real free-form call either way and surfaces Meta's real error if the
window has lapsed, rather than silently pretending it worked.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from channels.base import Channel
from channels.registry import register_channel_if_configured

logger = logging.getLogger(__name__)

WHATSAPP_API_VERSION = "v20.0"


class WhatsAppChannel(Channel):
    name = "whatsapp"

    def __init__(self) -> None:
        self.access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
        self.default_to = os.getenv("WHATSAPP_DEFAULT_TO")

    def is_configured(self) -> bool:
        return bool(self.access_token and self.phone_number_id)

    async def send(self, message: str, **kw: Any) -> bool:
        if not self.access_token or not self.phone_number_id:
            return False
        to_number = kw.get("to") or self.default_to
        if not to_number:
            logger.warning("WhatsAppChannel: no recipient specified and no WHATSAPP_DEFAULT_TO set")
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{self.phone_number_id}/messages",
                    json={
                        "messaging_product": "whatsapp",
                        "to": to_number,
                        "type": "text",
                        "text": {"body": message},
                    },
                    headers={"Authorization": f"Bearer {self.access_token}"},
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("WhatsAppChannel: send failed: %s", e)
            return False


register_channel_if_configured("whatsapp", WhatsAppChannel)
