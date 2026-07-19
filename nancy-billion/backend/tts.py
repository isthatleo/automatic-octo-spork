import logging
import os
import sys
import tempfile
import asyncio
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    import pythoncom
else:
    pythoncom = None

PYTTSX3_TIMEOUT_S = float(os.getenv("PYTTSX3_TIMEOUT_S", "12"))


class TTSBackend(ABC):
    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to speech, return WAV bytes."""
        pass

    @abstractmethod
    async def speak(self, text: str):
        """Speak text directly (non-blocking)."""
        pass


class Pyttsx3TTS(TTSBackend):
    """Windows SAPI via pyttsx3 -- last-resort fallback when NeuTTS is
    unreachable or times out.

    pyttsx3's SAPI5 driver on Windows is COM-based and not safe to drive
    from a thread other than the one that created the engine (a documented
    cause of runAndWait() hanging indefinitely). The engine used to be
    created in __init__ (the main/event-loop thread) while every actual
    call ran on asyncio's default executor (a *different* worker thread
    each time) -- confirmed live as the real second cause of TTS requests
    hanging for 20s+ even after NeuTTS's own timeout correctly fired and
    fell back to this class. Fixed by pinning all pyttsx3 work to one
    dedicated worker thread and creating the engine lazily on that same
    thread, plus a hard timeout so a hang degrades to an error instead of
    blocking the request forever.
    """

    def __init__(self):
        self.engine = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pyttsx3")
        self._com_ready = threading.local()
        logger.info("Initialized Pyttsx3 TTS (lazy engine, dedicated thread)")

    def _ensure_engine(self):
        # SAPI5 is COM-based; a worker thread spun up by a plain
        # ThreadPoolExecutor never gets CoInitialize() called on it the way
        # the main thread implicitly does, so every SAPI call from here
        # would silently hang waiting on COM machinery that was never set
        # up -- confirmed live: pyttsx3 synthesized in ~0.2s in a standalone
        # script (main thread) but hung past a 12s timeout every single
        # time when driven from this executor's thread. One CoInitialize()
        # per thread lifetime (this pool has exactly one worker) fixes it;
        # repeat calls on the same thread are a documented harmless no-op.
        if pythoncom is not None and not getattr(self._com_ready, "done", False):
            pythoncom.CoInitialize()
            self._com_ready.done = True
        if self.engine is None:
            self._init_engine()

    def _init_engine(self):
        import pyttsx3

        self.engine = pyttsx3.init()
        # Optional: set properties
        self.engine.setProperty("rate", 150)  # speed of speech
        self.engine.setProperty("volume", 0.9)  # volume 0-1

        # Try to select a female/British voice if installed.
        # On Windows SAPI, pyttsx3 usually exposes Microsoft Hazel (en-GB) and Microsoft Zira (en-US).
        try:
            desired = (os.getenv("TTS_VOICE_NAME", "") or "").lower()
            voices = self.engine.getProperty("voices") or []

            if voices:
                def voice_text(v):
                    name = str(getattr(v, "name", ""))
                    id_ = str(getattr(v, "id", ""))
                    langs = str(getattr(v, "languages", ""))
                    return f"{name} {id_} {langs}".lower()

                # If user provided an explicit desired voice, prefer it.
                if desired:
                    for v in voices:
                        if desired in voice_text(v):
                            self.engine.setProperty("voice", getattr(v, "id", None) or getattr(v, "name", None))
                            logger.info(f"TTS using voice (TTS_VOICE_NAME match): {getattr(v, 'name', '')}")
                            return

                # Otherwise: prefer British female voice hints.
                # Choose Hazel first if present; else pick the best heuristic.
                for v in voices:
                    if "hazel" in voice_text(v):
                        self.engine.setProperty("voice", getattr(v, "id", None) or getattr(v, "name", None))
                        logger.info(f"TTS using voice (hazel/en-GB): {getattr(v, 'name', '')}")
                        return

                # Enhanced fallback heuristic for female British voice.
                preferred_substrings = ["hazel", "zira", "female", "woman", "british", "uk", "english"]
                female_indicators = ["female", "woman", "girl", "lady"]
                british_indicators = ["hazel", "en-gb", "gb", "brit", "uk", "english", "british"]
                
                best = None
                best_score = -1
                for v in voices:
                    t = voice_text(v)
                    s = 0
                    # Strong preference for known British female voices
                    if "hazel" in t:
                        s += 300
                    # British indicators
                    if any(indicator in t for indicator in british_indicators):
                        s += 200
                    # Female indicators
                    if any(indicator in t for indicator in female_indicators):
                        s += 150
                    # Explicit desired voice match
                    if desired and desired in t:
                        s += 1000
                    if s > best_score:
                        best = v
                        best_score = s

                if best is not None and best_score > 0:
                    self.engine.setProperty("voice", getattr(best, "id", None) or getattr(best, "name", None))
                    logger.info(f"TTS using voice (enhanced heuristic): {getattr(best, 'name', '')}")

        except Exception as e:
            logger.warning(f"TTS voice selection skipped: {e}")

    async def synthesize(self, text: str) -> bytes:
        loop = asyncio.get_event_loop()

        def _synthesize():
            self._ensure_engine()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as fp:
                temp_path = fp.name
            try:
                self.engine.save_to_file(text, temp_path)
                self.engine.runAndWait()
                with open(temp_path, "rb") as f:
                    return f.read()
            finally:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self._executor, _synthesize),
                timeout=PYTTSX3_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.error("Pyttsx3 synthesis hung past %.0fs -- no further fallback available", PYTTSX3_TIMEOUT_S)
            raise RuntimeError("TTS synthesis timed out on every backend")

    async def speak(self, text: str):
        loop = asyncio.get_event_loop()

        def _speak():
            self._ensure_engine()
            self.engine.say(text)
            self.engine.runAndWait()

        try:
            await asyncio.wait_for(
                loop.run_in_executor(self._executor, _speak),
                timeout=PYTTSX3_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.error("Pyttsx3 speak() hung past %.0fs", PYTTSX3_TIMEOUT_S)


def get_tts_backend():
    backend_type = os.getenv("TTS_BACKEND", "neutts").lower()
    if backend_type == "neutts":
        try:
            from neu_tts import NeuTTSBackend

            return NeuTTSBackend()
        except Exception as e:
            logger.warning(f"NeuTTS backend unavailable ({e}), falling back to pyttsx3")
            return Pyttsx3TTS()
    if backend_type == "pyttsx3":
        return Pyttsx3TTS()
    logger.warning(f"Unknown TTS backend {backend_type}, falling back to pyttsx3")
    return Pyttsx3TTS()


tts_backend = get_tts_backend()

