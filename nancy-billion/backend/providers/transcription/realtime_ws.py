"""Real WebSocket streaming STT session -- ported from OpenClaw's
realtime-transcription extension. A provider-agnostic session wrapper around
Deepgram's real streaming endpoint (the same vendor as the batch/one-shot
adapter in deepgram.py, different API surface): feed it raw audio chunks as
they arrive from the mic, get back partial/final transcripts as they're
recognized, instead of waiting for a whole utterance before transcribing.

Session-based rather than a single request/response, so it doesn't fit the
one-method TranscriptionProvider ABC in providers/base.py -- this is a
standalone class used directly by realtime_voice.py (Batch 9), not routed
through providers/registry.py's get_ordered_providers().
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator, Optional

import websockets

logger = logging.getLogger(__name__)

DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"


class RealtimeTranscriptionSession:
    """Usage: `async with RealtimeTranscriptionSession() as session:` then
    `await session.send_audio(chunk)` for each real audio chunk, and iterate
    `async for text in session.transcripts():` (typically from a second
    concurrent task) to receive partial/final results as they arrive."""

    def __init__(self, sample_rate: int = 16000, encoding: str = "linear16") -> None:
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        self.sample_rate = sample_rate
        self.encoding = encoding
        self._ws: Optional[Any] = None  # type: ignore[name-defined]

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def __aenter__(self) -> "RealtimeTranscriptionSession":
        if not self.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY not set -- realtime transcription unavailable")
        url = f"{DEEPGRAM_WS_URL}?encoding={self.encoding}&sample_rate={self.sample_rate}&interim_results=true"
        self._ws = await websockets.connect(url, additional_headers={"Authorization": f"Token {self.api_key}"})
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def send_audio(self, chunk: bytes) -> None:
        if self._ws is None:
            raise RuntimeError("session not open -- use 'async with'")
        await self._ws.send(chunk)

    async def transcripts(self) -> AsyncIterator[dict]:
        """Yields {"text": str, "is_final": bool} for each recognized
        segment as Deepgram sends it. Ends when the connection closes."""
        if self._ws is None:
            raise RuntimeError("session not open -- use 'async with'")
        async for raw in self._ws:
            try:
                data = json.loads(raw)
                alt = data.get("channel", {}).get("alternatives", [{}])[0]
                text = alt.get("transcript", "")
                if text:
                    yield {"text": text, "is_final": bool(data.get("is_final"))}
            except Exception as e:
                logger.warning("RealtimeTranscriptionSession: failed to parse message: %s", e)

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
