"""Real (if intentionally lightweight) speaker verification -- lets Billion
check whether a voice sample actually matches the enrolled user before
treating it as trusted, as an additional signal layered on top of (never a
replacement for) the existing Telegram human-approval gate every sensitive
tool call already goes through.

Deliberately built on MFCC statistics (mean+std pooled over time) + cosine
similarity rather than a trained neural speaker-embedding model (a
d-vector/x-vector approach, e.g. via the `resemblyzer` package): that pulls
in a heavy dependency chain (librosa, webrtcvad, matplotlib, umap-learn) that
risks the exact pathological pip-resolver backtracking already hit once this
session, for marginal benefit in a single-enrolled-user setting. torchaudio
(already a base dependency, used by neu_tts.py) has everything actually
needed here: real MFCC extraction, real resampling. This is genuinely
functional for "is this the enrolled user or a random other voice" -- not a
forensic-grade biometric, and it says so.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

PROFILE_PATH = Path(__file__).parent / "data" / "voice_profile.json"
TARGET_SAMPLE_RATE = 16000
DEFAULT_MATCH_THRESHOLD = 0.80
_MIN_SAMPLES = TARGET_SAMPLE_RATE // 2  # refuse to embed less than ~0.5s of audio

_mfcc_transform = None  # lazy -- constructing it imports torch/torchaudio


def _get_mfcc_transform():
    global _mfcc_transform
    if _mfcc_transform is None:
        import torchaudio
        _mfcc_transform = torchaudio.transforms.MFCC(
            sample_rate=TARGET_SAMPLE_RATE, n_mfcc=20,
            melkwargs={"n_fft": 400, "hop_length": 160, "n_mels": 40},
        )
    return _mfcc_transform


def _embed(pcm_float32: np.ndarray, sample_rate: int = TARGET_SAMPLE_RATE) -> Optional[np.ndarray]:
    """pcm_float32: mono audio in [-1, 1]. Returns a fixed-length,
    L2-normalized embedding (MFCC mean+std over time), or None if the clip
    is too short/silent to embed meaningfully."""
    if pcm_float32 is None or len(pcm_float32) < _MIN_SAMPLES:
        return None
    try:
        import torch
        import torchaudio
        wav = torch.from_numpy(np.asarray(pcm_float32, dtype=np.float32)).unsqueeze(0)
        if sample_rate != TARGET_SAMPLE_RATE:
            wav = torchaudio.functional.resample(wav, sample_rate, TARGET_SAMPLE_RATE)
        mfcc = _get_mfcc_transform()(wav)  # (1, n_mfcc, T)
        mfcc = mfcc.squeeze(0).numpy()
        if mfcc.shape[1] < 2:
            return None
        embedding = np.concatenate([mfcc.mean(axis=1), mfcc.std(axis=1)])
        norm = np.linalg.norm(embedding)
        if norm < 1e-8:
            return None
        return embedding / norm
    except Exception as e:
        logger.warning("voice_id: embedding failed: %s", e)
        return None


def is_enrolled() -> bool:
    return PROFILE_PATH.exists()


def enroll(pcm_float32: np.ndarray, sample_rate: int = TARGET_SAMPLE_RATE) -> Dict[str, Any]:
    embedding = _embed(pcm_float32, sample_rate)
    if embedding is None:
        return {"success": False, "error": "Audio sample too short or silent to enroll -- need at least ~1-2 real seconds of clear speech."}
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps({"embedding": embedding.tolist()}), encoding="utf-8")
    return {"success": True}


def clear_enrollment() -> Dict[str, Any]:
    if PROFILE_PATH.exists():
        PROFILE_PATH.unlink()
    return {"success": True}


def verify(pcm_float32: np.ndarray, sample_rate: int = TARGET_SAMPLE_RATE, threshold: float = DEFAULT_MATCH_THRESHOLD) -> Dict[str, Any]:
    if not is_enrolled():
        return {"success": False, "error": "No voice profile enrolled.", "match": None}
    embedding = _embed(pcm_float32, sample_rate)
    if embedding is None:
        return {"success": False, "error": "Audio sample too short or silent to verify.", "match": None}
    try:
        stored = np.array(json.loads(PROFILE_PATH.read_text(encoding="utf-8"))["embedding"], dtype=np.float32)
    except Exception as e:
        return {"success": False, "error": f"Failed to read voice profile: {e}", "match": None}
    similarity = float(np.dot(embedding, stored))  # both L2-normalized -> this is cosine similarity
    return {"success": True, "match": bool(similarity >= threshold), "similarity": round(similarity, 3)}
