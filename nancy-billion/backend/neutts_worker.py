"""NeuTTS synthesis worker -- the code that runs INSIDE the dedicated TTS
subprocess (see neu_tts.py's NeuTTSBackend).

Standalone by design: imports nothing from tts.py or neu_tts.py. Windows
uses the `spawn` start method, so the worker re-imports whatever module its
target functions live in; putting these in neu_tts.py would drag in
tts.py, whose module level calls get_tts_backend() and re-enters the very
module being imported. That exact circular import already bit the Piper
worker (see piper_worker.py) -- it died on startup and was silently
respawned per request, reloading the model every single call.

Why a separate PROCESS at all: NeuTTS's generation loop does substantial
per-chunk Python work, and this backend runs dozens of concurrent asyncio
tasks (agent loops, cron, watches, Telegram long-polling, presence,
memory embedding) that hold the GIL constantly. Measured live, same text,
same machine: ~1.7x realtime standalone versus ~4.9x inside the backend --
a 42-character boot greeting took 22 SECONDS to synthesize in-process. A
separate process gets its own interpreter and its own GIL, which restores
standalone speed. Threads cannot help; they share the GIL.
"""

from __future__ import annotations

import io
import wave

import numpy as np

SAMPLE_RATE = 24_000

# NeuTTS's espeak-derived phonemizer silently emits near-empty audio for
# certain "smart" punctuation -- kept in sync with neu_tts.py's own map.
_PUNCTUATION_NORMALIZE = {
    "—": ", ", "–": "-", "…": "...",
    "“": '"', "”": '"', "‘": "'", "’": "'",
}

_tts = None
_ref_path = None
_ref_text = None


def init(ref_path: str, ref_text: str) -> None:
    """ProcessPoolExecutor initializer -- builds the GGUF backbone + ONNX
    codec ONCE per worker process. This is the expensive step (measured
    ~47s cold on this hardware); every call after it is warm."""
    global _tts, _ref_path, _ref_text
    from fury import TextToSpeech

    _tts = TextToSpeech(prewarm=False)
    _ref_path = ref_path
    _ref_text = ref_text


def synthesize(text: str) -> bytes:
    """Synthesize `text` to WAV bytes with the worker's preloaded model."""
    if _tts is None:
        raise RuntimeError("NeuTTS worker was never initialised")
    for bad, good in _PUNCTUATION_NORMALIZE.items():
        text = text.replace(bad, good)
    chunks = _tts.speak(text=text, ref_text=_ref_text, ref_audio_path=_ref_path)
    audio = np.concatenate(list(chunks))
    audio_int16 = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(audio_int16.tobytes())
    return buf.getvalue()
