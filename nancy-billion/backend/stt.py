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
        # For streaming, we could use VAD and accumulate; for now just transcribe chunk
        model = self._load_model()
        # faster_whisper expects audio as float32 numpy array.
        # `language` locks transcription to British English when available.
        segments, info = model.transcribe(
            audio_chunk,
            beam_size=5,
            vad_filter=True,
            language=self.language,
        )
        text = "".join(segment.text for segment in segments)
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