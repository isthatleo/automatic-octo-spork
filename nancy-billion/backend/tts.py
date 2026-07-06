import logging
import os
import tempfile
import asyncio
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


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
    def __init__(self):
        self.engine = None
        self._init_engine()
        logger.info("Initialized Pyttsx3 TTS")

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

        return await loop.run_in_executor(None, _synthesize)

    async def speak(self, text: str):
        loop = asyncio.get_event_loop()

        def _speak():
            self.engine.say(text)
            self.engine.runAndWait()

        await loop.run_in_executor(None, _speak)


def get_tts_backend():
    backend_type = os.getenv("TTS_BACKEND", "pyttsx3").lower()
    if backend_type == "pyttsx3":
        return Pyttsx3TTS()
    logger.warning(f"Unknown TTS backend {backend_type}, falling back to pyttsx3")
    return Pyttsx3TTS()


tts_backend = get_tts_backend()

