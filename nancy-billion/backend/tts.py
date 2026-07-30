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

    def _recycle_executor(self) -> None:
        """A hung call's underlying thread can't be cancelled (Python threads
        aren't preemptible) and keeps running forever, but leaving it in
        `self._executor` would mean every future call queues behind it
        indefinitely since this pool has exactly one worker -- confirmed
        live: a single stuck synthesis permanently broke every subsequent
        request until the whole process was restarted. Abandon the poisoned
        executor/engine and swap in a fresh pair instead, so the next call
        gets a clean thread rather than queuing behind a dead one."""
        old_executor = self._executor
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pyttsx3")
        self._com_ready = threading.local()
        self.engine = None
        old_executor.shutdown(wait=False, cancel_futures=True)

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

                # Real bug, confirmed live: on espeak/espeak-ng (this container's
                # driver -- pyttsx3 only uses SAPI5 on native Windows), loose
                # substring indicators like "english"/"uk"/"gb" false-positive
                # on plenty of NON-English voices whose descriptive name merely
                # mentions English in passing -- e.g. "Chinese (Mandarin, latin
                # as English)" (transliteration note, not a language) contains
                # "english"; "Ukrainian"'s own id/lang IS "uk". Both tied the
                # real English (Great Britain) voice's score, and since ties
                # kept whichever voice the loop saw FIRST (list order, not
                # relevance), Nancy ended up speaking through a Chinese voice.
                # Fixed by first filtering to voices whose actual `languages`
                # field (the structured signal espeak reports, not the human-
                # readable name) is really English, and only ranking
                # accent/gender preference within that filtered set.
                def is_english(v) -> bool:
                    langs = getattr(v, "languages", None) or []
                    if isinstance(langs, (str, bytes)):
                        langs = [langs]
                    for lang in langs:
                        code = lang.decode("utf-8", "ignore") if isinstance(lang, bytes) else str(lang)
                        if code.strip().lower().split("-")[0] == "en":
                            return True
                    # Fallback for drivers that report languages oddly: the id
                    # itself encodes the language for espeak (e.g. "gmw/en-gb").
                    id_ = str(getattr(v, "id", "")).lower()
                    return "/en" in id_ or id_.startswith("en")

                english_voices = [v for v in voices if is_english(v)]
                candidates = english_voices or voices  # never silently pick nothing if no English voice exists

                female_indicators = ["female", "woman", "girl", "lady", "zira", "hazel"]
                british_indicators = ["en-gb", "great britain", "british", "rp", "received pronunciation"]

                best = None
                best_score = -1
                for v in candidates:
                    t = voice_text(v)
                    s = 0
                    if any(indicator in t for indicator in british_indicators):
                        s += 200
                    if any(indicator in t for indicator in female_indicators):
                        s += 150
                    if desired and desired in t:
                        s += 1000
                    if s > best_score:
                        best = v
                        best_score = s

                if best is not None:
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
                # pyttsx3's SAPI engine is unreliable across repeated
                # runAndWait() calls on the same instance -- confirmed live:
                # the very first call on a fresh engine succeeds in well
                # under a second, but a second call on that same engine hangs
                # past PYTTSX3_TIMEOUT_S every time. Discard it so the next
                # call builds a fresh one instead of reusing this one.
                self.engine = None

        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self._executor, _synthesize),
                timeout=PYTTSX3_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.error("Pyttsx3 synthesis hung past %.0fs -- recycling executor", PYTTSX3_TIMEOUT_S)
            self._recycle_executor()
            raise RuntimeError("TTS synthesis timed out on every backend")

    async def speak(self, text: str):
        loop = asyncio.get_event_loop()

        def _speak():
            self._ensure_engine()
            try:
                self.engine.say(text)
                self.engine.runAndWait()
            finally:
                self.engine = None  # see _synthesize's comment on why

        try:
            await asyncio.wait_for(
                loop.run_in_executor(self._executor, _speak),
                timeout=PYTTSX3_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.error("Pyttsx3 speak() hung past %.0fs -- recycling executor", PYTTSX3_TIMEOUT_S)
            self._recycle_executor()


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

