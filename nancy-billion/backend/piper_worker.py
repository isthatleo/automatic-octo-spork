"""Piper synthesis worker -- the code that runs INSIDE the dedicated TTS
subprocess (see piper_tts.py's PiperTTSBackend).

Deliberately standalone: this module imports nothing from tts.py,
piper_tts.py, or anything else in this backend. That isolation is the whole
point, and it is load-bearing.

Windows uses the `spawn` start method, so a worker process re-imports
whatever module its target functions live in. When those functions lived in
piper_tts.py, the child's import chain was:

    piper_tts  ->  tts  ->  (tts.py module level) get_tts_backend()
               ->  piper_tts  (still half-initialised)  ->  ImportError

Confirmed live from the child's own log line: "cannot import name
'PiperTTSBackend' from 'piper_tts' ... falling back to pyttsx3". The worker
died on startup and the pool silently respawned it for EVERY request, so
each call paid a fresh 63MB ONNX model load -- measured as a consistent
~20s per synthesis against ~0.6s standalone, which looked exactly like
"Piper is slow" while actually being an import bug.
"""

from __future__ import annotations

import io
import wave

_voice = None
_speaker_id = None


def init(model_path: str, speaker_id=None) -> None:
    """ProcessPoolExecutor initializer -- loads the ONNX voice ONCE per
    worker process. Everything after this is a warm, sub-second call."""
    global _voice, _speaker_id
    from piper import PiperVoice

    _voice = PiperVoice.load(model_path)
    _speaker_id = speaker_id


def synthesize(text: str) -> bytes:
    """Synthesize `text` to WAV bytes using the worker's preloaded voice."""
    if _voice is None:
        raise RuntimeError("Piper worker voice was never initialised")
    buf = io.BytesIO()
    # Multi-speaker models (e.g. en_GB-vctk-medium, 109 speakers) need an
    # explicit speaker_id -- without one Piper silently uses speaker 0,
    # which for VCTK is an arbitrary voice, not the intended accent.
    syn_config = None
    if _speaker_id is not None:
        from piper import SynthesisConfig

        syn_config = SynthesisConfig(speaker_id=int(_speaker_id))
    with wave.open(buf, "wb") as wav_file:
        if syn_config is not None:
            _voice.synthesize_wav(text, wav_file, syn_config=syn_config)
        else:
            _voice.synthesize_wav(text, wav_file)
    return buf.getvalue()
