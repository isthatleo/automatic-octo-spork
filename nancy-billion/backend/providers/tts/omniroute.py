"""OmniRoute (github.com/diegosouzapw/OmniRoute) TTS adapter -- the same
local gateway llm.py's OmniRouteLLM already routes chat through, extended to
its OpenAI-compatible /v1/audio/speech endpoint. An optional cloud/aggregated
voice alongside Nancy's existing local NeuTTS/Kokoro/Piper/Pyttsx3 backends
(tts.py/neu_tts.py) -- those remain the default voice pipeline; this is
offered through the provider registry for callers that specifically want it.
Registered unconditionally (unless DISABLE_OMNIROUTE=1), not via
register_if_configured -- like OmniRouteLLM, this is a local keyless gateway,
not a vendor that needs its own API key here.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any, Dict

import httpx

from providers.base import TTSProvider
from providers.registry import register

logger = logging.getLogger(__name__)

OMNIROUTE_URL = os.getenv("OMNIROUTE_URL", "http://localhost:20128").rstrip("/")
OMNIROUTE_TTS_MODEL = os.getenv("OMNIROUTE_TTS_MODEL", "auto")
OMNIROUTE_TTS_VOICE = os.getenv("OMNIROUTE_TTS_VOICE", "alloy")


class OmniRouteTTSProvider(TTSProvider):
    def __init__(self) -> None:
        self.base_url = OMNIROUTE_URL
        self.model = OMNIROUTE_TTS_MODEL
        self.voice = OMNIROUTE_TTS_VOICE
        self._gateway_key = os.getenv("OMNIROUTE_API_KEY")

    async def synthesize(self, text: str, **kw: Any) -> Dict[str, Any]:
        headers = {}
        if self._gateway_key:
            headers["Authorization"] = f"Bearer {self._gateway_key}"
        payload = {
            "model": kw.get("model", self.model),
            "input": text,
            "voice": kw.get("voice", self.voice),
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/audio/speech", json=payload, headers=headers,
                )
                resp.raise_for_status()
                # OpenAI-compatible /audio/speech returns raw audio bytes
                # directly (audio/mpeg by default), not a JSON envelope.
                return {"success": True, "audio_base64": base64.b64encode(resp.content).decode("ascii")}
        except Exception as e:
            logger.warning("OmniRouteTTSProvider: synthesize failed: %s", e)
            return {"success": False, "error": str(e)}


if os.getenv("DISABLE_OMNIROUTE", "0").strip() != "1":
    register("tts", "omniroute", OmniRouteTTSProvider())
