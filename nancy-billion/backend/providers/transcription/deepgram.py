"""Real Deepgram transcription adapter -- an optional cloud STT alongside
Nancy's existing local faster-whisper backend (stt.py). Offered through the
provider registry for callers wanting cloud-grade accuracy/speed without
changing Nancy's default local STT path.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

import httpx

from providers.base import TranscriptionProvider
from providers.registry import register_if_configured

logger = logging.getLogger(__name__)

DEEPGRAM_MODEL = os.getenv("DEEPGRAM_MODEL", "nova-2")


class DeepgramTranscriptionProvider(TranscriptionProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        if not self.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY not set")

    async def transcribe(self, audio_bytes: bytes, **kw: Any) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.deepgram.com/v1/listen",
                    params={"model": DEEPGRAM_MODEL},
                    content=audio_bytes,
                    headers={"Authorization": f"Token {self.api_key}", "Content-Type": kw.get("content_type", "audio/wav")},
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["results"]["channels"][0]["alternatives"][0]["transcript"]
                return {"success": True, "text": text}
        except Exception as e:
            logger.warning("DeepgramTranscriptionProvider: transcribe failed: %s", e)
            return {"success": False, "error": str(e)}


register_if_configured("transcription", "deepgram", "DEEPGRAM_API_KEY", DeepgramTranscriptionProvider)
