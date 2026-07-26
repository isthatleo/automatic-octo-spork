"""Real fal.ai image-generation adapter -- queue-based API (submit, poll,
retrieve), the pattern most fal.ai model endpoints share."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict

import httpx

from providers.base import ImageProvider
from providers.registry import register_if_configured

logger = logging.getLogger(__name__)

FAL_MODEL = os.getenv("FAL_IMAGE_MODEL", "fal-ai/flux/schnell")
FAL_POLL_INTERVAL_S = 1.5
FAL_POLL_TIMEOUT_S = 60.0


class FalImageProvider(ImageProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("FAL_API_KEY")
        if not self.api_key:
            raise RuntimeError("FAL_API_KEY not set")

    async def generate(self, prompt: str, **kw: Any) -> Dict[str, Any]:
        headers = {"Authorization": f"Key {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                submit = await client.post(
                    f"https://queue.fal.run/{FAL_MODEL}", json={"prompt": prompt, **kw}, headers=headers,
                )
                submit.raise_for_status()
                req = submit.json()
                status_url = req["status_url"]
                result_url = req["response_url"]

                elapsed = 0.0
                while elapsed < FAL_POLL_TIMEOUT_S:
                    status_resp = await client.get(status_url, headers=headers)
                    status_resp.raise_for_status()
                    if status_resp.json().get("status") == "COMPLETED":
                        break
                    await asyncio.sleep(FAL_POLL_INTERVAL_S)
                    elapsed += FAL_POLL_INTERVAL_S
                else:
                    return {"success": False, "error": f"fal.ai generation timed out after {FAL_POLL_TIMEOUT_S:.0f}s"}

                result_resp = await client.get(result_url, headers=headers)
                result_resp.raise_for_status()
                result = result_resp.json()
                images = result.get("images") or []
                if not images:
                    return {"success": False, "error": "fal.ai returned no images"}
                return {"success": True, "url": images[0].get("url")}
        except Exception as e:
            logger.warning("FalImageProvider: generate failed: %s", e)
            return {"success": False, "error": str(e)}


register_if_configured("image", "fal", "FAL_API_KEY", FalImageProvider)
