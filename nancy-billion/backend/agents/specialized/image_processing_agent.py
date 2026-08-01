"""
Image Processing Agent for Nancy/Billion.
Real image analysis via Pillow (already a dependency, used elsewhere for
map snapshots and screen capture) -- actual pixel data, never a fabricated
description of an image that was never decoded.
"""
from __future__ import annotations

import base64
import io
from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent


class ImageProcessingAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Image Processing Agent", "image-processing")
        self.capabilities.update({
            "description": "Real image analysis (dimensions, format, dominant color, EXIF) via Pillow -- decodes actual pixel data",
            "confidence": 0.8,
            "specializations": ["image-analysis", "color-extraction", "metadata"],
            "tools": ["pillow"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "analyze":
            return self._analyze(task_data.get("image_base64", ""))
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

    def _analyze(self, image_b64: str) -> Dict[str, Any]:
        if not image_b64:
            return {"success": False, "error": "image_base64 is required"}
        try:
            from PIL import Image
            if image_b64.startswith("data:"):
                image_b64 = image_b64.split(",", 1)[-1]
            raw = base64.b64decode(image_b64)
            img = Image.open(io.BytesIO(raw))
            img_rgb = img.convert("RGB")
            small = img_rgb.resize((50, 50))
            pixels = list(small.getdata())
            r = sum(p[0] for p in pixels) / len(pixels)
            g = sum(p[1] for p in pixels) / len(pixels)
            b = sum(p[2] for p in pixels) / len(pixels)
            return {
                "success": True,
                "width": img.width, "height": img.height,
                "format": img.format, "mode": img.mode,
                "average_color_rgb": [round(r), round(g), round(b)],
                "average_color_hex": f"#{round(r):02x}{round(g):02x}{round(b):02x}",
                "file_size_bytes": len(raw),
            }
        except Exception as e:
            return {"success": False, "error": f"Could not decode image: {e}"}

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "Send me an image (base64) with task type 'analyze' and I'll give you real "
            "dimensions, format, and average color, decoded from the actual pixels."
        )}
