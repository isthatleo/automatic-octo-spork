import asyncio
import numpy as np
import logging
from abc import ABC, abstractmethod
import os

logger = logging.getLogger(__name__)

class STTBackend(ABC):
    @abstractmethod
    async def transcribe_chunk(self, audio_chunk: np.ndarray) -> str:
        """
        Process a chunk of audio (float32, -1 to 1) and return partial transcript.
        Return empty string if no speech detected.
        """
        pass

    @abstractmethod
    async def transcribe(self, audio: np.ndarray) -> str:
        """
        Transcribe a full audio utterance.
        """
        pass

class FasterWhisperSTT(STTBackend):
    def __init__(self):
        # Lazy import to avoid heavy dependency if not used
        self.model = None
        self.model_size = os.getenv("WHISPER_MODEL", "tiny.en")
        self.device = os.getenv("WHISPER_DEVICE", "cpu")
        # British English is the default for Nancy's persona.
        self.language = os.getenv("STT_LANGUAGE", "en-GB")
        logger.info(
            f"Initializing FasterWhisperSTT with model={self.model_size}, device={self.device}, language={self.language}"
        )

    def _load_model(self):
        if self.model is None:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(self.model_size, device=self.device, compute_type="int8")
        return self.model

    async def transcribe_chunk(self, audio_chunk: np.ndarray) -> str:
        # Both model loading (first call only, downloads/instantiates the
        # model) and model.transcribe() are blocking, CPU-bound calls --
        # running either directly on the event loop would freeze every other
        # concurrent request (chat, TTS, everything) for the whole duration.
        # Offload both to a thread, same pattern clap_detection's status/
        # predict calls use. beam_size=1 (greedy) trades marginal accuracy for
        # real-time latency, which matters far more than beam-search precision
        # for short commands.
        loop = asyncio.get_event_loop()

        def _transcribe():
            model = self._load_model()
            segments, info = model.transcribe(
                audio_chunk,
                beam_size=1,
                vad_filter=True,
                language=self.language,
            )
            return "".join(segment.text for segment in segments)

        text = await loop.run_in_executor(None, _transcribe)
        return text.strip()

    async def transcribe(self, audio: np.ndarray) -> str:
        return await self.transcribe_chunk(audio)

# Factory to select backend
def get_stt_backend():
    backend_type = os.getenv("STT_BACKEND", "faster_whisper").lower()
    if backend_type == "faster_whisper":
        return FasterWhisperSTT()
    # Add other backends as needed
    else:
        logger.warning(f"Unknown STT backend {backend_type}, falling back to faster_whisper")
        return FasterWhisperSTT()

# Instantiate based on env
stt_backend = get_stt_backend()