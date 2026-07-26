"""Real DeepInfra image-generation adapter -- a synchronous (non-queue)
OpenAI-images-compatible endpoint, second image vendor alongside fal.ai."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

import httpx

from providers.base import ImageProvider
from providers.registry import register_if_configured

logger = logging.getLogger(__name__)

DEEPINFRA_MODEL = os.getenv("DEEPINFRA_IMAGE_MODEL", "stabilityai/sd3.5")


class DeepInfraImageProvider(ImageProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("DEEPINFRA_API_KEY")
        if not self.api_key:
            raise RuntimeError("DEEPINFRA_API_KEY not set")

    async def generate(self, prompt: str, **kw: Any) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"https://api.deepinfra.com/v1/inference/{DEEPINFRA_MODEL}",
                    json={"prompt": prompt, **kw},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("DeepInfraImageProvider: generate failed: %s", e)
            return {"success": False, "error": str(e)}

        images = data.get("images") or []
        if not images:
            return {"success": False, "error": "DeepInfra returned no images"}
        # DeepInfra returns base64 data URIs for this model family.
        return {"success": True, "data_base64": images[0]}


register_if_configured("image", "deepinfra", "DEEPINFRA_API_KEY", DeepInfraImageProvider)
