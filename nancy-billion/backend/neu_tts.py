"""Local neural TTS via fury-sdk's NeuTTS-nano (satellite repo ../../fury-main).

Replaces the Windows SAPI voice in tts.py's Pyttsx3TTS (the actual source of
the "metallic" sound) with a real voice-cloned neural TTS. CPU-only, no GPU,
no cloud API and no per-request cost: a small quantized GGUF backbone
(neuphonic/neutts-nano-q4-gguf) run via llama-cpp-python, plus an ONNX codec
decoder (neuphonic/neucodec-onnx-decoder).

Voice source, checked fresh on every synthesize() call -- no restart needed
after dropping in or uploading a clip (see POST /voice/reference in
main_new.py for the real upload path; a .wav can also be dropped straight
into this directory by hand):
  1. voice_ref/user_reference.wav + user_reference.txt  <- your own clip
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
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import List, Optional, Tuple

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
    # Must cover a worst-case queue behind another in-flight synthesis (up to
    # NEUTTS_LOCK_WAIT_S, spent inside _synthesize_sync's model_lock.acquire
    # before generation even starts) PLUS this text's own real generation
    # budget. Confirmed live: with this outer timeout shorter than the lock-
    # wait budget, any request that landed while another was still
    # generating reliably blew the outer asyncio.wait_for while genuinely
    # still queued for the lock (not stuck, not slow) -- every chunk of a
    # multi-sentence reply fell back to Pyttsx3 in a row, which is the real
    # cause of the reported "voice keeps changing" mid-reply, since the two
    # timeouts were never actually composed the way the lock-wait's own
    # "deliberately generous" design comment already assumed they would be.
    return NEUTTS_LOCK_WAIT_S + max(NEUTTS_TIMEOUT_S, len(text) * NEUTTS_TIMEOUT_S_PER_CHAR)


# NeuTTS's underlying phonemizer silently produces empty/near-empty audio
# (no exception, no timeout -- completes in well under a second) for text
# containing certain "smart"/extended punctuation that plain espeak-derived
# phonemizer symbol tables don't map: confirmed live, an em dash, en dash, or
# ellipsis anywhere in the text reliably reduced the whole synthesis to a
# 48-byte (header-only) WAV, and curly double quotes to a near-silent one --
# regardless of how much real text surrounded it. Since that "successful"
# empty result then gets cached forever under the original text (see
# NeuTTSBackend._cache), a single LLM-generated sentence using an em dash
# would stay silently broken for the rest of the process's life. LLM output
# (Claude, GPT, Gemini) uses exactly this punctuation constantly, so this was
# a real, frequent cause of Nancy's reported "stops after a few words" and
# "long pauses" mid-reply. Normalizing to plain ASCII equivalents before
# synthesis (and before the cache key is computed) sidesteps the phonemizer
# gap entirely rather than trying to patch it upstream in fury-sdk/espeak.
_PUNCTUATION_NORMALIZE = {
    "—": ", ",   # em dash —
    "–": "-",    # en dash –
    "…": "...",  # ellipsis …
    "“": '"',    # left curly double quote "
    "”": '"',    # right curly double quote "
    "‘": "'",    # left curly single quote '
    "’": "'",    # right curly single quote '
}


def _sanitize_for_neutts(text: str) -> str:
    for bad, good in _PUNCTUATION_NORMALIZE.items():
        text = text.replace(bad, good)
    return text


# NeuTTS-nano's backbone (see fury-main's NeuTTSMinimal) runs on a llama.cpp
# model with a hard n_ctx=2048-TOKEN context window shared between the
# reference-audio codes, the reference text, the phonemized INPUT text, and
# the GENERATED speech tokens -- all in the same budget. Confirmed live: the
# same ~280-char greeting sometimes produced a full, correct ~25s WAV and
# other times a "successful" (no exception) but badly truncated ~9s WAV for
# what should have been the same amount of speech -- non-deterministic
# because token cost isn't a fixed function of character count (numeral-
# heavy text like "4107.0000, down 1.29%" phonemizes into far more tokens
# per character than plain prose, eating the shared budget faster). This is
# the actual root cause of "she speaks the first bit, goes quiet, then jumps
# to a much later part of the reply" for any sufficiently long or numeral-
# dense reply -- a different failure class than the inter-chunk CPU-cost
# gaps the batching in main_new.py/page.tsx addresses.
#
# Real speech for this voice measures ~11-17 chars/sec depending on content
# (slower for numeral-heavy text, per live measurements this session) --
# 25 chars/sec is a deliberately generous ceiling no real synthesis of this
# voice should ever exceed, so anything faster than that is almost
# certainly truncated output, not genuinely fast speech.
_MIN_CHARS_PER_SEC = float(os.getenv("NEUTTS_MIN_CHARS_PER_SEC", "25.0"))
_TRUNCATION_CHECK_MIN_CHARS = 60  # too short below this to reliably tell truncation from genuine brevity
_MAX_SPLIT_DEPTH = 3  # bounds the recursion; also bounds it to at most 2**3 = 8 pieces for any one reply


def _looks_truncated(text: str, wav_bytes: bytes) -> bool:
    stripped = text.strip()
    if len(stripped) < _TRUNCATION_CHECK_MIN_CHARS:
        return False
    audio_bytes = max(0, len(wav_bytes) - 44)  # 44-byte canonical PCM WAV header
    duration_s = audio_bytes / 2 / NEUTTS_SAMPLE_RATE  # 16-bit mono
    if duration_s <= 0:
        return True
    return (len(stripped) / duration_s) > _MIN_CHARS_PER_SEC


def _split_text_at_midpoint(text: str) -> Tuple[str, str]:
    """Splits text roughly in half at the nearest sentence, then clause,
    then word boundary -- used to retry a truncated synthesis in two
    smaller (and therefore token-budget-safer) pieces."""
    text = text.strip()
    mid = len(text) // 2
    window = text[: mid + 200]
    cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if cut < mid * 0.3:
        cut = window.rfind(", ")
    if cut < mid * 0.3:
        cut = window.rfind(" ")
    if cut <= 0:
        cut = mid
    else:
        cut += 1
    return text[:cut].strip(), text[cut:].strip()


def _concat_wav_bytes(chunks: List[bytes]) -> bytes:
    """Concatenates the raw PCM frames of several mono 16-bit WAVs into one
    valid WAV, using the first chunk's own sample rate for the result --
    used to stitch a truncation-triggered split-and-retry back into a
    single audio blob for the caller, same as it would have gotten from one
    successful call."""
    frames: List[bytes] = []
    rate = NEUTTS_SAMPLE_RATE
    for i, chunk in enumerate(chunks):
        with wave.open(io.BytesIO(chunk), "rb") as wf:
            if i == 0:
                rate = wf.getframerate()
            frames.append(wf.readframes(wf.getnframes()))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"".join(frames))
    return buf.getvalue()


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
        # Dedicated synthesis process + its own failure latch. See
        # neutts_worker.py: in-process synthesis is GIL-starved by this
        # backend's many concurrent loops (~4.9x realtime vs ~1.7x
        # standalone, measured on identical text).
        self._executor: Optional[ProcessPoolExecutor] = None
        self._worker_error: Optional[str] = None
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

    async def refresh_reference(self) -> dict:
        """Called right after a new reference clip is uploaded (see
        POST /voice/reference) so the status response reflects it
        immediately instead of waiting for the next synthesize() call to
        lazily discover it. Clears the text->WAV cache too -- every cached
        clip was generated against the *old* reference voice and would keep
        being served in the wrong voice otherwise."""
        async with self._ref_lock:
            await self._ensure_reference_ready()
        self._cache.clear()
        self._cache_order.clear()
        return self.status

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

    def _ensure_worker(self) -> Optional[str]:
        """Starts the dedicated synthesis PROCESS (see neutts_worker.py for
        why a process and not a thread). Returns None on success."""
        if self._executor is not None:
            return None
        if self._worker_error is not None:
            return self._worker_error
        with self._model_lock:
            if self._executor is not None:
                return None
            if self._worker_error is not None:
                return self._worker_error
            try:
                import neutts_worker

                ref_path, ref_text, _src = self._resolve_reference()
                self._executor = ProcessPoolExecutor(
                    max_workers=1, initializer=neutts_worker.init,
                    initargs=(ref_path, ref_text),
                )
                logger.info("NeuTTS synthesis worker process starting (ref=%s)", ref_path)
                return None
            except Exception as e:
                logger.exception("Failed to start NeuTTS worker process")
                self._worker_error = f"Failed to start NeuTTS worker: {e}"
                return self._worker_error

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

    async def _synthesize_one(self, text: str) -> Tuple[bytes, bool]:
        """One real attempt at `text` via NeuTTS, falling back to Pyttsx3 on
        any failure. Returns (wav_bytes, came_from_neutts) -- the caller
        (_synthesize_guarded) needs to know whether the result is genuinely
        subject to NeuTTS's context-window truncation risk at all, since a
        Pyttsx3-origin WAV never is and checking it anyway would just be
        comparing against the wrong voice's speaking rate."""
        try:
            async with self._ref_lock:
                await self._ensure_reference_ready()
        except Exception as e:
            logger.error("Could not prepare reference voice, falling back to Pyttsx3: %s", e)
            return await self._fallback.synthesize(text), False

        loop = asyncio.get_event_loop()
        timeout = _timeout_for(text) if self._warm else NEUTTS_COLD_START_TIMEOUT_S
        try:
            worker_error = self._ensure_worker()
            if worker_error:
                # Worker unavailable -- fall back to in-process synthesis
                # rather than losing the voice entirely (slower, but real).
                wav_bytes = await asyncio.wait_for(
                    loop.run_in_executor(None, self._synthesize_sync, text),
                    timeout=timeout,
                )
            else:
                import neutts_worker

                wav_bytes = await asyncio.wait_for(
                    loop.run_in_executor(self._executor, neutts_worker.synthesize, text),
                    timeout=timeout,
                )
        except asyncio.TimeoutError:
            logger.warning(
                "NeuTTS synthesis exceeded %.0fs (%s) for %d chars, falling back to Pyttsx3",
                timeout, "cold-start budget" if not self._warm else "scaled timeout", len(text),
            )
            return await self._fallback.synthesize(text), False
        except Exception as e:
            logger.error("NeuTTS synthesis failed, falling back to Pyttsx3: %s", e)
            return await self._fallback.synthesize(text), False

        # Defense in depth against the same failure class as the em-dash/en-
        # dash/ellipsis bug _sanitize_for_neutts patches: the phonemizer can
        # in principle choke silently on some OTHER character this codebase
        # hasn't hit yet, returning a "successful" (no exception, no timeout)
        # but near-empty WAV. A real sentence of any real length produces far
        # more than this many bytes of 24kHz 16-bit audio; below it almost
        # certainly means silence, not a hyper-fast synthesis. Caching that
        # silence forever under this text (see _cache_put) would be worse
        # than the extra Pyttsx3 fallback latency here.
        if len(wav_bytes) < 2_000 and len(text.strip()) > 3:
            logger.warning(
                "NeuTTS returned suspiciously small output (%d bytes) for %d chars, "
                "treating as a silent failure and falling back to Pyttsx3",
                len(wav_bytes), len(text),
            )
            return await self._fallback.synthesize(text), False

        self._warm = True
        return wav_bytes, True

    async def _synthesize_guarded(self, text: str, depth: int = 0) -> bytes:
        """Wraps _synthesize_one with the context-window-truncation guard
        (see _looks_truncated's module-level comment): if NeuTTS silently
        cut generation short for this text, split it in half at a sentence
        boundary and retry each half, recursively, then stitch the results
        back into one WAV -- rather than accepting incomplete audio as if
        it were a real, complete reply."""
        wav_bytes, from_neutts = await self._synthesize_one(text)
        if from_neutts and depth < _MAX_SPLIT_DEPTH and _looks_truncated(text, wav_bytes):
            left, right = _split_text_at_midpoint(text)
            if left and right and (left != text) and (right != text):
                logger.warning(
                    "NeuTTS output for %d chars looks truncated (implied speaking "
                    "rate too fast for real speech) -- splitting and retrying in "
                    "two halves (depth %d)",
                    len(text), depth + 1,
                )
                left_bytes = await self._synthesize_guarded(left, depth + 1)
                right_bytes = await self._synthesize_guarded(right, depth + 1)
                return _concat_wav_bytes([left_bytes, right_bytes])
        return wav_bytes

    async def synthesize(self, text: str) -> bytes:
        text = _sanitize_for_neutts(text)
        if text in self._cache:
            return self._cache[text]
        wav_bytes = await self._synthesize_guarded(text)
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
