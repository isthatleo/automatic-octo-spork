"""Real ElevenLabs TTS adapter -- an optional cloud voice alongside Nancy's
existing local NeuTTS/Pyttsx3 backends (tts.py/neu_tts.py). Those remain the
default; this is offered through the provider registry for callers that
specifically want a cloud voice (e.g. a future higher-fidelity voice-call
integration) without changing Nancy's primary voice pipeline.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any, Dict

import httpx

from providers.base import TTSProvider
from providers.registry import register_if_configured

logger = logging.getLogger(__name__)

DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # "Rachel", ElevenLabs' default demo voice


class ElevenLabsTTSProvider(TTSProvider):
    def __init__(self) -> None:
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY not set")

    async def synthesize(self, text: str, **kw: Any) -> Dict[str, Any]:
        voice_id = kw.get("voice_id", DEFAULT_VOICE_ID)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    json={"text": text, "model_id": kw.get("model_id", "eleven_multilingual_v2")},
                    headers={"xi-api-key": self.api_key, "Accept": "audio/mpeg"},
                )
                resp.raise_for_status()
                return {"success": True, "audio_base64": base64.b64encode(resp.content).decode("ascii")}
        except Exception as e:
            logger.warning("ElevenLabsTTSProvider: synthesize failed: %s", e)
            return {"success": False, "error": str(e)}


register_if_configured("tts", "elevenlabs", "ELEVENLABS_API_KEY", ElevenLabsTTSProvider)
