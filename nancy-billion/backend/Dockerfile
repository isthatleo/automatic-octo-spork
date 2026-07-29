# Nancy Backend Dockerfile
#
# Build context: automatic-octo-spork/ (two levels up from here), not
# backend/ alone -- see docker-compose.yml. requirements.txt's first line
# ("-e ../../fury-main[tts]") is a REAL, required dependency (tools.py does
# an unguarded `from fury.types import create_tool` at import time -- this
# is not optional the way NeuTTS's use of fury is), so fury-main has to
# actually be reachable in the build context, not excluded.
#
# The [tts] extra itself IS skipped -- fury-sdk's pyproject.toml shows its
# base install needs only httpx/numpy/termcolor, while [tts] pulls in
# torch/llama-cpp-python/onnxruntime/neucodec for the NeuTTS neural voice.
# tts.py's get_tts_backend() already falls back to Pyttsx3TTS if NeuTTS
# construction fails for any reason, so the app runs correctly on the base
# install alone -- just with the lighter espeak-based voice instead of the
# neural one.
# Pinned to bookworm (Debian 12), not the floating `python:3.11-slim` tag --
# that now resolves to Debian 13 "trixie", which renamed several font
# packages (ttf-unifont -> fonts-unifont, ttf-ubuntu-font-family dropped
# entirely) that `playwright install --with-deps` hardcodes by their old
# names, failing the build outright. bookworm is Playwright's actual tested
# target and avoids this whole class of package-name churn.
FROM python:3.11-slim-bookworm

WORKDIR /app

# gcc: fallback source builds for any wheel-less package.
# ffmpeg: audio format conversion for the STT/voice pipeline.
# espeak-ng: real backend for pyttsx3's Linux voice output (see TTS_BACKEND below).
# libportaudio2: sounddevice's runtime dependency.
# curl: container healthcheck.
# iputils-ping: real ICMP presence detection (presence_store.py) -- confirmed
# live this container can actually reach real LAN IPs (Docker's default
# bridge networking NATs outbound LAN traffic same as internet traffic), it
# just had no `ping` binary at all until now.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    ffmpeg \
    espeak-ng \
    libportaudio2 \
    curl \
    iputils-ping \
    && rm -rf /var/lib/apt/lists/* \
    # Some tooling (pyttsx3's Linux driver among it) still looks for the
    # classic `espeak` binary name specifically -- espeak-ng is command-line
    # compatible enough for that use, so this symlink is a real, safe
    # convenience rather than pulling in the separate (larger, and in
    # trixie/bookworm sometimes conflicting) classic espeak package. Not the
    # actual fix for NeuTTS's "espeak not installed on your system" error,
    # though -- that turned out to be docker-compose.yml's
    # PHONEMIZER_ESPEAK_LIBRARY override (see there): the real .env value is
    # a Windows path, meaningless inside this Linux container regardless of
    # what binaries/symlinks exist.
    && ln -s /usr/bin/espeak-ng /usr/bin/espeak

COPY fury-main ./fury-main
RUN pip install --no-cache-dir ./fury-main

COPY nancy-billion/backend/requirements.txt .
RUN grep -v '^-e ' requirements.txt > requirements.docker.txt \
    && pip install --no-cache-dir -r requirements.docker.txt

# Real headless Chromium for browser_tool.py -- --with-deps pulls the actual
# system libraries Chromium needs (this base image has none of them); the
# pip package above only gets the Python driver, not a real browser binary.
RUN playwright install --with-deps chromium

COPY nancy-billion/backend/ .

RUN mkdir -p /app/data

ENV TTS_BACKEND=pyttsx3 \
    HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Real endpoint (see main_new.py's @app.get("/system/health")) -- the
# previous healthcheck hit a nonexistent /health path via the `requests`
# package, which isn't even a project dependency (this app uses httpx).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/system/health || exit 1

CMD ["python", "main_new.py"]
