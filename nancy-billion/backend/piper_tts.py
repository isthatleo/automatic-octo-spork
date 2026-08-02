"""Local neural TTS via Piper (rhasspy/piper) -- the real fix for Billion's
voice-first latency requirement.

Replaces neu_tts.py's NeuTTS-nano as the default TTS engine. Both are local,
neural, and free; the difference is speed, and it is not marginal.
Benchmarked live on this exact machine, same text, same CPU:

    text            NeuTTS-nano      Piper (en_GB-jenny_dioco-medium)
    73 chars        18.8s            0.53s
    269 chars       ~53s             2.90s
    ratio           ~3x SLOWER       ~8x FASTER   (than realtime)

That 3x-slower-than-realtime figure is why no amount of chunking or
streaming could ever fix NeuTTS's latency here: while one second of audio
plays, only a third of a second of the next chunk finishes synthesizing, so
playback falls permanently behind no matter how the work is sliced. Piper
synthesizes ~8x faster than realtime, which makes the whole class of
"speaks the first bit then goes quiet" problems disappear at the source --
a full greeting is ready in ~3s instead of ~53s.

Piper also sidesteps NeuTTS's 2048-token context-window truncation bug
(see neu_tts.py's _looks_truncated) entirely: it phonemizes and synthesizes
sentence-by-sentence internally with no shared global budget, so long text
simply works.

Voice: PIPER_VOICE (default en_GB-jenny_dioco-medium -- a real British
female neural voice). Download more with:
    python -m piper.download_voices <voice-name> --data-dir data/piper_voices
NeuTTS remains available via TTS_BACKEND=neutts; Pyttsx3/SAPI remains the
last-resort fallback if Piper itself fails to load.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import threading
import wave
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Optional

from tts import TTSBackend, Pyttsx3TTS

logger = logging.getLogger(__name__)

PIPER_VOICE = os.getenv("PIPER_VOICE", "en_GB-jenny_dioco-medium")
PIPER_VOICE_DIR = Path(os.getenv("PIPER_VOICE_DIR", "./data/piper_voices"))
# Required for multi-speaker models. en_GB-vctk-medium carries 109 distinct
# speakers with different regional accents, so the speaker id IS the voice.
_raw_speaker = os.getenv("PIPER_SPEAKER", "").strip()
PIPER_SPEAKER = int(_raw_speaker) if _raw_speaker else None
_CACHE_MAX_ENTRIES = 200


# ---------------------------------------------------------------------------
# Dedicated synthesis worker PROCESS (not a thread).
#
# Measured live, same text, same machine, same minute:
#     standalone script      1.25s   (0.10x realtime)
#     inside this backend   34.42s   (2.72x realtime)   <- 27x slower
#
# with the CPU NOT saturated. The cause is GIL contention, not compute:
# Piper's synthesize_wav drives a per-chunk Python loop, and this backend
# runs dozens of concurrent asyncio tasks and threads (agent loops, cron,
# watches, Telegram long-polling, presence, screen-context, economic
# calendar, memory embedding...) that hold the GIL constantly, so that loop
# gets starved. A ThreadPoolExecutor cannot help -- threads share the same
# GIL. A separate process gets its own interpreter and its own GIL, which
# restores full standalone speed.
#
# max_workers=1 with a persistent worker: the 63MB ONNX voice is loaded ONCE
# in the child (via piper_worker.init) and reused for every later call, so
# this costs one model load, not one per request.
#
# The worker functions live in piper_worker.py, NOT here, and that placement
# is load-bearing -- see that module's docstring. Windows `spawn` re-imports
# the module the target function lives in; when these lived in piper_tts.py
# the child hit a circular import (piper_tts -> tts -> get_tts_backend() ->
# piper_tts), died on startup, and was silently respawned per request,
# reloading the model every time (~20s/call vs ~0.6s warm).
# ---------------------------------------------------------------------------


class PiperTTSBackend(TTSBackend):
    """Fast local neural TTS with a small text->WAV cache and an honest
    fallback to Pyttsx3TTS if the Piper model can't load."""

    def __init__(self):
        self._executor: Optional[ProcessPoolExecutor] = None
        self._load_error: Optional[str] = None
        self._fallback = Pyttsx3TTS()
        self._cache: dict[str, bytes] = {}
        self._cache_order: list[str] = []
        # Guards creation of the single worker process (not generation
        # itself -- the worker is max_workers=1, so the pool already
        # serializes real synthesis for us).
        self._model_lock = threading.Lock()
        logger.info("Initialized Piper TTS backend (voice=%s, speaker=%s, dir=%s)", PIPER_VOICE, PIPER_SPEAKER, PIPER_VOICE_DIR)

    # -- status ---------------------------------------------------------------

    @property
    def status(self) -> dict:
        error = self._ensure_loaded()
        return {
            "available": error is None,
            "engine": "piper",
            "voice": PIPER_VOICE,
            "error": error,
        }

    def _model_path(self) -> Path:
        return PIPER_VOICE_DIR / f"{PIPER_VOICE}.onnx"

    def _ensure_loaded(self) -> Optional[str]:
        """Returns None once the worker process is up, else an error string."""
        if self._executor is not None:
            return None
        if self._load_error is not None:
            return self._load_error
        with self._model_lock:
            if self._executor is not None:
                return None
            if self._load_error is not None:
                return self._load_error
            try:
                model = self._model_path()
                if not model.is_file():
                    self._load_error = (
                        f"Piper voice not found at {model}. Download it with: "
                        f"python -m piper.download_voices {PIPER_VOICE} --data-dir {PIPER_VOICE_DIR}"
                    )
                    logger.error(self._load_error)
                    return self._load_error
                import piper_worker

                self._executor = ProcessPoolExecutor(
                    max_workers=1, initializer=piper_worker.init,
                    initargs=(str(model), PIPER_SPEAKER),
                )
                logger.info("Piper synthesis worker process starting (voice=%s)", model)
                return None
            except Exception as e:
                logger.exception("Failed to start Piper worker process")
                self._load_error = f"Failed to start Piper worker: {e}"
                return self._load_error

    # -- synthesis -------------------------------------------------------------

    async def synthesize(self, text: str) -> bytes:
        text = (text or "").strip()
        if not text:
            return b""
        if text in self._cache:
            return self._cache[text]

        error = self._ensure_loaded()
        if error:
            logger.error("Piper unavailable (%s), falling back to Pyttsx3", error)
            return await self._fallback.synthesize(text)

        loop = asyncio.get_event_loop()
        try:
            import piper_worker

            wav_bytes = await loop.run_in_executor(self._executor, piper_worker.synthesize, text)
        except Exception as e:
            # A crashed worker poisons the pool -- drop it so the next call
            # builds a fresh one instead of failing forever.
            logger.error("Piper synthesis failed, falling back to Pyttsx3: %s", e)
            with self._model_lock:
                if self._executor is not None:
                    self._executor.shutdown(wait=False)
                    self._executor = None
            return await self._fallback.synthesize(text)

        if not wav_bytes:
            logger.warning("Piper returned empty audio for %d chars, falling back to Pyttsx3", len(text))
            return await self._fallback.synthesize(text)

        self._cache_put(text, wav_bytes)
        return wav_bytes

    async def speak(self, text: str):
        # No server-side speaker output is used by the web app; keep interface
        # parity via the SAPI fallback's direct-playback path (same as NeuTTS).
        await self._fallback.speak(text)

    async def prewarm(self) -> None:
        """Starts the worker process, loads the voice in it, and runs one
        real synthesis. Both costs are genuinely one-time -- spawning the
        process plus the ONNX Runtime warmup (measured ~13s on the first
        call, versus ~1s for every call after) -- so paying them at startup
        means the user's first real reply doesn't."""
        try:
            await self.synthesize("Systems online.")
            logger.info("Piper TTS pre-warmed.")
        except Exception as e:
            logger.warning("Piper prewarm failed: %s", e)

    def _cache_put(self, text: str, wav_bytes: bytes) -> None:
        if text in self._cache:
            return
        self._cache[text] = wav_bytes
        self._cache_order.append(text)
        if len(self._cache_order) > _CACHE_MAX_ENTRIES:
            oldest = self._cache_order.pop(0)
            self._cache.pop(oldest, None)
