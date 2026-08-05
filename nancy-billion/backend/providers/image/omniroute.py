"""OmniRoute (github.com/diegosouzapw/OmniRoute) image-generation adapter --
the same local gateway llm.py's OmniRouteLLM already routes chat through,
extended to its OpenAI-compatible /v1/images/generations endpoint (Grok
Imagine, Freepik, Adobe Firefly, Segmind, ... behind one call). Registered
unconditionally (unless DISABLE_OMNIROUTE=1) rather than via
register_if_configured -- like OmniRouteLLM, this is a local keyless gateway,
not a vendor that needs its own API key here; an unreachable gateway just
means this adapter's calls fail fast and callers fall through to another
registered image provider (fal/deepinfra) exactly as intended by the
provider-registry pattern (providers/registry.py).
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any, Dict

import httpx

from providers.base import ImageProvider
from providers.registry import register

logger = logging.getLogger(__name__)

OMNIROUTE_URL = os.getenv("OMNIROUTE_URL", "http://localhost:20128").rstrip("/")
OMNIROUTE_IMAGE_MODEL = os.getenv("OMNIROUTE_IMAGE_MODEL", "auto")


class OmniRouteImageProvider(ImageProvider):
    def __init__(self) -> None:
        self.base_url = OMNIROUTE_URL
        self.model = OMNIROUTE_IMAGE_MODEL
        self._gateway_key = os.getenv("OMNIROUTE_API_KEY")

    async def generate(self, prompt: str, **kw: Any) -> Dict[str, Any]:
        headers = {}
        if self._gateway_key:
            headers["Authorization"] = f"Bearer {self._gateway_key}"
        payload = {
            "model": kw.get("model", self.model),
            "prompt": prompt,
            "n": kw.get("n", 1),
            "size": kw.get("size", "1024x1024"),
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/images/generations", json=payload, headers=headers,
                )
                resp.raise_for_status()
                data = resp.json().get("data") or []
                if not data:
                    return {"success": False, "error": "OmniRoute returned no images"}
                first = data[0]
                if first.get("url"):
                    return {"success": True, "url": first["url"]}
                if first.get("b64_json"):
                    return {"success": True, "data_base64": first["b64_json"]}
                return {"success": False, "error": f"OmniRoute image response had neither url nor b64_json: {first!r}"}
        except Exception as e:
            logger.warning("OmniRouteImageProvider: generate failed: %s", e)
            return {"success": False, "error": str(e)}


if os.getenv("DISABLE_OMNIROUTE", "0").strip() != "1":
    register("image", "omniroute", OmniRouteImageProvider())
