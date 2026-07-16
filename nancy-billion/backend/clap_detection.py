"""Clap-detection integration (satellite repo: ../../clap-detection-main).

Ports the mel-spectrogram preprocessing from clap-detection-main/predict.py to
run on in-memory audio chunks (no temp-file round trip) as they arrive over
the WebSocket, instead of the original file-based CLI flow.

That repo doesn't ship pretrained weights — see its README for the external
download link, or train your own with clap-detection-main/train.py. Until
CLAP_MODEL_PATH points at a real .pth file (or torch/torchaudio/torchvision
aren't installed), `status`/`is_available` honestly report unavailable and
`predict()` raises instead of fabricating a result.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

MODEL_PATH = os.getenv("CLAP_MODEL_PATH", "./models/audio_classifier.pth")
SAMPLE_RATE = int(os.getenv("CLAP_SAMPLE_RATE", "44100"))


@dataclass(frozen=True)
class ClapResult:
    is_clap: bool
    confidence: float


class ClapDetector:
    """Lazily loads torch and the CNN weights on first use."""

    def __init__(self, model_path: str = MODEL_PATH):
        self.model_path = model_path
        self._model = None
        self._load_error: Optional[str] = None
        self._torch = None
        self._transform = None
        self._resize = None

    @property
    def is_available(self) -> bool:
        return self._ensure_loaded() is None

    @property
    def status(self) -> Dict[str, Any]:
        error = self._ensure_loaded()
        return {"available": error is None, "model_path": self.model_path, "error": error}

    def _ensure_loaded(self) -> Optional[str]:
        """Returns None if the model is ready to use, else a human-readable error."""
        if self._model is not None:
            return None
        if self._load_error is not None:
            return self._load_error

        if not os.path.exists(self.model_path):
            self._load_error = (
                f"No clap-detection weights found at {self.model_path}. Download the "
                "pretrained model linked from clap-detection-main/README.md, or train "
                "your own with clap-detection-main/train.py, then set CLAP_MODEL_PATH "
                "(or place the file at the default path)."
            )
            return self._load_error

        try:
            import torch
            import torchaudio.transforms as T
            from torchvision.transforms import Resize

            from clap_model import AudioClassifier

            model = AudioClassifier()
            model.load_state_dict(torch.load(self.model_path, map_location="cpu"))
            model.eval()

            self._torch = torch
            self._transform = T.MelSpectrogram(
                sample_rate=SAMPLE_RATE, n_fft=400, win_length=400, hop_length=200, n_mels=128,
            )
            self._resize = Resize((256, 256))
            self._model = model
            return None
        except Exception as e:
            logger.exception("Failed to load clap-detection model")
            self._load_error = f"Failed to load clap-detection model: {e}"
            return self._load_error

    def predict(self, audio_float32: np.ndarray) -> ClapResult:
        error = self._ensure_loaded()
        if error:
            raise RuntimeError(error)

        torch = self._torch
        waveform = torch.from_numpy(np.asarray(audio_float32, dtype=np.float32)).unsqueeze(0)
        spec = self._transform(waveform)
        spec = self._resize(spec)
        spec = (spec - spec.mean()) / spec.std()
        spec = spec.unsqueeze(0)

        with torch.no_grad():
            output = self._model(spec)
            probabilities = torch.softmax(output, dim=1)
            prediction = int(torch.argmax(output, dim=1).item())
            confidence = float(probabilities[0][prediction].item())

        return ClapResult(is_clap=prediction == 1, confidence=confidence)


clap_detector = ClapDetector()
