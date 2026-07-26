"""Local neural TTS via fury-sdk's NeuTTS-nano (satellite repo ../../fury-main).

Replaces the Windows SAPI voice in tts.py's Pyttsx3TTS (the actual source of
the "metallic" sound) with a real voice-cloned neural TTS. CPU-only, no GPU,
no cloud API and no per-request cost: a small quantized GGUF backbone
(neuphonic/neutts-nano-q4-gguf) run via llama-cpp-python, plus an ONNX codec
decoder (neuphonic/neucodec-onnx-decoder).

Voice source, checked in this order (no restart-free hot path needed beyond
dropping files -- just restart the backend after uploading):
  1. voice_ref/user_reference.wav + user_reference.txt  <- drop your own clip here
  2. voice_ref/synthetic_reference.wav + .txt           <- auto-bootstrapped once
     via the existing Pyttsx3 "Hazel" engine, so there is always a genuinely
     British-female placeholder without any external download.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import threading
import wave
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from tts import TTSBackend, Pyttsx3TTS

logger = logging.getLogger(__name__)

VOICE_REF_DIR = Path(os.getenv("VOICE_REF_DIR", "./voice_ref"))
USER_REF_WAV = VOICE_REF_DIR / "user_reference.wav"
USER_REF_TXT = VOICE_REF_DIR / "user_reference.txt"
SYNTHETIC_REF_WAV = VOICE_REF_DIR / "synthetic_reference.wav"
SYNTHETIC_REF_TXT = VOICE_REF_DIR / "synthetic_reference.txt"
SYNTHETIC_REF_TEXT = "Hello, I'm Nancy, your personal assistant."

NEUTTS_SAMPLE_RATE = 24_000
_CACHE_MAX_ENTRIES = 200
# Real neural synthesis on CPU-only hardware scales with text length. A
# single fixed timeout was the actual cause of every personalized-greeting
# readout silently falling back to the robotic Pyttsx3 voice: confirmed
# live, an 8s ceiling reliably killed a ~300-character greeting that was
# still making real progress, never a genuine hang. The base timeout now
# covers a short sentence (the unit chat streaming actually synthesizes);
# longer text scales the budget instead of being cut off at the same ceiling
# regardless of length. NEUTTS_TIMEOUT_S alone still exists for callers that
# want to override the base explicitly (e.g. tests).
NEUTTS_TIMEOUT_S = float(os.getenv("NEUTTS_TIMEOUT_S", "20"))
NEUTTS_TIMEOUT_S_PER_CHAR = float(os.getenv("NEUTTS_TIMEOUT_S_PER_CHAR", "0.2"))
# How long a caller will queue for the model lock while someone else's
# (possibly long) text is still generating -- deliberately generous and
# decoupled from this caller's own text length, since a short sentence might
# still need to wait out a long greeting that's genuinely still in progress.
NEUTTS_LOCK_WAIT_S = float(os.getenv("NEUTTS_LOCK_WAIT_S", "90"))
# Confirmed live: the model's first-ever load (GGUF backbone + ONNX codec)
# can take several minutes on this hardware, seemingly I/O-bound rather than
# CPU-bound (disk/AV-scan territory, not a hang -- CPU time barely advances
# while it's happening). Any caller before NeuTTSBackend._warm becomes True
# gets this much patience instead of the normal per-text-length timeout,
# since giving up early there was falling back to Pyttsx3 for a model that
# was still genuinely (if slowly) loading, not stuck.
NEUTTS_COLD_START_TIMEOUT_S = float(os.getenv("NEUTTS_COLD_START_TIMEOUT_S", "300"))


def _timeout_for(text: str) -> float:
    return max(NEUTTS_TIMEOUT_S, len(text) * NEUTTS_TIMEOUT_S_PER_CHAR)


class NeuTTSBackend(TTSBackend):
    """Voice-cloned neural TTS with a small text->WAV cache and an honest
    fallback to Pyttsx3TTS if the neural model or a reference clip can't load."""

    def __init__(self):
        self._tts = None
        self._load_error: Optional[str] = None
        self._fallback = Pyttsx3TTS()
        self._cache: dict[str, bytes] = {}
        self._cache_order: list[str] = []
        # True only after a real synthesis has actually completed once --
        # the model's first-ever load can take minutes on this hardware
        # (confirmed live), unrelated to the text being synthesized. Any
        # caller arriving before that finishes needs a much longer leash
        # than the normal per-text-length timeout, or it gives up on a
        # model that's still genuinely loading (not stuck) and falls back
        # to Pyttsx3 for no real reason.
        self._warm = False
        # Guards model construction and self._tts.speak() calls, which run on
        # ThreadPoolExecutor worker threads (not the event loop) and are not
        # safe to enter concurrently -- llama.cpp-backed contexts aren't
        # built for concurrent generation on one instance.
        self._model_lock = threading.Lock()
        # Guards the async reference-clip bootstrap so two overlapping
        # synthesize() calls on a cold start can't race writing the
        # synthetic .wav/.txt pair.
        self._ref_lock = asyncio.Lock()
        logger.info("Initialized NeuTTS backend (voice_ref=%s)", VOICE_REF_DIR)

    # -- status -------------------------------------------------------------

    @property
    def status(self) -> dict:
        """Synchronous, cheap status check -- run this via run_in_executor from
        an async context, same pattern as clap_detection.ClapDetector.status."""
        error = self._ensure_loaded()
        if USER_REF_WAV.exists() and USER_REF_TXT.exists():
            source = "user"
        elif SYNTHETIC_REF_WAV.exists() and SYNTHETIC_REF_TXT.exists():
            source = "synthetic-placeholder"
        else:
            source = "not_yet_initialized"
        return {"available": error is None, "voice_source": source, "error": error}

    def _ensure_loaded(self) -> Optional[str]:
        """Returns None once the NeuTTS backbone is constructed, else an error."""
        if self._tts is not None:
            return None
        if self._load_error is not None:
            return self._load_error
        with self._model_lock:
            # Re-check inside the lock: another thread may have finished
            # loading (or recorded the error) while we were waiting.
            if self._tts is not None:
                return None
            if self._load_error is not None:
                return self._load_error
            try:
                from fury import TextToSpeech

                self._tts = TextToSpeech(prewarm=False)
                return None
            except Exception as e:
                logger.exception("Failed to load NeuTTS backbone")
                self._load_error = f"Failed to load NeuTTS: {e}"
                return self._load_error

    # -- reference clip -------------------------------------------------------

    async def _ensure_reference_ready(self) -> None:
        """Bootstraps a synthetic placeholder reference clip if neither it nor
        a user-supplied one exists yet. Runs on the event loop (not a worker
        thread) since it needs to await the async Pyttsx3 fallback.

        Also covers the "just drop a recording in" flow: if a user_reference.wav
        exists without a matching .txt, auto-transcribe it with the STT backend
        already in this codebase (faster-whisper) instead of requiring the user
        to hand-type the transcript -- checked on every call, so dropping the
        file in is genuinely all that's needed, no restart required."""
        if USER_REF_WAV.exists() and not USER_REF_TXT.exists():
            await self._transcribe_user_reference()
        if (USER_REF_WAV.exists() and USER_REF_TXT.exists()) or (
            SYNTHETIC_REF_WAV.exists() and SYNTHETIC_REF_TXT.exists()
        ):
            return
        VOICE_REF_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("No reference voice found - synthesizing a placeholder via Pyttsx3 (Hazel)...")
        wav_bytes = await self._fallback.synthesize(SYNTHETIC_REF_TEXT)
        SYNTHETIC_REF_WAV.write_bytes(wav_bytes)
        SYNTHETIC_REF_TXT.write_text(SYNTHETIC_REF_TEXT, encoding="utf-8")

    async def _transcribe_user_reference(self) -> None:
        try:
            from stt import stt_backend

            logger.info("Auto-transcribing dropped-in voice clip %s...", USER_REF_WAV)
            # Dedicated higher-accuracy pass, not stt_backend.transcribe_chunk's
            # beam_size=1 (tuned for live-chat latency) -- this only ever runs
            # once per dropped-in clip, and a wrong transcript here silently
            # degrades cloning quality for every future synthesis, so
            # correctness matters far more than speed for this one call.
            loop = asyncio.get_event_loop()

            def _transcribe():
                model = stt_backend._load_model()
                segments, _info = model.transcribe(str(USER_REF_WAV), beam_size=5, vad_filter=True)
                return "".join(segment.text for segment in segments)

            transcript = await loop.run_in_executor(None, _transcribe)
            transcript = transcript.strip()
            if not transcript:
                logger.warning(
                    "Auto-transcription of %s produced no text -- leaving it unpaired; "
                    "add user_reference.txt by hand if this keeps happening.",
                    USER_REF_WAV,
                )
                return
            USER_REF_TXT.write_text(transcript, encoding="utf-8")
            logger.info("Voice clone reference ready: %r", transcript)
        except Exception as e:
            logger.warning("Could not auto-transcribe %s: %s", USER_REF_WAV, e)

    def _resolve_reference(self) -> Tuple[str, str, str]:
        """Sync lookup -- call only after _ensure_reference_ready has run."""
        if USER_REF_WAV.exists() and USER_REF_TXT.exists():
            return str(USER_REF_WAV), USER_REF_TXT.read_text(encoding="utf-8").strip(), "user"
        return (
            str(SYNTHETIC_REF_WAV),
            SYNTHETIC_REF_TXT.read_text(encoding="utf-8").strip(),
            "synthetic-placeholder",
        )

    # -- synthesis ------------------------------------------------------------

    def _synthesize_sync(self, text: str) -> bytes:
        error = self._ensure_loaded()
        if error:
            raise RuntimeError(error)

        ref_path, ref_text, _source = self._resolve_reference()
        # self._tts is a single shared llama.cpp-backed instance -- serialize
        # actual generation so two concurrent requests (e.g. a chat reply over
        # the WS handler and a nav-confirmation via POST /tts/synthesize)
        # can't both drive it at once.
        #
        # Timed acquire, not a plain `with` -- asyncio.wait_for() in
        # synthesize() below only stops *awaiting* this call after
        # NEUTTS_TIMEOUT_S; the executor thread running this function keeps
        # running underneath it regardless (Python threads aren't
        # cancellable). If that orphaned thread is mid-generation and still
        # holding a plain lock, every request after it would queue forever
        # on the same lock -- confirmed live: one slow/aborted call left
        # every subsequent request hanging indefinitely even though each
        # had its own timeout. A bounded acquire means a request that can't
        # get the lock in time fails fast into the Pyttsx3 fallback instead
        # of joining a queue with no end.
        if not self._model_lock.acquire(timeout=NEUTTS_LOCK_WAIT_S):
            raise RuntimeError("NeuTTS busy with a prior request past the timeout window")
        try:
            chunks = self._tts.speak(text=text, ref_text=ref_text, ref_audio_path=ref_path)
            audio = np.concatenate(list(chunks))
        finally:
            self._model_lock.release()
        return _encode_wav(audio, NEUTTS_SAMPLE_RATE)

    async def synthesize(self, text: str) -> bytes:
        if text in self._cache:
            return self._cache[text]

        try:
            async with self._ref_lock:
                await self._ensure_reference_ready()
        except Exception as e:
            logger.error("Could not prepare reference voice, falling back to Pyttsx3: %s", e)
            return await self._fallback.synthesize(text)

        loop = asyncio.get_event_loop()
        timeout = _timeout_for(text) if self._warm else NEUTTS_COLD_START_TIMEOUT_S
        try:
            wav_bytes = await asyncio.wait_for(
                loop.run_in_executor(None, self._synthesize_sync, text),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "NeuTTS synthesis exceeded %.0fs (%s) for %d chars, falling back to Pyttsx3",
                timeout, "cold-start budget" if not self._warm else "scaled timeout", len(text),
            )
            return await self._fallback.synthesize(text)
        except Exception as e:
            logger.error("NeuTTS synthesis failed, falling back to Pyttsx3: %s", e)
            return await self._fallback.synthesize(text)

        self._warm = True
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


def _encode_wav(audio: np.ndarray, sample_rate: int) -> bytes:
    audio_int16 = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_int16.tobytes())
    return buf.getvalue()
