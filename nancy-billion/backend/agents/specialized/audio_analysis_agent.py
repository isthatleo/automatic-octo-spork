"""
Audio Analysis Agent for Nancy/Billion.
Real waveform analysis via the standard library's `wave` module + numpy --
actual decoded samples, never a fabricated duration or amplitude.
"""
from __future__ import annotations

import base64
import io
import wave
from typing import Any, Dict

import numpy as np

from .base_specialized_agent import SpecializedAgent


class AudioAnalysisAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Audio Analysis Agent", "audio-analysis")
        self.capabilities.update({
            "description": "Real WAV waveform analysis (duration, sample rate, RMS/peak amplitude) from actual decoded samples",
            "confidence": 0.8,
            "specializations": ["waveform-analysis", "amplitude", "signal-stats"],
            "tools": ["wave", "numpy"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "analyze_wav":
            return self._analyze(task_data.get("audio_base64", ""))
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

    def _analyze(self, audio_b64: str) -> Dict[str, Any]:
        if not audio_b64:
            return {"success": False, "error": "audio_base64 is required"}
        try:
            raw = base64.b64decode(audio_b64)
            with wave.open(io.BytesIO(raw), "rb") as wf:
                channels = wf.getnchannels()
                sample_rate = wf.getframerate()
                sample_width = wf.getsampwidth()
                n_frames = wf.getnframes()
                frames = wf.readframes(n_frames)

            dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sample_width, np.int16)
            samples = np.frombuffer(frames, dtype=dtype).astype(np.float64)
            if channels > 1:
                samples = samples.reshape(-1, channels).mean(axis=1)

            max_possible = float(np.iinfo(dtype).max)
            rms = float(np.sqrt(np.mean(samples ** 2))) if len(samples) else 0.0
            peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
            duration_s = n_frames / sample_rate if sample_rate else 0.0

            return {
                "success": True,
                "duration_s": round(duration_s, 3),
                "sample_rate_hz": sample_rate,
                "channels": channels,
                "rms_amplitude_normalized": round(rms / max_possible, 4) if max_possible else None,
                "peak_amplitude_normalized": round(peak / max_possible, 4) if max_possible else None,
                "is_likely_silent": bool(peak / max_possible < 0.01) if max_possible else None,
            }
        except Exception as e:
            return {"success": False, "error": f"Could not decode WAV audio: {e}"}

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "Send me WAV audio (base64) with task type 'analyze_wav' and I'll give you real "
            "duration, sample rate, and amplitude stats from the actual decoded waveform."
        )}
