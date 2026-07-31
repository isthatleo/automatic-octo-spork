"""Real image generation -- dispatches to whichever ImageProvider is
configured (providers/image/*.py, e.g. fal.py, deepinfra.py), same
"registered but never called" gap web_search's providers used to have
before web_tool.py wired them to a real tool. Confirmed live via code
read (2026-07-31 Hermes-parity audit): the providers existed and
self-registered correctly, but nothing in main_new.py's tool dispatch
ever called .generate() on one -- multi-modal image generation was
listed as a capability with no actual path to it.
"""
from __future__ import annotations

import base64
import logging

import httpx

logger = logging.getLogger(__name__)

MEDIA_TOOLS = [
    {
        "name": "generate_image",
        "description": (
            "Generate a real image from a text description using whichever real image-generation "
            "provider is configured (fal.ai, DeepInfra, ...). The result is posted to the shared "
            "canvas so the user sees it immediately, and returned to you as an image so you can "
            "describe or reason about what was actually produced. Not available if no image "
            "provider API key is configured."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "What to generate, as a clear visual description."},
                "title": {"type": "string", "description": "Short label for the canvas item. Defaults to the prompt."},
            },
            "required": ["prompt"],
        },
    },
]


async def generate_image(prompt: str, title: str = "") -> dict:
    from providers.registry import get_ordered_providers

    providers = get_ordered_providers("image")
    if not providers:
        return {
            "success": False,
            "error": "No image generation provider is configured (e.g. FAL_API_KEY or DEEPINFRA_API_KEY).",
        }

    result = await providers[0].generate(prompt)
    if not result.get("success"):
        return {"success": False, "error": result.get("error", "image generation failed")}

    url = result.get("url")
    image_b64 = result.get("data_base64")

    if image_b64:
        # Some vendors (DeepInfra) hand back a data: URI directly rather
        # than a URL to fetch -- strip the "data:image/...;base64," prefix
        # if present so canvas_store gets raw base64 either way.
        if image_b64.startswith("data:"):
            image_b64 = image_b64.split(",", 1)[-1]
    elif url:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                image_b64 = base64.b64encode(resp.content).decode()
        except Exception as e:
            logger.warning("generate_image: fetching generated image from %s failed: %s", url, e)
            # Real image, just not embeddable right now -- give the URL back
            # rather than pretending the whole thing failed.
            return {"success": True, "url": url, "note": f"Image generated but could not be downloaded for the canvas: {e}"}
    else:
        return {"success": False, "error": "provider reported success but returned neither a URL nor image data"}

    canvas_item_id = None
    try:
        from canvas_store import canvas_store as store
        from event_bus import event_bus

        item = store.create("image", title or prompt[:80], image_b64)
        await event_bus.publish("CANVAS_ITEM_ADDED", {"item": item.to_public_dict()})
        canvas_item_id = item.id
    except Exception:
        logger.exception("generate_image: posting to canvas failed (image still returned)")

    return {"success": True, "url": url, "canvas_item_id": canvas_item_id, "_image_base64": image_b64}
