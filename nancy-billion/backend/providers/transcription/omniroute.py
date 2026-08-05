"""OmniRoute (github.com/diegosouzapw/OmniRoute) transcription adapter -- the
same local gateway llm.py's OmniRouteLLM already routes chat through,
extended to its OpenAI-compatible (Whisper-style) /v1/audio/transcriptions
endpoint. An optional cloud/aggregated STT alongside Nancy's existing local
faster-whisper backend (stt.py) -- that remains the default; this is offered
through the provider registry for callers that specifically want it.
Registered unconditionally (unless DISABLE_OMNIROUTE=1), not via
register_if_configured -- like OmniRouteLLM, this is a local keyless gateway,
not a vendor that needs its own API key here.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

import httpx

from providers.base import TranscriptionProvider
from providers.registry import register

logger = logging.getLogger(__name__)

OMNIROUTE_URL = os.getenv("OMNIROUTE_URL", "http://localhost:20128").rstrip("/")
OMNIROUTE_STT_MODEL = os.getenv("OMNIROUTE_STT_MODEL", "whisper-1")


class OmniRouteTranscriptionProvider(TranscriptionProvider):
    def __init__(self) -> None:
        self.base_url = OMNIROUTE_URL
        self.model = OMNIROUTE_STT_MODEL
        self._gateway_key = os.getenv("OMNIROUTE_API_KEY")

    async def transcribe(self, audio_bytes: bytes, **kw: Any) -> Dict[str, Any]:
        headers = {}
        if self._gateway_key:
            headers["Authorization"] = f"Bearer {self._gateway_key}"
        # Whisper-style multipart upload -- unlike Deepgram's raw-body
        # convention (deepgram.py), OpenAI-compatible /audio/transcriptions
        # takes a real multipart/form-data "file" field plus a "model" field.
        files = {"file": ("audio.wav", audio_bytes, kw.get("content_type", "audio/wav"))}
        data = {"model": kw.get("model", self.model)}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/audio/transcriptions", files=files, data=data, headers=headers,
                )
                resp.raise_for_status()
                text = resp.json().get("text", "")
                return {"success": True, "text": text}
        except Exception as e:
            logger.warning("OmniRouteTranscriptionProvider: transcribe failed: %s", e)
            return {"success": False, "error": str(e)}


if os.getenv("DISABLE_OMNIROUTE", "0").strip() != "1":
    register("transcription", "omniroute", OmniRouteTranscriptionProvider())
