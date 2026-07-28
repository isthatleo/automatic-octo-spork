"""Real pluggable-vendor ABCs -- ported in spirit from Hermes' image/video/TTS/
transcription/web-search provider registries and OpenClaw's music-generation/
browser-provider abstractions. One capability, many interchangeable vendors;
Nancy already has this exact shape for LLM backends (llm.py's FallbackLLM /
get_llm_backends()) -- these are the same idea generalized past LLM text
generation.

Each ABC exposes exactly one async method so a vendor adapter is a small,
focused module (see providers/web_search/brave.py for the reference
implementation), not a kitchen-sink client.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class WebSearchProvider(ABC):
    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Returns a list of {"title", "url", "snippet"} dicts."""


class ImageProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, **kw: Any) -> Dict[str, Any]:
        """Returns {"success", "url"|"data_base64", "error"?}."""


class VideoProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, **kw: Any) -> Dict[str, Any]:
        """Returns {"success", "url", "error"?}."""


class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str, **kw: Any) -> Dict[str, Any]:
        """Returns {"success", "audio_base64"|"url", "error"?}."""


class TranscriptionProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, **kw: Any) -> Dict[str, Any]:
        """Returns {"success", "text", "error"?}."""


class MusicGenProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, **kw: Any) -> Dict[str, Any]:
        """Returns {"success", "url", "error"?}."""


class BrowserProvider(ABC):
    @abstractmethod
    async def open_session(self, url: str, **kw: Any) -> Dict[str, Any]:
        """Opens a real remote/cloud browser session at `url`. Returns
        {"success", "session_id", "error"?} -- further interaction (screenshot,
        click, get_text) is provider-specific and out of scope for this ABC;
        callers needing that use the returned session_id with the provider's
        own client directly."""


class TelephonyProvider(ABC):
    @abstractmethod
    async def place_call(self, to_number: str, **kw: Any) -> Dict[str, Any]:
        """Returns {"success", "call_id", "error"?}."""

    async def send_sms(self, to_number: str, message: str) -> Dict[str, Any]:
        """Not abstract -- not every telephony vendor's API necessarily
        covers SMS the same way it covers voice calls. Default: unsupported;
        a provider that does support it overrides this."""
        return {"success": False, "error": "This telephony provider does not support SMS."}


class SandboxProvider(ABC):
    @abstractmethod
    async def execute(self, command: str, **kw: Any) -> Dict[str, Any]:
        """Runs `command` in a remote/isolated sandbox. Returns
        {"success", "stdout", "stderr", "exit_code", "error"?}."""


class MemoryProvider(ABC):
    @abstractmethod
    async def add(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Returns {"success", "id"?, "error"?}."""

    @abstractmethod
    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Returns a list of {"content", "score", "metadata"} dicts."""
