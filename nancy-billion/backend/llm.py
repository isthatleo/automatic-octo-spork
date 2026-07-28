import logging
import os
import asyncio
import json
import random
import subprocess
import time
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Dict, List, Optional

from tool_args import coerce_tool_input
from retry_util import retry_async, is_transient_llm_error
import usage_analytics

logger = logging.getLogger(__name__)

# Real, live-observed failure mode (via OpenRouter's auto-router): a model
# asked to show tool-retrieved content (a file's real text, a search result)
# will sometimes paraphrase or reconstruct plausible-looking content from its
# own training-data memory instead of quoting the tool_result it was just
# given -- confirmed live asking Nancy to read a specific line range of her
# own main_new.py: the reported line number was correct (from a real
# search_files call) but the "file content" shown afterward was entirely
# fabricated, not what read_file actually returned. Prepended as a system
# message to every tool-use call (both Claude and the OpenAI-compat
# fallbacks) since this is a real correctness risk for a coding agent
# specifically, not just a style nit.
TOOL_RESULT_FIDELITY_INSTRUCTION = (
    "When relaying content that came from a tool result -- file contents, search matches, command "
    "output, or anything else retrieved rather than reasoned about -- quote it exactly as the tool "
    "returned it. Never paraphrase, summarize from memory, or reconstruct plausible-looking content "
    "for factual material like source code or file text. If a tool result doesn't contain what's "
    "needed to answer, say so explicitly rather than filling the gap with an invented answer."
)


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
    """Real local inference via llama-cpp-python against a GGUF model file --
    fully offline, no API key, no per-token cost, works with the network
    down. Only ever constructed by get_llm_backends() when LLM_MODEL_PATH
    actually points at a file that exists (see PHASE 3 below) -- previously
    this class existed but was never reachable in the default chain at all
    (only via the legacy LLM_BACKENDS=llama_cpp opt-in, which the real .env
    never set), and LLM_MODEL_PATH was left at a literal placeholder path
    that was never a real file even when llama_cpp WAS requested."""

    def __init__(self, model_path: Optional[str] = None):
        # model_path lets get_llm_backends() construct several of these --
        # e.g. one per comma-separated entry in LLM_MODEL_PATH, so more than
        # one local GGUF model can sit in the chain (a primary plus a
        # fallback) -- falls back to reading the env var directly for
        # backward compat with the legacy LLM_BACKENDS=llama_cpp opt-in,
        # which only ever knows how to construct this with no arguments.
        self.model = None
        self.model_path = model_path or os.getenv("LLM_MODEL_PATH")
        self.n_ctx = int(os.getenv("LLM_N_CTX", "4096"))
        self.n_batch = int(os.getenv("LLM_N_BATCH", "512"))
        self.n_gpu_layers = int(os.getenv("LLM_N_GPU_LAYERS", "0"))
        if not self.model_path:
            logger.warning("LLM_MODEL_PATH not set; LlamaCppLLM will not function")
        elif not os.path.isfile(self.model_path):
            logger.warning("LLM_MODEL_PATH set to %s but that file doesn't exist; LlamaCppLLM will not function", self.model_path)
        else:
            logger.info(f"LlamaCppLLM ready, will lazy-load model from {self.model_path} on first use")

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
        loop = asyncio.get_event_loop()
        def _generate():
            # create_chat_completion (not raw completion) so llama-cpp-python
            # applies the model's own embedded chat template -- confirmed
            # live this session: raw completion against an instruct-tuned
            # model (deepreinforce-ai/Ornith-1.0-9B, a reasoning model) with
            # an un-templated prompt returned an empty string, immediately
            # hitting the stop sequence rather than actually answering.
            output = model.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return output["choices"][0]["message"]["content"] or ""
        return await loop.run_in_executor(None, _generate)

# =============================================================================
# New LLM Backends for various providers
# =============================================================================

class OllamaLLM(LLMBackend):
    def __init__(self, model: str | None = None):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", "llama2")
        self._last_usage: dict | None = None
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
                    # Ollama's real response reports exact token counts AND a
                    # real prompt-eval (prefill)/eval (decode) time split, in
                    # nanoseconds -- one of the few backends with both.
                    if "prompt_eval_count" in result or "eval_count" in result:
                        self._last_usage = {
                            "prompt_tokens": result.get("prompt_eval_count"),
                            "completion_tokens": result.get("eval_count"),
                            "prompt_time_s": result.get("prompt_eval_duration", 0) / 1e9 if result.get("prompt_eval_duration") else None,
                            "decode_time_s": result.get("eval_duration", 0) / 1e9 if result.get("eval_duration") else None,
                        }
                    return result.get("response", "")
                else:
                    text = await resp.text()
                    raise Exception(f"Ollama error: {resp.status} - {text}")

class VLLMLLM(LLMBackend):
    """Real HTTP client for a self-hosted vLLM server's OpenAI-compatible API
    (`python -m vllm.entrypoints.openai.api_server ...`). vLLM itself needs a
    real GPU and runs as its own separate process -- this class doesn't
    start or manage it, only talks to whatever's already running at
    VLLM_BASE_URL, the same relationship OllamaLLM has with `ollama serve`.
    Unlike Ollama (commonly already running locally by default), vLLM is
    only ever added to the backend chain when VLLM_BASE_URL is explicitly
    set (see get_llm_backends) -- standing up a GPU inference server isn't
    something to probe for opportunistically."""

    def __init__(self, model: str | None = None):
        self.base_url = os.getenv("VLLM_BASE_URL", "http://localhost:8001")
        self.model = model or os.getenv("VLLM_MODEL", "")
        logger.info(f"VLLMLLM initialized with base_url={self.base_url}, model={self.model or '(server default)'}")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        import aiohttp
        url = f"{self.base_url}/v1/completions"
        payload = {"model": self.model, "prompt": prompt, "max_tokens": max_tokens, "temperature": temperature}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    choices = result.get("choices") or []
                    return choices[0].get("text", "") if choices else ""
                else:
                    text = await resp.text()
                    raise Exception(f"vLLM error: {resp.status} - {text}")


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
        self._last_usage: dict | None = None
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
        # Real, exact provider-reported token counts -- Anthropic doesn't
        # expose a prompt-processing/decode time split, so only tokens are
        # populated here (prompt_time_s/decode_time_s stay unset).
        if getattr(response, "usage", None) is not None:
            self._last_usage = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            }
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
        max_rounds: int = 15,
        on_tool_image: Optional[Callable[[bytes], None]] = None,
    ) -> str:
        """Full Claude tool-use loop: send `prompt` + `tools`, execute any
        requested tool calls via `tool_executor(name, input) -> result_dict`,
        feed results back as tool_result blocks, repeat until Claude stops
        requesting tools or `max_rounds` is hit.

        A real screenshot/canvas image a tool produces (the reserved
        `_image_base64` result key) was previously only ever shown to Claude
        internally, inside the tool_result block -- the human never actually
        saw it in either the web UI or Telegram, regardless of which one
        asked for it. `on_tool_image`, if given, is called with the raw PNG
        bytes for every such image so the caller can actually surface it
        (see main_new.py's _generate_response_via_hierarchy).

        Not part of the LLMBackend interface (other backends don't do tool
        use yet) -- call directly when tool-enabled generation is wanted, same
        pattern as generate_stream.
        """
        if not self.api_key:
            raise Exception("ANTHROPIC_API_KEY not configured")
        client = self._get_client()
        messages: List[Dict[str, Any]] = [{"role": "user", "content": prompt}]
        schema_by_name = {t["name"]: t.get("input_schema", {}) for t in tools if isinstance(t, dict) and "name" in t}

        for _ in range(max_rounds):
            try:
                response = await client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=TOOL_RESULT_FIDELITY_INSTRUCTION,
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
                # Even through Claude's real structured tool-use API, an
                # argument can come back in the wrong JSON-schema shape (a
                # stringified number/bool/object) -- coerce toward the
                # tool's own declared schema before it ever reaches a
                # Python function with normal type hints. Never raises: an
                # uncoercible value passes through unchanged.
                tool_input = coerce_tool_input(block.input, schema_by_name.get(block.name, {}))
                try:
                    result = await tool_executor(block.name, tool_input)
                except Exception as e:
                    result = {"success": False, "error": str(e)}
                # Real vision support for tools that need Claude to actually
                # SEE something (take_screenshot) rather than just read a
                # text description of it -- an executor signals this with a
                # reserved `_image_base64` key; every other tool's result is
                # untouched, still a single JSON string, exactly as before.
                image_b64 = result.pop("_image_base64", None) if isinstance(result, dict) else None
                if image_b64:
                    content: Any = [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_b64}},
                        {"type": "text", "text": json.dumps(result)},
                    ]
                    if on_tool_image:
                        try:
                            import base64
                            on_tool_image(base64.b64decode(image_b64))
                        except Exception as e:
                            logger.warning("on_tool_image callback failed: %s", e)
                else:
                    content = json.dumps(result)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                })
            messages.append({"role": "user", "content": tool_results})

        raise Exception("Exceeded max tool-use rounds without a final answer")


async def generate_with_tools_openai_compat(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    tools: List[Dict[str, Any]],
    tool_executor: Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]],
    max_tokens: int = 1024,
    max_rounds: int = 15,
    provider_label: str = "backend",
    on_tool_image: Optional[Callable[[bytes], None]] = None,
) -> str:
    """Real tool-use loop for any OpenAI-chat-completions-compatible backend
    (Groq, OpenRouter, and OpenCode Zen all use this exact API shape) -- lets
    Nancy's real tool-calling (file access, terminal, canvas, ...) survive
    Anthropic being unavailable, instead of silently degrading straight to a
    tool-less plain-text guess the moment Claude's own tool-use loop fails
    (see main_new.py's _generate_response_via_hierarchy, which now tries
    this as a real fallback before giving up on tools entirely).

    Converts Nancy's Anthropic-shaped tool definitions ({name, description,
    input_schema}) to OpenAI's ({"type": "function", "function": {...}})
    format once per call; the tool_executor callback is the exact same one
    AnthropicLLM.generate_with_tools uses, so a tool behaves identically
    regardless of which backend ends up calling it.

    One real, disclosed limitation vs Claude: an executor's real screenshot
    image (the reserved _image_base64 result key) can't be shown to the
    MODEL here -- these APIs don't accept inline images in a tool result the
    way Claude's does, so the model itself never sees it. The human still
    can, though: on_tool_image (if given) still fires with the raw bytes
    before the key is dropped, same as AnthropicLLM.generate_with_tools, so
    the caller can surface the real image regardless of which backend
    handled the tool call.
    """
    import aiohttp

    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools if isinstance(t, dict) and "name" in t
    ]
    schema_by_name = {t["name"]: t.get("input_schema", {}) for t in tools if isinstance(t, dict) and "name" in t}
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": TOOL_RESULT_FIDELITY_INSTRUCTION},
        {"role": "user", "content": prompt},
    ]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        for _ in range(max_rounds):
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "tools": openai_tools,
                "tool_choice": "auto",
            }
            async with session.post(f"{base_url}/chat/completions", json=payload, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"{provider_label} error: {resp.status} - {text}")
                data = await resp.json()

            message = data["choices"][0]["message"]
            tool_calls = message.get("tool_calls")
            if not tool_calls:
                logger.info("%s: model answered without calling any tool (round used, model=%s)", provider_label, model)
                return message.get("content") or ""

            messages.append({
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": tool_calls,
            })
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                try:
                    raw_args = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    raw_args = {}
                tool_input = coerce_tool_input(raw_args, schema_by_name.get(name, {}))
                logger.info("%s: calling tool %s(%s)", provider_label, name, tool_input)
                try:
                    result = await tool_executor(name, tool_input)
                except Exception as e:
                    result = {"success": False, "error": str(e)}
                logger.info("%s: tool %s result preview: %s", provider_label, name, json.dumps(result)[:300])
                if isinstance(result, dict):
                    image_b64 = result.pop("_image_base64", None)
                    if image_b64 and on_tool_image:
                        try:
                            import base64
                            on_tool_image(base64.b64decode(image_b64))
                        except Exception as e:
                            logger.warning("on_tool_image callback failed: %s", e)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(result),
                })

    raise Exception(f"Exceeded max tool-use rounds without a final answer ({provider_label})")


class OpenAILLM(LLMBackend):
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not set; OpenAI LLM will not function")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
        self._last_usage: dict | None = None
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
                    usage = result.get("usage")
                    if usage:
                        self._last_usage = {"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")}
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
        self._last_usage: dict | None = None
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
                    usage = result.get("usageMetadata")
                    if usage:
                        self._last_usage = {
                            "prompt_tokens": usage.get("promptTokenCount"),
                            "completion_tokens": usage.get("candidatesTokenCount"),
                        }
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
        self._last_usage: dict | None = None
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
                    usage = result.get("usage")
                    if usage:
                        self._last_usage = {"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")}
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
        self._last_usage: dict | None = None
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
                    # Groq is one of the few providers that reports a real
                    # prompt-processing/decode time split (under x_groq.usage),
                    # not just token counts -- both captured when present.
                    usage = result.get("usage") or result.get("x_groq", {}).get("usage")
                    if usage:
                        self._last_usage = {
                            "prompt_tokens": usage.get("prompt_tokens"),
                            "completion_tokens": usage.get("completion_tokens"),
                            "prompt_time_s": usage.get("prompt_time"),
                            "decode_time_s": usage.get("completion_time"),
                        }
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
        self._last_usage: dict | None = None
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
                usage = result.get("usage")
                if usage:
                    self._last_usage = {"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")}
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


class ClawRouterLLM(LLMBackend):
    """ClawRouter -- a managed multi-provider model router with its own
    quota reporting, ported from OpenClaw's ClawRouter extension. Same
    OpenAI-chat-completions-compatible shape as OpenCodeLLM above; a single
    ClawRouter key stands in for routing across whichever underlying
    providers ClawRouter itself is configured to use."""

    def __init__(self):
        self.api_key = os.getenv("CLAWROUTER_API_KEY")
        if not self.api_key:
            logger.warning("CLAWROUTER_API_KEY not set; ClawRouter LLM will not function")
        self.model = os.getenv("CLAWROUTER_MODEL", "auto")
        self.base_url = os.getenv("CLAWROUTER_BASE_URL", "https://api.clawrouter.com/v1")
        self._last_usage: dict | None = None
        logger.info(f"ClawRouterLLM initialized with model={self.model}")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        import aiohttp
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"ClawRouter error: {resp.status} - {text}")
                result = await resp.json()
                usage = result.get("usage")
                if usage:
                    self._last_usage = {"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")}
                content = result["choices"][0]["message"].get("content")
                if not content:
                    raise Exception("ClawRouter returned no content")
                return content

# =============================================================================
# Fallback LLM Backend
# =============================================================================

async def _get_ollama_models(base_url: str) -> list[str]:
    """Return installed Ollama model tags via Ollama's own real /api/tags
    REST endpoint -- NOT the `ollama` CLI binary (the previous approach),
    which doesn't exist inside this backend's own Docker container even
    when Ollama itself is genuinely reachable at OLLAMA_BASE_URL (the CLI
    also has no way to respect that env var anyway -- it uses a differently
    named OLLAMA_HOST). Confirmed live this session: with the CLI approach,
    OllamaAutoModelsLLM silently found zero models and failed every attempt,
    regardless of Ollama being installed with 7 real models pulled on the
    host.

    Purely local (non ':cloud'-suffixed) models are tried before any
    ':cloud' ones -- those proxy through Ollama's own hosted service and
    need internet, which defeats the point of this being the *offline*
    fallback if a genuinely local model is also available.
    """
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
    except Exception:
        return []

    models = [m.get("name") or m.get("model") for m in data.get("models", [])]
    models = [m for m in models if m]
    models.sort(key=lambda m: m.endswith(":cloud"))
    return models


def _get_ollama_models_sync(base_url: str) -> list[str]:
    """Blocking counterpart to _get_ollama_models, for the one call site
    (select_llm_for_task, a sync function) that can't await it -- same real
    /api/tags endpoint."""
    try:
        import requests
        resp = requests.get(f"{base_url}/api/tags", timeout=3)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []
    return [m.get("name") or m.get("model") for m in data.get("models", []) if m.get("name") or m.get("model")]


class OllamaAutoModelsLLM(LLMBackend):
    """Try all locally installed Ollama models until one succeeds."""

    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._last_usage: dict | None = None
        logger.info(f"OllamaAutoModelsLLM initialized with base_url={self.base_url}")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        models = await _get_ollama_models(self.base_url)
        if not models:
            raise Exception(f"No Ollama models found at {self.base_url}/api/tags")

        last_exception: Exception | None = None
        # Keep ordering from ollama list output.
        for model in models:
            try:
                logger.info(f"Trying Ollama model: {model}")
                ollama = OllamaLLM(model=model)
                result = await ollama.generate(prompt, max_tokens=max_tokens, temperature=temperature)
                logger.info(f"Ollama model succeeded: {model}")
                self._last_usage = ollama._last_usage
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
        # LLM_MODEL_PATH may now be a comma-separated list (see LlamaCppLLM,
        # which iterates it to build several real local fallbacks) -- Fury's
        # own Agent(model=...) expects a single model identifier, so only
        # the first entry is Fury's. Without this split, a real multi-model
        # LLM_MODEL_PATH would hand Fury a literal "path1,path2" string.
        self.model = os.getenv("LLM_MODEL_PATH", "llamafactory/Llama-3-8B-Instruct-GGUF").split(",")[0].strip()

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
    # No individual backend call here (or in its own SDK client) had an
    # explicit timeout before -- a single slow/hanging backend (e.g. a big
    # cloud model under load, or a local Ollama/Fury model doing real CPU
    # inference) could block the entire chain well past a minute with
    # nothing to cut it short and move to the next backend.
    BACKEND_TIMEOUT_S = 20.0

    def __init__(self, backends):
        self.backends = backends
        logger.info(f"FallbackLLM initialized with {len(self.backends)} backends")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        last_exception = None
        for backend in self.backends:
            # Cloud backends set self.api_key from an env var and always fail
            # the same way when it's missing -- skip immediately instead of
            # burning up to BACKEND_TIMEOUT_S waiting on a call that can never
            # succeed. Local/no-key backends (Ollama, Fury, llama.cpp, Dummy)
            # have no api_key attribute at all, so they're never skipped here.
            if hasattr(backend, "api_key") and not backend.api_key:
                logger.info(f"Skipping LLM backend {backend.__class__.__name__}: no API key configured")
                continue
            call_start = time.monotonic()
            try:
                logger.info(f"Trying LLM backend: {backend.__class__.__name__}")
                # One real, fast retry for a genuinely transient failure
                # (timeout/connection reset) before conceding this backend --
                # never for a credit/auth/quota error, which won't succeed on
                # retry and (for quota specifically) is strictly better
                # served by immediately trying the NEXT backend in the chain
                # than waiting out this one's own suggested retry delay.
                # Still bounded by the same overall BACKEND_TIMEOUT_S.
                result = await asyncio.wait_for(
                    retry_async(
                        lambda: backend.generate(prompt, max_tokens=max_tokens, temperature=temperature),
                        max_attempts=2,
                        base_delay_s=0.4,
                        should_retry=is_transient_llm_error,
                    ),
                    timeout=self.BACKEND_TIMEOUT_S,
                )
                logger.info(f"LLM backend {backend.__class__.__name__} succeeded")
                # Backends that can extract real provider-reported usage from
                # their own raw API response stash it on self._last_usage
                # (see e.g. AnthropicLLM/GroqLLM.generate) -- picked up here
                # so real exact tokens/prompt-decode timing flow into the
                # SAME analytics record as the estimate fallback, with no
                # double-counting.
                real_usage = getattr(backend, "_last_usage", None) or {}
                usage_analytics.record_call(
                    backend.__class__.__name__, time.monotonic() - call_start, prompt, result, True,
                    prompt_tokens=real_usage.get("prompt_tokens"),
                    completion_tokens=real_usage.get("completion_tokens"),
                    prompt_time_s=real_usage.get("prompt_time_s"),
                    decode_time_s=real_usage.get("decode_time_s"),
                )
                return result
            except asyncio.TimeoutError:
                logger.warning(
                    f"LLM backend {backend.__class__.__name__} timed out after {self.BACKEND_TIMEOUT_S}s"
                )
                usage_analytics.record_call(
                    backend.__class__.__name__, time.monotonic() - call_start, prompt, "", False,
                    error=f"timed out after {self.BACKEND_TIMEOUT_S}s",
                )
                last_exception = TimeoutError(f"{backend.__class__.__name__} timed out")
                continue
            except Exception as e:
                logger.warning(f"LLM backend {backend.__class__.__name__} failed: {e}")
                usage_analytics.record_call(
                    backend.__class__.__name__, time.monotonic() - call_start, prompt, "", False, error=str(e),
                )
                last_exception = e
                continue
        # If all backends failed, raise the last exception
        logger.error("All LLM backends failed")
        raise last_exception

# Real, declarative catalog of cloud LLM providers -- single source of truth
# for get_llm_backends()'s PHASE 1 below AND for main_new.py's /config/keys
# catalog endpoint (the Keys page's credential list). Adding a new provider
# here is the *only* place it needs to be added: it's simultaneously wired
# into the live fallback chain and automatically offered as a configurable
# credential in the UI, with real live status -- no separate list to keep in
# sync by hand.
LLM_PROVIDER_CATALOG: list[tuple[str, str, type, str]] = [
    ("ANTHROPIC_API_KEY", "Anthropic (Claude)", AnthropicLLM, "primary backend (best quality)"),
    ("GROQ_API_KEY", "Groq", GroqLLM, "fast cloud backend"),
    ("OPENAI_API_KEY", "OpenAI", OpenAILLM, "general-purpose cloud backend"),
    ("GEMINI_API_KEY", "Gemini", GeminiLLM, "multimodal cloud backend"),
    ("OPENROUTER_API_KEY", "OpenRouter", OpenRouterLLM, "aggregator backend"),
    ("OPENCODE_API_KEY", "OpenCode Zen", OpenCodeLLM, "coding-focused cloud backend"),
    ("CLAWROUTER_API_KEY", "ClawRouter", ClawRouterLLM, "managed multi-provider backend"),
]


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

    # ---- PHASE 1: Cloud (best quality first, in LLM_PROVIDER_CATALOG order) ----
    for env_var, _label, backend_cls, role in LLM_PROVIDER_CATALOG:
        if os.getenv(env_var):
            logger.info(f"Adding {backend_cls.__name__} as {role}")
            backends.append(backend_cls())

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

    # Real local GGUF inference via llama.cpp -- offline, no API cost.
    # LLM_MODEL_PATH may list more than one real .gguf file, comma-separated
    # -- each real (existing) one becomes its own LlamaCppLLM in the chain,
    # in the order listed, so e.g. a coding-specialized primary model can
    # have a smaller/faster one as a real fallback if the first fails to
    # load or generate. Any entry that isn't a real file is skipped rather
    # than raising, same graceful-degrade convention as every other
    # optional backend here.
    for raw_path in os.getenv("LLM_MODEL_PATH", "").split(","):
        llama_cpp_model_path = raw_path.strip()
        if llama_cpp_model_path and os.path.isfile(llama_cpp_model_path):
            logger.info("Adding LlamaCppLLM as local GGUF backend (%s)", llama_cpp_model_path)
            backends.append(LlamaCppLLM(llama_cpp_model_path))

    # Real self-hosted vLLM server (GPU-backed, high-throughput) -- explicit
    # opt-in only (VLLM_BASE_URL must be set), unlike Ollama's always-probed
    # default, since a vLLM server is a deliberate GPU setup this backend
    # never starts on its own.
    if os.getenv("VLLM_BASE_URL"):
        logger.info("Adding VLLMLLM as self-hosted GPU backend")
        backends.append(VLLMLLM())

    # ---- PHASE 4: Legacy configured providers (if LLM_BACKENDS env var set) ----
    backends_env = os.getenv("LLM_BACKENDS", "")
    backend_names = [name.strip().lower() for name in backends_env.split(",") if name.strip()]

    for name in backend_names:
        if name == "dummy":
            backends.append(DummyLLM())
        elif name == "llama_cpp":
            # Already added automatically above if LLM_MODEL_PATH is real -- avoid a duplicate.
            if not any(isinstance(b, LlamaCppLLM) for b in backends):
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
        if coding_model in _get_ollama_models_sync(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")):
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