"""Audio decoding utilities.

Production-grade requirements:
- Accept base64-encoded WebM/Opus blobs coming from the browser.
- Decode to 16-bit PCM at the sample-rate expected by the STT backend.
- Provide deterministic output for streaming chunks.

We decode via ffmpeg because Python-native Opus/WebM decoding is non-trivial.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DecodedAudio:
    pcm_int16: np.ndarray  # shape: (n_samples,)
    sample_rate: int


def _require_ffmpeg() -> str:
    ffmpeg = os.getenv("FFMPEG_BIN", "ffmpeg")
    if shutil.which(ffmpeg) is None:
        raise RuntimeError(
            "ffmpeg binary not found. Install ffmpeg and ensure it is on PATH, "
            "or set FFMPEG_BIN to the full path to ffmpeg."
        )
    return ffmpeg


def _b64_to_bytes(b64: str) -> bytes:
    # Allow either plain base64 or data-url base64 payload.
    b64 = b64.strip()
    if b64.startswith("data:"):
        # data:mime;base64,....
        b64 = b64.split(",", 1)[1]
    return base64.b64decode(b64, validate=False)


def decode_webm_opus_b64_to_pcm(
    audio_b64: str,
    *,
    target_sample_rate: int = 16000,
    ffmpeg_path: Optional[str] = None,
) -> DecodedAudio:
    """Decode a browser WebM/Opus blob (base64) to mono PCM int16.

    Notes:
    - We use ffmpeg's libopus + demuxer to handle WebM.
    - Output is signed 16-bit little-endian PCM.
    """

    ffmpeg = ffmpeg_path or _require_ffmpeg()

    audio_bytes = _b64_to_bytes(audio_b64)

    # Write input to temp file (ffmpeg reads from file well across platforms).
    with tempfile.TemporaryDirectory() as td:
        in_path = os.path.join(td, "input.webm")
        out_path = os.path.join(td, "output.raw")
        with open(in_path, "wb") as f:
            f.write(audio_bytes)

        # Build ffmpeg command.
        # -ac 1: mono
        # -f s16le: raw pcm
        # -ar: target sample rate
        # -loglevel error: keep logs clean (we log stderr on failure)
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            in_path,
            "-ac",
            "1",
            "-ar",
            str(target_sample_rate),
            "-f",
            "s16le",
            out_path,
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            logger.error("ffmpeg decode failed: %s", proc.stderr)
            raise RuntimeError(f"ffmpeg decode failed: {proc.stderr.strip()}")

        with open(out_path, "rb") as f:
            raw = f.read()

    if not raw:
        return DecodedAudio(pcm_int16=np.zeros((0,), dtype=np.int16), sample_rate=target_sample_rate)

    pcm = np.frombuffer(raw, dtype=np.int16).copy()
    return DecodedAudio(pcm_int16=pcm, sample_rate=target_sample_rate)


def pcm_int16_to_float32(pcm_int16: np.ndarray) -> np.ndarray:
    """Convert PCM int16 [-32768,32767] to float32 [-1,1]."""
    if pcm_int16.dtype != np.int16:
        pcm_int16 = pcm_int16.astype(np.int16)
    return (pcm_int16.astype(np.float32) / 32768.0).astype(np.float32)

