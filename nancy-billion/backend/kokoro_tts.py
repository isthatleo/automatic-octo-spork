"""Local neural TTS via Kokoro-82M (hexgrad/Kokoro-82M, Apache-2.0).

The third engine tried here, and the one that actually resolves the
quality-versus-speed conflict the other two couldn't. Measured live on this
machine, same text, warm, in a dedicated worker process:

    engine    short greeting   full brief (~17s audio)   voice quality
    NeuTTS    7.2s             ~29s                      good (Hazel clone)
    Kokoro    3.0s             ~16s                      best available
    Piper     ~0.4s            ~2s                       rejected (accents)

NeuTTS clones Microsoft Hazel and sounds decent, but runs ~1.7x slower than
realtime. Piper is far faster than realtime but its en_GB voices were all
rejected -- alba is Scottish, jenny_dioco and cori read Irish, and the VCTK
Southern-England speakers were no better. Kokoro is roughly 2x faster than
NeuTTS while being a genuinely higher-quality model: it consistently places
at or near the top of the human-rated TTS Spaces Arena despite being only
82M parameters.

Voice: KOKORO_VOICE (default bf_emma). Kokoro's own published voice grades
rate bf_emma highest among its British females (B-), ahead of bf_isabella
(C+), bf_alice and bf_lily (C). All four are available and switchable.

Synthesis runs in a dedicated process -- see kokoro_worker.py for why that
is load-bearing rather than incidental.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Optional

from tts import TTSBackend, Pyttsx3TTS

logger = logging.getLogger(__name__)

KOKORO_VOICE = os.getenv("KOKORO_VOICE", "bf_emma")
KOKORO_SPEED = float(os.getenv("KOKORO_SPEED", "1.0"))
KOKORO_DIR = Path(os.getenv("KOKORO_DIR", "./data/kokoro"))
KOKORO_MODEL = KOKORO_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES = KOKORO_DIR / "voices-v1.0.bin"
_CACHE_MAX_ENTRIES = 200


class KokoroTTSBackend(TTSBackend):
    """Fast, high-quality local neural TTS with a small text->WAV cache and
    an honest fallback to Pyttsx3TTS if the model can't load."""

    def __init__(self):
        self._executor: Optional[ProcessPoolExecutor] = None
        self._load_error: Optional[str] = None
        self._fallback = Pyttsx3TTS()
        self._cache: dict[str, bytes] = {}
        self._cache_order: list[str] = []
        # Guards worker creation only -- max_workers=1 already serializes
        # real synthesis for us.
        self._model_lock = threading.Lock()
        logger.info(
            "Initialized Kokoro TTS backend (voice=%s, speed=%.2f, dir=%s)",
            KOKORO_VOICE, KOKORO_SPEED, KOKORO_DIR,
        )

    @property
    def status(self) -> dict:
        error = self._ensure_loaded()
        return {
            "available": error is None,
            "engine": "kokoro",
            "voice": KOKORO_VOICE,
            "error": error,
        }

    def _ensure_loaded(self) -> Optional[str]:
        if self._executor is not None:
            return None
        if self._load_error is not None:
            return self._load_error
        with self._model_lock:
            if self._executor is not None:
                return None
            if self._load_error is not None:
                return self._load_error
            missing = [str(p) for p in (KOKORO_MODEL, KOKORO_VOICES) if not p.is_file()]
            if missing:
                self._load_error = (
                    f"Kokoro model files missing: {', '.join(missing)}. Download them from "
                    "https://github.com/thewh1teagle/kokoro-onnx/releases (model-files-v1.0) "
                    f"into {KOKORO_DIR}."
                )
                logger.error(self._load_error)
                return self._load_error
            try:
                import kokoro_worker

                self._executor = ProcessPoolExecutor(
                    max_workers=1, initializer=kokoro_worker.init,
                    initargs=(str(KOKORO_MODEL), str(KOKORO_VOICES), KOKORO_VOICE, KOKORO_SPEED),
                )
                logger.info("Kokoro synthesis worker process starting (voice=%s)", KOKORO_VOICE)
                return None
            except Exception as e:
                logger.exception("Failed to start Kokoro worker process")
                self._load_error = f"Failed to start Kokoro worker: {e}"
                return self._load_error

    async def synthesize(self, text: str) -> bytes:
        text = (text or "").strip()
        if not text:
            return b""
        if text in self._cache:
            return self._cache[text]

        error = self._ensure_loaded()
        if error:
            logger.error("Kokoro unavailable (%s), falling back to Pyttsx3", error)
            return await self._fallback.synthesize(text)

        loop = asyncio.get_event_loop()
        try:
            import kokoro_worker

            wav_bytes = await loop.run_in_executor(self._executor, kokoro_worker.synthesize, text)
        except Exception as e:
            # A crashed worker poisons the pool -- drop it so the next call
            # builds a fresh one instead of failing forever.
            logger.error("Kokoro synthesis failed, falling back to Pyttsx3: %s", e)
            with self._model_lock:
                if self._executor is not None:
                    self._executor.shutdown(wait=False)
                    self._executor = None
            return await self._fallback.synthesize(text)

        if not wav_bytes:
            logger.warning("Kokoro returned empty audio for %d chars, falling back to Pyttsx3", len(text))
            return await self._fallback.synthesize(text)

        self._cache_put(text, wav_bytes)
        return wav_bytes

    async def speak(self, text: str):
        # No server-side speaker output is used by the web app; keep interface
        # parity via the SAPI fallback's direct-playback path.
        await self._fallback.speak(text)

    def _cache_put(self, text: str, wav_bytes: bytes) -> None:
        if text in self._cache:
            return
        self._cache[text] = wav_bytes
        self._cache_order.append(text)
        if len(self._cache_order) > _CACHE_MAX_ENTRIES:
            oldest = self._cache_order.pop(0)
            self._cache.pop(oldest, None)
