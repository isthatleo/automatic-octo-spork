"""Kokoro synthesis worker -- runs INSIDE the dedicated TTS subprocess
(see kokoro_tts.py's KokoroTTSBackend).

Standalone by design: imports nothing from tts.py or kokoro_tts.py. Windows
spawns workers by re-importing the module the target function lives in, and
importing kokoro_tts here would drag in tts.py, whose module level calls
get_tts_backend() and re-enters the module being imported. That exact
circular import already killed the Piper worker once -- it died on startup
and was silently respawned per request, reloading the model every call.

A separate PROCESS rather than a thread for the same reason as the other
engines: ONNX inference plus per-chunk Python work gets GIL-starved by this
backend's dozens of concurrent asyncio loops. Measured for NeuTTS on
identical text, ~1.7x realtime standalone versus ~4.9x in-process.
"""

from __future__ import annotations

import io
import wave

import numpy as np

_kokoro = None
_voice = None
_speed = 1.0

# Kokoro emits float32 at 24kHz.
SAMPLE_RATE = 24_000


def init(model_path: str, voices_path: str, voice: str, speed: float = 1.0) -> None:
    """ProcessPoolExecutor initializer -- loads the ONNX model ONCE per
    worker process (~2s), so every later call is warm."""
    global _kokoro, _voice, _speed
    from kokoro_onnx import Kokoro

    _kokoro = Kokoro(model_path, voices_path)
    _voice = voice
    _speed = speed


def synthesize(text: str) -> bytes:
    """Synthesize `text` to 16-bit PCM WAV bytes."""
    if _kokoro is None:
        raise RuntimeError("Kokoro worker was never initialised")
    # lang='en-gb' matters: it selects British phonemisation, so a British
    # voice isn't rendered with American vowels.
    samples, sample_rate = _kokoro.create(text, voice=_voice, speed=_speed, lang="en-gb")
    audio_int16 = (np.asarray(samples) * 32767).clip(-32768, 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(int(sample_rate))
        wav_file.writeframes(audio_int16.tobytes())
    return buf.getvalue()
