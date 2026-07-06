"""
Voice Streaming Service for Nancy/Billion

Provides:
- Real-time STT streaming
- Wake word detection
- Streaming TTS response
- Response time optimization (300-500ms target)
"""

import logging
import asyncio
from typing import AsyncGenerator, Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class VoiceState(Enum):
    """Voice UI states"""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"


class WakeWordDetector:
    """
    Detects wake words to activate Nancy.

    Supported wake words:
    - "Nancy"
    - "Billion"
    - "Jarvis"
    """

    WAKE_WORDS = ["nancy", "billion", "jarvis"]
    CONFIDENCE_THRESHOLD = 0.7

    def __init__(self):
        self.detection_history = []

    def detect(self, text: str) -> Optional[str]:
        """
        Detect wake word in text.

        Returns:
            Wake word if detected, None otherwise
        """
        text_lower = text.lower().strip()

        for wake_word in self.WAKE_WORDS:
            if wake_word in text_lower:
                logger.info(f"Wake word detected: {wake_word}")
                self.detection_history.append(wake_word)
                return wake_word

        return None

    def should_activate(self, text: str) -> bool:
        """
        Determine if we should activate voice mode.

        Returns True if:
        - Wake word detected at start
        - Or recent detection within context
        """
        words = text.lower().split()

        # Check if starts with wake word
        if words and words[0] in self.WAKE_WORDS:
            return True

        # Check recent history
        if self.detection_history and self.detection_history[-1] == words[0]:
            return True

        return False


class StreamingVoiceResponse:
    """
    Handles streaming voice responses.

    Streams:
    - Text chunks as they're generated
    - Audio chunks as they're synthesized
    - Animation frames synchronized with speech
    """

    def __init__(self, on_text_chunk: Optional[Callable] = None, on_audio_chunk: Optional[Callable] = None):
        self.on_text_chunk = on_text_chunk
        self.on_audio_chunk = on_audio_chunk
        self.buffer = ""
        self.is_streaming = False

    async def stream_response(self, llm_generator: AsyncGenerator) -> AsyncGenerator:
        """
        Stream response from LLM.

        Yields chunks as they arrive.
        """
        self.is_streaming = True
        word_buffer = ""

        try:
            async for chunk in llm_generator:
                self.buffer += chunk
                word_buffer += chunk

                # Yield complete sentences/words
                if any(delimiter in word_buffer for delimiter in [" ", "\n", ".", "!", "?"]):
                    if self.on_text_chunk:
                        self.on_text_chunk(word_buffer)

                    yield {
                        "type": "text_chunk",
                        "data": word_buffer,
                        "timestamp": asyncio.get_event_loop().time()
                    }

                    word_buffer = ""

        finally:
            # Flush remaining
            if word_buffer and self.on_text_chunk:
                self.on_text_chunk(word_buffer)

            self.is_streaming = False
            yield {
                "type": "complete",
                "data": self.buffer,
                "timestamp": asyncio.get_event_loop().time()
            }

    async def stream_audio(self, audio_generator: AsyncGenerator) -> AsyncGenerator:
        """
        Stream audio chunks for TTS.

        Yields audio as it's synthesized.
        """
        try:
            async for audio_chunk in audio_generator:
                yield {
                    "type": "audio",
                    "data": audio_chunk,  # Base64 encoded WAV
                    "timestamp": asyncio.get_event_loop().time()
                }
        except Exception as e:
            logger.error(f"Audio streaming error: {e}")
            yield {
                "type": "error",
                "error": str(e)
            }


class VoiceAnimationSync:
    """
    Synchronizes voice with animations.

    Coordinates:
    - Orb state changes
    - Text display
    - Audio playback
    - Animation frames
    """

    def __init__(self):
        self.current_state = VoiceState.IDLE
        self.animation_queue = []

    def get_state_animation(self, state: VoiceState) -> dict:
        """
        Get animation config for voice state.

        Returns animation keyframes for frontend.
        """
        animations = {
            VoiceState.IDLE: {
                "orb": {"scale": 1.0, "opacity": 0.8, "glow": 0.5},
                "pulse": {"enabled": False},
                "rotation": 0
            },
            VoiceState.LISTENING: {
                "orb": {"scale": 1.1, "opacity": 1.0, "glow": 1.0},
                "pulse": {"enabled": True, "frequency": 2},  # Hz
                "rotation": {"speed": 360, "direction": "cw"}  # degrees/sec
            },
            VoiceState.PROCESSING: {
                "orb": {"scale": 0.95, "opacity": 0.9, "glow": 0.8},
                "pulse": {"enabled": True, "frequency": 3},
                "rotation": {"speed": 180, "direction": "ccw"}
            },
            VoiceState.SPEAKING: {
                "orb": {"scale": 1.05, "opacity": 1.0, "glow": 1.2},
                "pulse": {"enabled": True, "frequency": 1.5},
                "rotation": 0,
                "audio_sync": True  # Pulse to audio frequency
            }
        }

        return animations.get(state, animations[VoiceState.IDLE])

    def transition_state(self, from_state: VoiceState, to_state: VoiceState) -> dict:
        """
        Get transition animation between states.
        """
        return {
            "from": from_state.value,
            "to": to_state.value,
            "duration_ms": 300,
            "easing": "ease-in-out"
        }

    def sync_with_audio(self, audio_level: float) -> dict:
        """
        Get animation frame synchronized with audio level.

        Args:
            audio_level: 0.0-1.0 audio volume

        Returns animation frame for that audio level.
        """
        return {
            "orb": {
                "scale": 1.0 + (audio_level * 0.1),
                "glow": 0.5 + (audio_level * 0.7)
            },
            "timestamp": asyncio.get_event_loop().time()
        }


class VoiceLatencyOptimizer:
    """
    Optimizes for 300-500ms response time.

    Tracks:
    - STT latency
    - LLM generation latency
    - TTS synthesis latency
    - Total latency
    """

    def __init__(self):
        self.latencies = {
            "stt": [],
            "llm": [],
            "tts": [],
            "total": []
        }
        self.target_latency_ms = 400

    def record_latency(self, component: str, latency_ms: float):
        """Record latency for a component"""
        if component in self.latencies:
            self.latencies[component].append(latency_ms)
            logger.debug(f"{component} latency: {latency_ms}ms")

    def get_average_latency(self, component: str) -> float:
        """Get average latency for component"""
        if component not in self.latencies or not self.latencies[component]:
            return 0.0

        return sum(self.latencies[component]) / len(self.latencies[component])

    def get_optimization_hints(self) -> dict:
        """
        Suggest optimizations to meet 300-500ms target.
        """
        total_avg = sum(
            self.get_average_latency(c)
            for c in ["stt", "llm", "tts"]
        )

        hints = {
            "total_latency_ms": total_avg,
            "target_latency_ms": self.target_latency_ms,
            "status": "on_target" if total_avg <= self.target_latency_ms else "needs_optimization"
        }

        # Component-specific hints
        if self.get_average_latency("stt") > 150:
            hints["stt_hint"] = "STT is slow - consider local model"

        if self.get_average_latency("llm") > 300:
            hints["llm_hint"] = "LLM is slow - use faster model or streaming"

        if self.get_average_latency("tts") > 200:
            hints["tts_hint"] = "TTS is slow - use cached or streaming TTS"

        return hints


# Example usage
if __name__ == "__main__":
    detector = WakeWordDetector()

    # Test wake word detection
    test_phrases = [
        "Nancy, what's the weather?",
        "Hey Jarvis, play music",
        "Billion, analyze this trade"
    ]

    for phrase in test_phrases:
        wake_word = detector.detect(phrase)
        print(f"'{phrase}' → Wake word: {wake_word}")

    # Test animation sync
    sync = VoiceAnimationSync()

    for state in VoiceState:
        anim = sync.get_state_animation(state)
        print(f"{state.value}: {anim}")

