import logging
import os
import asyncio
import json
import random
import subprocess
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Dict, List

logger = logging.getLogger(__name__)

class LLMBackend(ABC):
    @abstractmethod
    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        """
        Generate text from prompt.
        """
        pass

class DummyLLM(LLMBackend):
    """A dummy LLM that returns a simple echo or canned response for testing."""
    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        # Simulate some processing delay
        await asyncio.sleep(0.5)
        responses = [
            "I understand. Let me think about that.",
            "That's an interesting point. Here's what I suggest...",
            "I've processed your request. The result is ready.",
            "As your sovereign AI, I recommend proceeding with caution.",
            f"You said: \"{prompt[:50]}...\". Here's my analysis.",
        ]
        return random.choice(responses)

class LlamaCppLLM(LLMBackend):
    def __init__(self):
        self.model = None
        self.model_path = os.getenv("LLM_MODEL_PATH")
        self.n_ctx = int(os.getenv("LLM_N_CTX", "4096"))
        self.n_batch = int(os.getenv("LLM_N_BATCH", "512"))
        self.n_gpu_layers = int(os.getenv("LLM_N_GPU_LAYERS", "0"))
        if not self.model_path:
            logger.warning("LLM_MODEL_PATH not set; LLM will not function")
        else:
            logger.info(f"Loading LlamaCpp model from {self.model_path}")

    def _load_model(self):
        if self.model is None:
            try:
                from llama_cpp import Llama
                self.model = Llama(
                    model_path=self.model_path,
                    n_ctx=self.n_ctx,
                    n_batch=self.n_batch,
                    n_gpu_layers=self.n_gpu_layers,
                    verbose=False
                )
            except Exception as e:
                logger.error(f"Failed to load LlamaCpp model: {e}")
                raise
        return self.model

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        model = self._load_model()
        # Run in thread to avoid blocking
        loop = asyncio.get_event_loop()
        def _generate():
            output = model(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=["\n", "User:", "Assistant:"],
                echo=False
            )
            return output["choices"][0]["text"]
        return await loop.run_in_executor(None, _generate)

# =============================================================================
# New LLM Backends for various providers
# =============================================================================

class OllamaLLM(LLMBackend):
    def __init__(self, model: str | None = None):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", "llama2")
        logger.info(f"OllamaLLM initialized with base_url={self.base_url}, model={self.model}")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        import aiohttp
        import json
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get("response", "")
                else:
                    text = await resp.text()
                    raise Exception(f"Ollama error: {resp.status} - {text}")

class AnthropicLLM(LLMBackend):
    """Claude backend via the official `anthropic` SDK.

    Sampling params (temperature/top_p/top_k) are intentionally never sent —
    Claude Opus 4.8 and later reject them with a 400. Callers that need
    variance should adjust the prompt, not this backend's `temperature` param
    (kept only for LLMBackend interface compatibility).
    """

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set; Anthropic LLM will not function")
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8")
        self._client = None
        logger.info(f"AnthropicLLM initialized with model={self.model}")

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        effort: str | None = None,
    ) -> str:
        if not self.api_key:
            raise Exception("ANTHROPIC_API_KEY not configured")
        client = self._get_client()
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if effort:
            kwargs["output_config"] = {"effort": effort}
        try:
            response = await client.messages.create(**kwargs)
        except Exception as e:
            raise Exception(f"Anthropic error: {e}")
        for block in response.content:
            if block.type == "text":
                return block.text
        raise Exception("Anthropic returned no text content")

    async def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        effort: str | None = None,
    ):
        """Yield text deltas as they arrive. Not part of the LLMBackend interface
        (other backends don't stream yet) — call directly when streaming is wanted."""
        if not self.api_key:
            raise Exception("ANTHROPIC_API_KEY not configured")
        client = self._get_client()
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if effort:
            kwargs["output_config"] = {"effort": effort}
        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    async def generate_with_tools(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        tool_executor: Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]],
        max_tokens: int = 1024,
        max_rounds: int = 5,
    ) -> str:
        """Full Claude tool-use loop: send `prompt` + `tools`, execute any
        requested tool calls via `tool_executor(name, input) -> result_dict`,
        feed results back as tool_result blocks, repeat until Claude stops
        requesting tools or `max_rounds` is hit.

        Not part of the LLMBackend interface (other backends don't do tool
        use yet) -- call directly when tool-enabled generation is wanted, same
        pattern as generate_stream.
        """
        if not self.api_key:
            raise Exception("ANTHROPIC_API_KEY not configured")
        client = self._get_client()
        messages: List[Dict[str, Any]] = [{"role": "user", "content": prompt}]

        for _ in range(max_rounds):
            try:
                response = await client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    messages=messages,
                    tools=tools,
                )
            except Exception as e:
                raise Exception(f"Anthropic error: {e}")

            if response.stop_reason != "tool_use":
                for block in response.content:
                    if block.type == "text":
                        return block.text
                return ""

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                try:
                    result = await tool_executor(block.name, block.input)
                except Exception as e:
                    result = {"success": False, "error": str(e)}
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })
            messages.append({"role": "user", "content": tool_results})

        raise Exception("Exceeded max tool-use rounds without a final answer")

class OpenAILLM(LLMBackend):
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set; OpenAI LLM will not function")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
        logger.info(f"OpenAILLM initialized with model={self.model}")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        import aiohttp
        import json
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    text = await resp.text()
                    raise Exception(f"OpenAI error: {resp.status} - {text}")

class GeminiLLM(LLMBackend):
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not set; Gemini LLM will not function")
        self.model = os.getenv("GEMINI_MODEL", "gemini-pro")
        logger.info(f"GeminiLLM initialized with model={self.model}")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        import aiohttp
        import json
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature
            }
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    text = await resp.text()
                    raise Exception(f"Gemini error: {resp.status} - {text}")

class OpenRouterLLM(LLMBackend):
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not set; OpenRouter LLM will not function")
        self.model = os.getenv("OPENROUTER_MODEL", "openrouter/auto")
        logger.info(f"OpenRouterLLM initialized with model={self.model}")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        import aiohttp
        import json
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    text = await resp.text()
                    raise Exception(f"OpenRouter error: {resp.status} - {text}")

class GroqLLM(LLMBackend):
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            logger.warning("GROQ_API_KEY not set; Groq LLM will not function")
        self.model = os.getenv("GROQ_MODEL", "mixtral-8x7b-32768")
        logger.info(f"GroqLLM initialized with model={self.model}")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        import aiohttp
        import json
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    text = await resp.text()
                    raise Exception(f"Groq error: {resp.status} - {text}")


class OpenCodeLLM(LLMBackend):
    """OpenCode Zen (opencode.ai/zen) -- a curated, pay-per-use gateway to
    GPT/Claude/open-source models aimed at coding agents, one API key for all
    of them. OpenAI-chat-completions-compatible endpoint. See
    https://opencode.ai/docs/zen/ -- model ids are bare (e.g. 'big-pickle',
    'gpt-5.5'), confirmed against the live /v1/models list; the 'opencode/'
    -prefixed form in some docs examples is only their JS AI-SDK provider
    registry convention, not what this raw REST endpoint expects.
    """

    def __init__(self):
        self.api_key = os.getenv("OPENCODE_API_KEY")
        if not self.api_key:
            logger.warning("OPENCODE_API_KEY not set; OpenCode Zen LLM will not function")
        self.model = os.getenv("OPENCODE_MODEL", "big-pickle")
        logger.info(f"OpenCodeLLM initialized with model={self.model}")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        import aiohttp
        url = "https://opencode.ai/zen/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"OpenCode Zen error: {resp.status} - {text}")
                result = await resp.json()
                content = result["choices"][0]["message"].get("content")
                if not content:
                    # Reasoning models (e.g. big-pickle) can spend the whole
                    # max_tokens budget on internal reasoning and never reach
                    # a final answer (finish_reason: "length", content: null).
                    # Treat that as a failure so FallbackLLM moves on, instead
                    # of returning None/empty as if it were a real reply.
                    reason = result["choices"][0].get("finish_reason", "unknown")
                    raise Exception(f"OpenCode Zen returned no content (finish_reason={reason})")
                return content

# =============================================================================
# Fallback LLM Backend
# =============================================================================

def _get_ollama_models() -> list[str]:
    """Return installed Ollama model tags, newest-first.

    Uses `ollama list` CLI so we can auto-detect whatever is installed.
    """
    try:
        # PowerShell-friendly execution from Python
        cmd = ["ollama", "list", "--format", "json"]
        # Newer Ollama supports --format json; if not supported we'll fall back.
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        out = (proc.stdout or "").strip()
        if proc.returncode == 0 and out:
            import json as _json
            data = _json.loads(out)
            # Expected shape: [{"name": "llama3.2:3b", ...}, ...] or {"models": [...]}.
            if isinstance(data, list):
                models = [m.get("name") or m.get("model") for m in data]
            else:
                models = [m.get("name") or m.get("model") for m in data.get("models", [])]
            models = [m for m in models if m]
            return models
    except Exception:
        pass

    # Fallback: parse human output of `ollama list`
    proc = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=False)
    out = (proc.stdout or "").splitlines()
    models: list[str] = []
    for line in out:
        line = line.strip()
        if not line or line.lower().startswith("models"):
            continue
        # Typical row: <tag> <size> <modified>
        parts = line.split()
        if not parts:
            continue
        tag = parts[0]
        # Skip headers like "NAME".
        if tag.lower() == "name":
            continue
        models.append(tag)
    return models


class OllamaAutoModelsLLM(LLMBackend):
    """Try all locally installed Ollama models until one succeeds."""

    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        logger.info(f"OllamaAutoModelsLLM initialized with base_url={self.base_url}")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        models = _get_ollama_models()
        if not models:
            raise Exception("No Ollama models found via `ollama list`")

        last_exception: Exception | None = None
        # Keep ordering from ollama list output.
        for model in models:
            try:
                logger.info(f"Trying Ollama model: {model}")
                ollama = OllamaLLM(model=model)
                result = await ollama.generate(prompt, max_tokens=max_tokens, temperature=temperature)
                logger.info(f"Ollama model succeeded: {model}")
                return result
            except Exception as e:
                logger.warning(f"Ollama model failed: {model} - {e}")
                last_exception = e
                continue
        raise last_exception or Exception("All Ollama models failed")


class FuryLLM(LLMBackend):
    """Fallback LLM using Fury's Agent runner.

    This uses the local Fury stack (model from LLM_MODEL_PATH) and the same tool set.
    """

    def __init__(self):
        self.system_prompt = os.getenv(
            "FURY_SYSTEM_PROMPT",
            "You are Nancy/Billion, a sovereign AI operating system.",
        )
        self.model = os.getenv("LLM_MODEL_PATH", "llamafactory/Llama-3-8B-Instruct-GGUF")

        # Import lazily to avoid import cycles during module import.
        # Fury package may not be installed in this backend environment.
        try:
            from fury import Agent
            from tools import get_tools

            self._tools = get_tools()
            self._agent = Agent(
                model=self.model,
                system_prompt=self.system_prompt,
                tools=self._tools,
            )
        except Exception as e:
            raise RuntimeError(f"FuryLLM unavailable: {e}")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        # Fury examples show using agent.runner().chat(history)
        # We pass history as a minimal list because our server already builds the full prompt.
        history = [{"role": "user", "content": prompt}]
        runner = self._agent.runner()

        buffer = ""
        async for event in runner.chat(history):
            if getattr(event, "content", None):
                buffer += event.content

        if not buffer:
            raise Exception("Fury generated empty response")
        return buffer


class FallbackLLM(LLMBackend):
    def __init__(self, backends):
        self.backends = backends
        logger.info(f"FallbackLLM initialized with {len(self.backends)} backends")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        last_exception = None
        for backend in self.backends:
            try:
                logger.info(f"Trying LLM backend: {backend.__class__.__name__}")
                result = await backend.generate(prompt, max_tokens=max_tokens, temperature=temperature)
                logger.info(f"LLM backend {backend.__class__.__name__} succeeded")
                return result
            except Exception as e:
                logger.warning(f"LLM backend {backend.__class__.__name__} failed: {e}")
                last_exception = e
                continue
        # If all backends failed, raise the last exception
        logger.error("All LLM backends failed")
        raise last_exception

# Factory to create a list of backends from the environment variable LLM_BACKENDS
def get_llm_backends():
    """Build backend chain in priority order.

    Default chain (quality-first; local Ollama is the offline fallback, not primary):
    1) Anthropic: Claude for complex/coding tasks (if ANTHROPIC_API_KEY set)
    2) Groq: Fast cloud inference (if GROQ_API_KEY set)
    3) OpenAI: GPT for general tasks (if OPENAI_API_KEY set)
    4) Gemini: Google's LLM (if GEMINI_API_KEY set)
    5) OpenRouter: Multi-model aggregator (if OPENROUTER_API_KEY set)
    6) OpenCode Zen: Coding-focused model gateway (if OPENCODE_API_KEY set)
    7) Ollama: try ALL locally installed models (free, works offline, lower quality/speed
       on CPU-only hardware) -- used when no cloud backend is configured or all of them fail
    8) Fury: Local Fury model if available
    9) DummyLLM: Fallback for testing

    If a backend succeeds, we stop searching (enforced by FallbackLLM).
    """

    backends: list[LLMBackend] = []

    # ---- PHASE 1: Cloud (best quality first) ----
    # Anthropic: Claude is excellent for coding, complex reasoning, writing
    if os.getenv("ANTHROPIC_API_KEY"):
        logger.info("Adding AnthropicLLM as primary backend (best quality)")
        backends.append(AnthropicLLM())

    # Groq: Lightning-fast inference (best for quick responses)
    if os.getenv("GROQ_API_KEY"):
        logger.info("Adding GroqLLM as fast cloud backend")
        backends.append(GroqLLM())

    # OpenAI: GPT models for general tasks
    if os.getenv("OPENAI_API_KEY"):
        logger.info("Adding OpenAILLM as general-purpose cloud backend")
        backends.append(OpenAILLM())

    # Gemini: Google's LLM for multimodal support
    if os.getenv("GEMINI_API_KEY"):
        logger.info("Adding GeminiLLM as multimodal cloud backend")
        backends.append(GeminiLLM())

    # OpenRouter: Aggregator with many models
    if os.getenv("OPENROUTER_API_KEY"):
        logger.info("Adding OpenRouterLLM as aggregator backend")
        backends.append(OpenRouterLLM())

    # OpenCode Zen: coding-focused model gateway
    if os.getenv("OPENCODE_API_KEY"):
        logger.info("Adding OpenCodeLLM as coding-focused cloud backend")
        backends.append(OpenCodeLLM())

    # ---- PHASE 2: Local (free, offline fallback) ----
    disable_auto_ollama = os.getenv("DISABLE_AUTO_OLLAMA", "0").strip() == "1"
    if not disable_auto_ollama:
        logger.info("Adding OllamaAutoModelsLLM as offline fallback backend")
        backends.append(OllamaAutoModelsLLM())

    # ---- PHASE 3: Local advanced (if available) ----
    disable_fury = os.getenv("DISABLE_FURY", "0").strip() == "1"
    if not disable_fury:
        try:
            import fury  # noqa: F401
            logger.info("Adding FuryLLM as advanced local backend")
            backends.append(FuryLLM())
        except Exception as e:
            logger.debug(f"FuryLLM unavailable: {e}")

    # ---- PHASE 4: Legacy configured providers (if LLM_BACKENDS env var set) ----
    backends_env = os.getenv("LLM_BACKENDS", "")
    backend_names = [name.strip().lower() for name in backends_env.split(",") if name.strip()]

    for name in backend_names:
        if name == "dummy":
            backends.append(DummyLLM())
        elif name == "llama_cpp":
            backends.append(LlamaCppLLM())
        elif name == "ollama":
            # Legacy single-model fallback (only if not already added)
            if not any(isinstance(b, OllamaAutoModelsLLM) for b in backends):
                backends.append(OllamaLLM())
        else:
            logger.warning(f"Unknown LLM backend '{name}', skipping")

    # ---- PHASE 5: Final fallback ----
    if not backends:
        logger.warning("No valid LLM backends configured; using DummyLLM")
        backends.append(DummyLLM())

    logger.info(f"LLM backend chain initialized with {len(backends)} backends: {[b.__class__.__name__ for b in backends]}")
    return backends


def select_llm_for_task(task_hint: str | None = None) -> LLMBackend:
    """Select the best LLM backend for a specific task type.

    Task hints allow Nancy to use specialized LLMs for specific domains:
    - "coding", "code_review", "debugging" → Claude (excellent at code)
    - "fast_response", "quick_chat" → Groq (fastest inference)
    - "general", "research", "explanation" → OpenAI GPT (balanced)
    - "multimodal", "image_analysis" → Gemini (multimodal support)
    - None / "default" → FallbackLLM (uses full chain)
    """

    if not task_hint:
        # Return the full fallback chain
        return llm_backend

    task = task_hint.lower().strip()

    # Coding-specific tasks → Claude first, then OpenCode Zen (a gateway
    # curated for coding agents), then a local coding-specialized Ollama
    # model if one's been pulled. A real fallback chain, not a single
    # backend with nothing to catch it failing (e.g. Anthropic out of credits
    # -- previously this returned a bare AnthropicLLM() with no fallback at
    # all for coding-hinted tasks specifically).
    if any(x in task for x in [
        "coding", "code", "debug", "programming", "development", "refactor",
        "devops", "self_improvement", "self-improv", "architecture",
    ]):
        coding_backends: list[LLMBackend] = []
        if os.getenv("ANTHROPIC_API_KEY"):
            coding_backends.append(AnthropicLLM())
        if os.getenv("OPENCODE_API_KEY"):
            coding_backends.append(OpenCodeLLM())
        coding_model = os.getenv("OLLAMA_CODING_MODEL", "qwen2.5-coder:3b")
        if coding_model in _get_ollama_models():
            coding_backends.append(OllamaLLM(model=coding_model))
        if coding_backends:
            logger.info(f"Using coding-task fallback chain for: {task_hint}")
            return FallbackLLM(coding_backends)

    # Fast/chat tasks → use Groq if available
    if any(x in task for x in ["fast", "quick", "chat", "conversation", "response"]):
        try:
            if os.getenv("GROQ_API_KEY"):
                logger.info(f"Using GroqLLM for fast task: {task_hint}")
                return GroqLLM()
        except Exception as e:
            logger.warning(f"Failed to select Groq for fast task: {e}")

    # Multimodal tasks → use Gemini if available
    if any(x in task for x in ["image", "vision", "multimodal", "visual"]):
        try:
            if os.getenv("GEMINI_API_KEY"):
                logger.info(f"Using GeminiLLM for multimodal task: {task_hint}")
                return GeminiLLM()
        except Exception as e:
            logger.warning(f"Failed to select Gemini for multimodal: {e}")

    # Default to full fallback chain
    logger.info(f"Using default FallbackLLM for task: {task_hint}")
    return llm_backend


# Create the fallback LLM backend (chain of all providers)
llm_backend = FallbackLLM(get_llm_backends())