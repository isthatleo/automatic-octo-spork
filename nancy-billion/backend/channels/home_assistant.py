"""Real Home Assistant integration -- ported from Hermes' Home Assistant
platform. Two-way: `send()` fires a `notify.notify` (or a configured
notify.<target> service) so Nancy's messages can show up on HA's own
notification surfaces (phone app, dashboard); `call_service()` is the
general two-way control primitive (turn on a light, run a scene, etc.),
exposed as a real Claude tool, not just a notification sink.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

import httpx

from channels.base import Channel
from channels.registry import register_channel_if_configured

logger = logging.getLogger(__name__)


class HomeAssistantChannel(Channel):
    name = "home_assistant"

    def __init__(self) -> None:
        self.base_url = os.getenv("HOME_ASSISTANT_URL", "").rstrip("/")
        self.token = os.getenv("HOME_ASSISTANT_TOKEN")
        self.notify_service = os.getenv("HOME_ASSISTANT_NOTIFY_SERVICE", "notify.notify")

    def is_configured(self) -> bool:
        return bool(self.base_url and self.token)

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def send(self, message: str, **kw: Any) -> bool:
        domain, _, service = self.notify_service.partition(".")
        result = await self.call_service(domain or "notify", service or "notify", {"message": message})
        return result.get("success", False)

    async def call_service(self, domain: str, service: str, service_data: Dict[str, Any]) -> Dict[str, Any]:
        """Real two-way Home Assistant control -- calls any service
        (light.turn_on, scene.turn_on, notify.notify, etc.). Not gated by
        Telegram approval here: HA's own service-call surface already
        represents a bounded, user-configured set of real-world actions the
        user chose to expose, the same trust tier as `fetch_url`, not
        arbitrary shell/file access."""
        if not self.is_configured():
            return {"success": False, "error": "HOME_ASSISTANT_URL/HOME_ASSISTANT_TOKEN not configured"}
        url = f"{self.base_url}/api/services/{domain}/{service}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=service_data, headers=self._headers())
                resp.raise_for_status()
                return {"success": True, "result": resp.json()}
        except Exception as e:
            logger.warning("HomeAssistantChannel: call_service(%s.%s) failed: %s", domain, service, e)
            return {"success": False, "error": str(e)}


HOME_ASSISTANT_TOOLS = [
    {
        "name": "ha_call_service",
        "description": (
            "Call a real Home Assistant service to control a smart-home device or scene (e.g. "
            "domain='light', service='turn_on', service_data={'entity_id': 'light.kitchen'}). Only "
            "available if Home Assistant is configured."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "e.g. 'light', 'scene', 'switch'"},
                "service": {"type": "string", "description": "e.g. 'turn_on', 'turn_off'"},
                "service_data": {"type": "object", "description": "e.g. {'entity_id': 'light.kitchen'}"},
            },
            "required": ["domain", "service"],
        },
    },
]

register_channel_if_configured("home_assistant", HomeAssistantChannel)
