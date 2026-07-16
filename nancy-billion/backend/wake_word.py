import logging
import threading
import time
import os
from abc import ABC, abstractmethod
import numpy as np
import sounddevice as sd

from clap_detection import clap_detector, SAMPLE_RATE as CLAP_SAMPLE_RATE


logger = logging.getLogger(__name__)

class WakeWordDetector(ABC):
    @abstractmethod
    def start(self, callback):
        """
        Start listening in a background thread.
        callback() will be called when a wake word is detected.
        """
        pass

    @abstractmethod
    def stop(self):
        pass

class ClapWakeWord(WakeWordDetector):
    """Listens on the backend host's own microphone via sounddevice and fires
    the wake callback on a clap. Uses the shared clap_detector (clap_detection.py)
    so this and the browser-side WS path (main_new.py's "clap_chunk" message,
    for setups where the backend has no mic of its own) load one set of
    weights instead of two independent copies of the model.
    """

    def __init__(self):
        self.stream = None
        self.running = False
        self.callback = None
        self.chunk_duration = 0.5  # seconds
        self.sample_rate = CLAP_SAMPLE_RATE
        self.chunk_samples = int(self.chunk_duration * self.sample_rate)
        self.audio_buffer = np.zeros(self.chunk_samples, dtype=np.float32)

        if not clap_detector.is_available:
            logger.warning(
                "Clap wake word inactive: %s", clap_detector.status["error"]
            )

    def _audio_callback(self, indata, frames, time, status):
        if status:
            logger.warning(f"Audio stream status: {status}")
        if not clap_detector.is_available:
            return

        # indata shape: (frames, channels); we take first channel
        audio_chunk = indata[:, 0].astype(np.float32) / 32768.0 if indata.dtype == np.int16 else indata[:, 0]
        self.audio_buffer = np.roll(self.audio_buffer, -len(audio_chunk))
        self.audio_buffer[-len(audio_chunk):] = audio_chunk

        try:
            result = clap_detector.predict(self.audio_buffer)
            if result.is_clap and result.confidence > float(os.getenv("CLAP_DETECT_THRESHOLD", "0.6")):
                logger.info(f"Clap detected! confidence={result.confidence:.3f}")
                if self.callback:
                    self.callback()
        except Exception as e:
            logger.error(f"Error in wake word processing: {e}")

    def start(self, callback):
        self.callback = callback
        self.running = True
        # Find default input device
        devices = sd.query_devices()
        default_input = sd.default.device[0]
        logger.info(f"Using audio input device: {default_input} ({devices[default_input]['name']})")
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype='int16',
            callback=self._audio_callback,
            blocksize=self.chunk_samples
        )
        self.stream.start()
        logger.info("Clap wake word detector started.")

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
        logger.info("Clap wake word detector stopped.")

# Voice trigger stub (to be implemented with Porcupine/Vosk)
class VoiceWakeWord(WakeWordDetector):
    """Production-grade keyword spotting via Whisper-based streaming.

    Approach:
    - Capture audio continuously from mic using sounddevice.
    - Maintain a rolling buffer.
    - Every VAD-ish interval, transcribe the buffer using faster-whisper.
    - If transcript contains 'nancy' or 'billion' (with light normalization), trigger callback.

    This is not as CPU-cheap as Porcupine, but it is functional and robust without
    extra model assets.
    """

    def __init__(
        self,
        keywords=("nancy", "billion", "jarvis"),
        *,
        sample_rate: int = 16000,
        chunk_seconds: float = 0.5,
        buffer_seconds: float = 3.0,
        cooldown_seconds: float = 3.0,
        model_size: str | None = None,
    ):
        self.keywords = [k.lower() for k in keywords]
        self.sample_rate = sample_rate
        self.chunk_seconds = chunk_seconds
        self.buffer_seconds = buffer_seconds
        self.cooldown_seconds = cooldown_seconds
        self.model_size = model_size or os.getenv("VOICE_WAKEWORD_MODEL", "tiny.en")

        self.model = None
        self.audio_buffer = np.zeros((int(self.buffer_seconds * self.sample_rate),), dtype=np.float32)
        self._write_ptr_samples = 0
        self._last_trigger_ts = 0.0

        self.stream = None
        self.running = False
        self.callback = None
        self._load_model()

    def _load_model(self):
        try:
            from faster_whisper import WhisperModel

            device = os.getenv("WHISPER_DEVICE", "cpu")
            compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
            self.model = WhisperModel(self.model_size, device=device, compute_type=compute_type)
            logger.info(f"Voice wake word WhisperModel loaded: {self.model_size} ({device}, {compute_type})")
        except Exception as e:
            logger.error(f"Failed to init Whisper for voice wakeword: {e}")
            self.model = None

    def _maybe_trigger(self, text: str):
        if not text:
            return
        now = time.time()
        if now - self._last_trigger_ts < self.cooldown_seconds:
            return

        t = text.lower()
        # very small normalization
        t = t.replace("-", " ")
        words = set(t.split())
        if any(k in words or k in t for k in self.keywords):
            self._last_trigger_ts = now
            logger.info(f"Voice wake word detected in transcript: '{text}'")
            if self.callback:
                # Nancy/Billion is a fully female British persona.
                # Trigger wake-word callback uniformly (regardless of which detector fired).
                self.callback()


    def _transcribe_buffer(self):
        if self.model is None:
            return ""

        # Faster-whisper expects float32 in [-1,1]
        segments, _info = self.model.transcribe(
            self.audio_buffer,
            beam_size=1,
            vad_filter=True,
        )
        return "".join(seg.text for seg in segments).strip()

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.debug(f"VoiceWakeWord audio status: {status}")

        # sounddevice returns int16 if configured; normalize to float32
        if indata.dtype == np.int16:
            chunk = indata[:, 0].astype(np.float32) / 32768.0
        else:
            chunk = indata[:, 0].astype(np.float32)

        n = len(chunk)
        buf_n = len(self.audio_buffer)
        if n >= buf_n:
            self.audio_buffer[:] = chunk[-buf_n:]
        else:
            # roll left then append
            self.audio_buffer = np.roll(self.audio_buffer, -n)
            self.audio_buffer[-n:] = chunk

    def start(self, callback):
        self.callback = callback
        self.running = True

        if self.model is None:
            logger.warning("Voice wake word disabled because Whisper model failed to load.")
            return

        blocksize = int(self.chunk_seconds * self.sample_rate)

        # Start mic stream
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype='int16',
            callback=self._audio_callback,
            blocksize=blocksize,
        )
        self.stream.start()
        logger.info("Voice wake word detector started.")

        # Background transcription loop
        def loop():
            # Transcribe periodically (not every callback) to control CPU
            interval = float(os.getenv("VOICE_WAKEWORD_TRANSCRIBE_INTERVAL", "1.5"))
            while self.running:
                try:
                    text = self._transcribe_buffer()
                    if text:
                        self._maybe_trigger(text)
                except Exception as e:
                    logger.error(f"VoiceWakeWord transcription error: {e}")
                time.sleep(interval)

        threading.Thread(target=loop, daemon=True).start()

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
        logger.info("Voice wake word detector stopped.")

def get_wake_word_detector():
    # Combine multiple detectors? For now, we can choose one or run both.
    # We'll return a composite that starts both.
    class CompositeWakeWord(WakeWordDetector):
        def __init__(self):
            self.detectors = [ClapWakeWord(), VoiceWakeWord()]

        def start(self, callback):
            for d in self.detectors:
                d.start(callback)

        def stop(self):
            for d in self.detectors:
                d.stop()
    return CompositeWakeWord()