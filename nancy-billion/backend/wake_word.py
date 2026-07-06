import logging
import threading
import time
import os
from abc import ABC, abstractmethod
import numpy as np
import sounddevice as sd
import torch


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
    def __init__(self):
        # Reuse the existing clap detection model from clap-detection-main
        # We'll load the model and set up the audio stream.
        self.model = None
        self.transform_audio = None
        self.stream = None
        self.running = False
        self.callback = None
        self.chunk_duration = 0.5  # seconds
        self.buffer_duration = 1.0
        self.sample_rate = 44100
        self.chunk_samples = int(self.chunk_duration * self.sample_rate)
        self.buffer_samples = int(self.buffer_duration * self.sample_rate)
        self.audio_buffer = np.zeros(self.buffer_samples, dtype=np.float32)
        self._load_model()

    def _load_model(self):
        # Import the predict module from clap-detection-main
        # We assume the clap-detection-main folder is accessible via PYTHONPATH or we copy the needed files.
        # For simplicity, we'll import directly if possible.
        try:
            import sys
            import torch

            clap_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../clap-detection-main'))
            if clap_dir not in sys.path:
                sys.path.append(clap_dir)

            from predict import transform_audio, load_model

            # clap-detection-main expects a torch checkpoint path.
            # Provide via env or fall back to a local default filename.
            model_path = os.getenv(
                "CLAP_MODEL_PATH",
                os.path.join(clap_dir, "audio_classifier.pth"),
            )
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"Clap model file not found: {model_path}")

            self.model = load_model(model_path)
            self.transform_audio = transform_audio
            # sanity: torch model stays on CPU for compatibility
            self.model.to(torch.device("cpu"))

            logger.info(f"Clap detection model loaded from: {model_path}")
        except Exception as e:
            logger.error(f"Failed to load clap detection model: {e}")
            self.model = None
            self.transform_audio = None


    def _audio_callback(self, indata, frames, time, status):
        if status:
            logger.warning(f"Audio stream status: {status}")
        # indata shape: (frames, channels); we take first channel
        audio_chunk = indata[:, 0].astype(np.float32) / 32768.0 if indata.dtype == np.int16 else indata[:, 0]
        # Update buffer
        self.audio_buffer = np.roll(self.audio_buffer, -len(audio_chunk))
        self.audio_buffer[-len(audio_chunk):] = audio_chunk
        # Process if we have enough for a chunk and model is available
        if len(self.audio_buffer) >= self.chunk_samples and self.model is not None and self.transform_audio is not None:
            chunk = self.audio_buffer[-self.chunk_samples:]
            # Transform to mel spectrogram
            try:
                spec = self.transform_audio(chunk)
                # spec returned by clap-detection-main/predict.transform_audio is already shaped for the model.
                # In this repo's implementation: spec is resized and normalized, then spec.unsqueeze(0).
                # So model expects input with shape (B, 1, H, W).

                with torch.no_grad():
                    out = self.model(spec if isinstance(spec, torch.Tensor) else torch.tensor(spec))
                    # out is log_softmax over 2 classes; convert to probabilities.
                    probs = torch.exp(out)
                    # class 1 == Clap, class 0 == Noise (per README/predict.py)
                    clap_prob = float(probs[0, 1].item())

                if clap_prob > float(os.getenv("CLAP_DETECT_THRESHOLD", "0.6")):
                    logger.info(f"Clap detected! clap_prob={clap_prob:.3f}")
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