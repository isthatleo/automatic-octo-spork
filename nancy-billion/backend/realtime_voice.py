"""Real realtime "Talk" voice mode -- ported from OpenClaw's talk/*
realtime-voice stack. An alternative wake-word backend to wake_word.py's
VoiceWakeWord (which polls a local rolling audio buffer through
faster-whisper every ~1.5s): this streams real microphone audio directly to
a live cloud realtime transcription session (providers/transcription/
realtime_ws.py's Deepgram WS client, from Batch 3) and watches the
continuously-updating transcript for the wake phrase as it arrives, instead
of periodic batch transcription -- lower latency, at the cost of needing
DEEPGRAM_API_KEY.

Implements the same WakeWordDetector ABC as ClapWakeWord/VoiceWakeWord
(wake_word.py) so it's a genuine drop-in alternative, selected via
WAKE_WORD_BACKEND=realtime, not a parallel system bolted on beside it.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Optional

import numpy as np
import sounddevice as sd

from wake_word import WakeWordDetector

logger = logging.getLogger(__name__)


class RealtimeVoiceWakeWord(WakeWordDetector):
    def __init__(self, keywords=("nancy", "billion", "jarvis"), *, sample_rate: int = 16000, cooldown_seconds: float = 3.0) -> None:
        self.keywords = [k.lower() for k in keywords]
        self.sample_rate = sample_rate
        self.cooldown_seconds = cooldown_seconds
        self.callback = None
        self.running = False
        self.stream: Optional[sd.InputStream] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._session = None
        self._last_trigger_ts = 0.0

    def is_configured(self) -> bool:
        return bool(os.getenv("DEEPGRAM_API_KEY"))

    def _maybe_trigger(self, text: str) -> None:
        if not text:
            return
        now = time.time()
        if now - self._last_trigger_ts < self.cooldown_seconds:
            return
        t = text.lower().replace("-", " ")
        words = set(t.split())
        if any(k in words or k in t for k in self.keywords):
            self._last_trigger_ts = now
            logger.info("RealtimeVoiceWakeWord: wake phrase detected in live transcript: %r", text)
            if self.callback:
                self.callback()

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            logger.debug("RealtimeVoiceWakeWord audio status: %s", status)
        if self._loop is None or self._session is None:
            return
        chunk = indata[:, 0].tobytes() if indata.dtype == np.int16 else (indata[:, 0] * 32768.0).astype(np.int16).tobytes()
        asyncio.run_coroutine_threadsafe(self._session.send_audio(chunk), self._loop)

    async def _run_session(self) -> None:
        from providers.transcription.realtime_ws import RealtimeTranscriptionSession
        self._session = RealtimeTranscriptionSession(sample_rate=self.sample_rate)
        try:
            async with self._session as session:
                async for update in session.transcripts():
                    if not self.running:
                        break
                    self._maybe_trigger(update["text"])
        except Exception as e:
            logger.warning("RealtimeVoiceWakeWord: realtime session ended: %s", e)

    def _thread_main(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run_session())
        finally:
            self._loop.close()

    def start(self, callback) -> None:
        if not self.is_configured():
            logger.warning("RealtimeVoiceWakeWord: DEEPGRAM_API_KEY not set, real-time voice mode unavailable")
            return
        self.callback = callback
        self.running = True
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()

        # Real mic capture starts only once the WS session thread/loop is up,
        # so the very first audio callback has somewhere real to send audio to.
        for _ in range(50):
            if self._loop is not None:
                break
            time.sleep(0.1)

        self.stream = sd.InputStream(samplerate=self.sample_rate, channels=1, dtype="int16", callback=self._audio_callback, blocksize=int(0.1 * self.sample_rate))
        self.stream.start()
        logger.info("RealtimeVoiceWakeWord started (Deepgram realtime streaming).")

    def stop(self) -> None:
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        if self._loop is not None and self._session is not None:
            asyncio.run_coroutine_threadsafe(self._session.close(), self._loop)
        logger.info("RealtimeVoiceWakeWord stopped.")
