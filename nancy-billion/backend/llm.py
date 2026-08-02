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


def _anthropic_system_blocks(system, extra_instruction: str | None = None):
    """Normalize a `system` argument into Anthropic system-block form, with
    real prompt caching on the FIRST block.

    Accepts: None, a plain string, or an already-built list of
    {"type": "text", ...} blocks. The first (largest/most stable by
    convention -- callers put their static persona prompt there) block gets
    `cache_control: {"type": "ephemeral"}` so Anthropic caches the prefix
    across the many calls that share it: every round of a tool-use loop
    re-sends the identical system prompt, as does every chat turn, so
    without this the full persona+skills text is re-billed and re-processed
    every single time (higher latency AND cost -- cache reads are billed at
    a fraction of input-token price).
    """
    blocks: list = []
    if isinstance(system, str) and system.strip():
        blocks = [{"type": "text", "text": system}]
    elif isinstance(system, list):
        blocks = [dict(b) for b in system if isinstance(b, dict) and b.get("text", "").strip()]
    if blocks:
        blocks[0] = {**blocks[0], "cache_control": {"type": "ephemeral"}}
    if extra_instruction:
        blocks.append({"type": "text", "text": extra_instruction})
    return blocks or None


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

    def _auth_headers(self) -> Dict[str, str]:
        """Local Ollama needs no auth; OllamaCloudLLM overrides this with a
        real Bearer token. Kept as a method so both classes share one
        generate() implementation instead of drifting apart."""
        return {}

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
        # Accept-Encoding: identity -- confirmed live that at least Groq's
        # API can respond with brotli (Content-Encoding: br), which aiohttp
        # advertises support for whenever a brotli decoder happens to be
        # importable in this environment but then fails to actually decode
        # ("Can not decode content-encoding: br"), silently taking that
        # entire backend out of the fallback chain on every real call.
        # Requesting no compression sidesteps it without a new dependency.
        async with aiohttp.ClientSession(headers={"Accept-Encoding": "identity"}) as session:
            async with session.post(url, json=payload, headers=self._auth_headers()) as resp:
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

class OllamaCloudLLM(OllamaLLM):
    """Ollama Cloud (ollama.com) -- Ollama's hosted service running large
    open models (gpt-oss 120b, deepseek-v3.1 671b, qwen3-coder 480b, ...)
    on their datacenter GPUs, behind the exact same Ollama REST API shape
    the local daemon serves, just with a Bearer API key. Sits BETWEEN the
    other cloud providers and the local Ollama daemon in the fallback
    chain (see get_llm_backends): far higher quality than anything a
    CPU-only box can run locally, so it should be tried first -- but it
    still needs internet + quota, so local Ollama remains the true offline
    last resort behind it.

    Key: OLLAMA_CLOUD_API_KEY (falls back to OLLAMA_API_KEY -- the name
    Ollama's own tooling uses). Model: OLLAMA_CLOUD_MODEL, default
    gpt-oss:120b. Base URL override: OLLAMA_CLOUD_BASE_URL."""

    def __init__(self, model: str | None = None):
        self.api_key = os.getenv("OLLAMA_CLOUD_API_KEY") or os.getenv("OLLAMA_API_KEY")
        if not self.api_key:
            logger.warning("OLLAMA_CLOUD_API_KEY not set; Ollama Cloud LLM will not function")
        self.base_url = os.getenv("OLLAMA_CLOUD_BASE_URL", "https://ollama.com")
        self.model = model or os.getenv("OLLAMA_CLOUD_MODEL", "gpt-oss:120b")
        self._last_usage: dict | None = None
        logger.info(f"OllamaCloudLLM initialized with base_url={self.base_url}, model={self.model}")

    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        if not self.api_key:
            raise Exception("OLLAMA_CLOUD_API_KEY (or OLLAMA_API_KEY) not configured")
        return await super().generate(prompt, max_tokens=max_tokens, temperature=temperature)


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
        # Accept-Encoding: identity -- confirmed live that at least Groq's
        # API can respond with brotli (Content-Encoding: br), which aiohttp
        # advertises support for whenever a brotli decoder happens to be
        # importable in this environment but then fails to actually decode
        # ("Can not decode content-encoding: br"), silently taking that
        # entire backend out of the fallback chain on every real call.
        # Requesting no compression sidesteps it without a new dependency.
        async with aiohttp.ClientSession(headers={"Accept-Encoding": "identity"}) as session:
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
        system: str | list | None = None,
        images: list[str] | None = None,
    ) -> str:
        """`system`: real system-role prompt (cached -- see
        _anthropic_system_blocks) instead of the previous convention of
        concatenating persona text into the user message, which burned
        full input-token price on every call and gave the model a weaker
        instruction hierarchy. `images`: base64 PNG/JPEG strings for real
        vision input (e.g. a screenshot or user-shared photo) alongside the
        text prompt."""
        if not self.api_key:
            raise Exception("ANTHROPIC_API_KEY not configured")
        client = self._get_client()
        if images:
            content: list = [
                {"type": "image",
                 "source": {"type": "base64",
                            "media_type": "image/png" if not img.startswith("/9j/") else "image/jpeg",
                            "data": img}}
                for img in images
            ]
            content.append({"type": "text", "text": prompt})
        else:
            content = prompt
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}],
        }
        system_blocks = _anthropic_system_blocks(system)
        if system_blocks:
            kwargs["system"] = system_blocks
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
        system: str | list | None = None,
    ):
        """Yield text deltas as they arrive. Not part of the LLMBackend interface
        (other backends don't stream yet) — call directly when streaming is wanted.
        `system` behaves exactly as in generate() (real system role + prompt cache)."""
        if not self.api_key:
            raise Exception("ANTHROPIC_API_KEY not configured")
        client = self._get_client()
        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        system_blocks = _anthropic_system_blocks(system)
        if system_blocks:
            kwargs["system"] = system_blocks
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
        on_tool_call: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
        system: str | list | None = None,
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

        `on_tool_call`, if given, is awaited right before EACH tool actually
        runs, with (name, tool_input) -- lets the caller push a real-time
        "Nancy is reading X..." update to the UI while a multi-round tool
        loop is in flight, instead of the user staring at a blank screen for
        however long the whole loop takes (previously nothing was visible
        until the final reply, unlike Claude Code's own real-time tool-call
        visibility).

        Not part of the LLMBackend interface (other backends don't do tool
        use yet) -- call directly when tool-enabled generation is wanted, same
        pattern as generate_stream.
        """
        if not self.api_key:
            raise Exception("ANTHROPIC_API_KEY not configured")
        client = self._get_client()
        messages: List[Dict[str, Any]] = [{"role": "user", "content": prompt}]
        schema_by_name = {t["name"]: t.get("input_schema", {}) for t in tools if isinstance(t, dict) and "name" in t}

        # Caller's system prompt (persona/context) rides in the real system
        # role -- with prompt caching on its first block -- instead of being
        # concatenated into the user message. The fidelity instruction is
        # always appended as a final system block, preserving the previous
        # behavior when no caller system prompt is given.
        system_blocks = _anthropic_system_blocks(system, extra_instruction=TOOL_RESULT_FIDELITY_INSTRUCTION)

        # Cache the tools array too (cache_control on the LAST tool marks
        # the whole tools prefix cacheable) -- the tool schemas are by far
        # the most byte-identical thing re-sent on every round of the loop.
        cached_tools = list(tools)
        if cached_tools and isinstance(cached_tools[-1], dict):
            cached_tools[-1] = {**cached_tools[-1], "cache_control": {"type": "ephemeral"}}

        for _ in range(max_rounds):
            try:
                response = await client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system_blocks,
                    messages=messages,
                    tools=cached_tools,
                )
            except Exception as e:
                raise Exception(f"Anthropic error: {e}")

            if response.stop_reason != "tool_use":
                for block in response.content:
                    if block.type == "text":
                        if block.text.strip():
                            return block.text
                # No text at all: a refusal, a max_tokens stop on the first
                # round, or thinking-only output. Returning "" here counted as
                # success and stopped the fallback chain dead, so the caller
                # got silence. Fail instead, and let the next backend try.
                raise RuntimeError(
                    f"Claude returned no text (stop_reason={response.stop_reason})"
                )

            messages.append({"role": "assistant", "content": response.content})

            async def _run_tool_call(block):
                # Even through Claude's real structured tool-use API, an
                # argument can come back in the wrong JSON-schema shape (a
                # stringified number/bool/object) -- coerce toward the
                # tool's own declared schema before it ever reaches a
                # Python function with normal type hints. Never raises: an
                # uncoercible value passes through unchanged.
                tool_input = coerce_tool_input(block.input, schema_by_name.get(block.name, {}))
                if on_tool_call:
                    try:
                        await on_tool_call(block.name, tool_input)
                    except Exception as e:
                        logger.warning("on_tool_call callback failed: %s", e)
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
                return {"type": "tool_result", "tool_use_id": block.id, "content": content}

            # Real concurrent execution when Claude requests several
            # independent tool calls in one round -- matches how Claude
            # Code itself runs independent tool calls in parallel rather
            # than one at a time. gather() (not as_completed) keeps results
            # positionally aligned with tool_use_blocks even though
            # execution overlaps, so tool_use_id pairing stays correct
            # regardless of which finishes first.
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            tool_results = await asyncio.gather(*(_run_tool_call(b) for b in tool_use_blocks))
            messages.append({"role": "user", "content": list(tool_results)})

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
    on_tool_call: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None,
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

    async with aiohttp.ClientSession(headers={"Accept-Encoding": "identity"}) as session:
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
                content = message.get("content") or ""
                # `content: null` with no tool call is a routine outcome for
                # these providers (content filter, malformed tool call). It is
                # not an answer, so don't let it end the chain as if it were.
                if not content.strip():
                    raise RuntimeError(f"{provider_label} returned an empty response")
                return content

            messages.append({
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": tool_calls,
            })

            async def _run_tool_call(tc):
                fn = tc.get("function", {})
                name = fn.get("name", "")
                try:
                    raw_args = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    raw_args = {}
                tool_input = coerce_tool_input(raw_args, schema_by_name.get(name, {}))
                logger.info("%s: calling tool %s(%s)", provider_label, name, tool_input)
                if on_tool_call:
                    try:
                        await on_tool_call(name, tool_input)
                    except Exception as e:
                        logger.warning("on_tool_call callback failed: %s", e)
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
                return {"role": "tool", "tool_call_id": tc.get("id", ""), "content": json.dumps(result)}

            # Same real concurrent-execution reasoning as AnthropicLLM.generate_with_tools above.
            tool_messages = await asyncio.gather(*(_run_tool_call(tc) for tc in tool_calls))
            messages.extend(tool_messages)

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
        # Accept-Encoding: identity -- confirmed live that at least Groq's
        # API can respond with brotli (Content-Encoding: br), which aiohttp
        # advertises support for whenever a brotli decoder happens to be
        # importable in this environment but then fails to actually decode
        # ("Can not decode content-encoding: br"), silently taking that
        # entire backend out of the fallback chain on every real call.
        # Requesting no compression sidesteps it without a new dependency.
        async with aiohttp.ClientSession(headers={"Accept-Encoding": "identity"}) as session:
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
    def __init__(self, model: str | None = None):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not set; Gemini LLM will not function")
        # `model` lets get_llm_backends() register a second, real
        # free-tier-eligible instance (see GEMINI_FREE_MODEL below) alongside
        # whatever GEMINI_MODEL is configured -- the configured model is
        # commonly a Pro-tier model, which as of Google's April 2026 pricing
        # change has a real, actual zero free-tier quota (Pro is paid-only;
        # only Flash/Flash-Lite retain a working free tier). Falls back to
        # the env var exactly as before when called with no argument, so
        # every existing call site (select_llm_for_task's multimodal path,
        # etc.) is unaffected.
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-pro")
        self._last_usage: dict | None = None
        logger.info(f"GeminiLLM initialized with model={self.model}")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        import aiohttp
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        def _build_payload(with_thinking_config: bool) -> dict:
            generation_config = {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            }
            if with_thinking_config:
                # Gemini's "thinking" models (2.5+/flash-latest included) spend
                # part of maxOutputTokens on invisible internal reasoning
                # tokens unless this is set -- confirmed live: a 350-token
                # budget for a short greeting came back cut off mid-sentence
                # after ~12 visible words, because most of the budget was
                # silently consumed by thinking. 0 disables it; this codebase
                # doesn't ask Gemini to do multi-step reasoning anywhere it
                # calls .generate() directly (that's what the tool-use loop
                # is for), so there's no real work this ever needed to do.
                # NOT every configured model accepts this field though --
                # confirmed live, GEMINI_MODEL pointed at one that rejected it
                # outright with a generic 400 "invalid argument" (no
                # field-level detail), which took the entire backend out of
                # the fallback chain on every call. Rather than guess which
                # model names support it, the 400 handler below retries once
                # without it before giving up.
                generation_config["thinkingConfig"] = {"thinkingBudget": 0}
            return {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": generation_config,
            }

        # Accept-Encoding: identity -- confirmed live that at least Groq's
        # API can respond with brotli (Content-Encoding: br), which aiohttp
        # advertises support for whenever a brotli decoder happens to be
        # importable in this environment but then fails to actually decode
        # ("Can not decode content-encoding: br"), silently taking that
        # entire backend out of the fallback chain on every real call.
        # Requesting no compression sidesteps it without a new dependency.
        async with aiohttp.ClientSession(headers={"Accept-Encoding": "identity"}) as session:
            for with_thinking_config in (True, False):
                payload = _build_payload(with_thinking_config)
                async with session.post(url, json=payload) as resp:
                    if resp.status == 400 and with_thinking_config:
                        text = await resp.text()
                        logger.warning(
                            "Gemini rejected thinkingConfig for model=%s (%s); retrying without it",
                            self.model, text[:200],
                        )
                        continue
                    if resp.status == 200:
                        result = await resp.json()
                        usage = result.get("usageMetadata")
                        if usage:
                            self._last_usage = {
                                "prompt_tokens": usage.get("promptTokenCount"),
                                "completion_tokens": usage.get("candidatesTokenCount"),
                            }
                        candidates = result.get("candidates") or []
                        if not candidates:
                            raise Exception(f"Gemini returned no candidates: {result}")
                        finish_reason = candidates[0].get("finishReason", "unknown")
                        parts = candidates[0].get("content", {}).get("parts") or []
                        if not parts:
                            # A real, observed shape: finishReason == "MAX_TOKENS"
                            # with an empty parts list when the whole budget went
                            # to thinking before this fix -- surface the real
                            # reason instead of a bare KeyError.
                            raise Exception(f"Gemini returned no text (finishReason={finish_reason})")
                        if finish_reason == "MAX_TOKENS":
                            # thinkingConfig can't be disabled for every model
                            # (see the 400-retry above) and at least one --
                            # confirmed live, gemini-flash-latest resolving to
                            # gemini-3.6-flash -- reserves ~90%+ of whatever
                            # maxOutputTokens is given for invisible "thinking"
                            # regardless of prompt complexity, and that share
                            # scales UP with the budget rather than being a
                            # fixed overhead (confirmed live: raising the
                            # budget 350->1200 raised thinking tokens
                            # 335->1151, same cut-off-mid-sentence result
                            # either way). There's no token budget that
                            # reliably outruns this, so a MAX_TOKENS finish is
                            # treated as a hard failure -- letting the
                            # FallbackLLM chain move on to the next real
                            # backend -- rather than returning the genuinely
                            # truncated (garbled-sounding, mid-clause) text as
                            # if it were a complete, valid reply.
                            raise Exception(
                                f"Gemini truncated by MAX_TOKENS with {usage.get('thoughtsTokenCount', '?') if usage else '?'} "
                                f"thinking tokens consumed (model={self.model} doesn't allow disabling thinking)"
                            )
                        return parts[0].get("text", "")
                    else:
                        text = await resp.text()
                        raise Exception(f"Gemini error: {resp.status} - {text}")
        raise Exception("Gemini error: exhausted retries")

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
        # Accept-Encoding: identity -- confirmed live that at least Groq's
        # API can respond with brotli (Content-Encoding: br), which aiohttp
        # advertises support for whenever a brotli decoder happens to be
        # importable in this environment but then fails to actually decode
        # ("Can not decode content-encoding: br"), silently taking that
        # entire backend out of the fallback chain on every real call.
        # Requesting no compression sidesteps it without a new dependency.
        async with aiohttp.ClientSession(headers={"Accept-Encoding": "identity"}) as session:
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

class OmniRouteLLM(LLMBackend):
    """Local OmniRoute gateway (github.com/diegosouzapw/OmniRoute) --
    aggregates 290+ providers (90+ free, keyless) behind one OpenAI-
    compatible local endpoint with its own real circuit-breaker/cooldown
    resilience layers. Added ahead of every single-vendor cloud backend in
    get_llm_backends() specifically because a single exhausted quota
    (Gemini's real 20/day cap, Anthropic's exhausted credit balance -- both
    hit live, repeatedly, this session) used to take the whole chain down to
    slow local Ollama/llama.cpp inference, which directly competes with
    NeuTTS for the same CPU. Runs entirely on this machine
    (`npm install -g omniroute && omniroute`), no API key required for its
    default keyless "auto" combo -- has no `api_key` attribute so
    FallbackLLM's no-key skip never applies to it, same as the other local
    backends (Ollama/Fury/llama.cpp): OMNIROUTE_API_KEY (below) is a
    GATEWAY auth token, not a "this backend can't work without it" key, so
    it's deliberately named `_gateway_key` instead to keep that skip logic
    from ever applying here. If the gateway process isn't running, the
    connection simply fails fast (a genuinely transient error per
    is_transient_llm_error) and the chain falls through to the cloud
    backends below exactly as it did before this existed."""

    def __init__(self):
        self.base_url = os.getenv("OMNIROUTE_URL", "http://localhost:20128").rstrip("/")
        # "auto/best-chat" (a curated, quality-filtered combo), not bare
        # "auto" -- confirmed live that plain "auto" can round-robin onto a
        # genuinely broken free provider (repeatedly observed "felo-chat"
        # returning a single punctuation character -- "!", ".", "?" -- as
        # its entire reply, 3/3 times, for an ordinary conversational
        # prompt). "auto/best-chat" gave 3/3 real, coherent answers on the
        # same prompt in the same live test.
        self.model = os.getenv("OMNIROUTE_MODEL", "auto/best-chat")
        # Gateway-level auth (generated via the OmniRoute dashboard, protects
        # the local endpoint from anything else on the machine) -- optional:
        # the gateway works fine unauthenticated too, so an unset key here
        # just means no Authorization header is sent, not a skipped backend.
        self._gateway_key = os.getenv("OMNIROUTE_API_KEY")
        self._last_usage: dict | None = None
        logger.info(f"OmniRouteLLM initialized (url={self.base_url}, model={self.model})")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        import aiohttp
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        headers = {"Accept-Encoding": "identity"}
        if self._gateway_key:
            headers["Authorization"] = f"Bearer {self._gateway_key}"
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    usage = result.get("usage")
                    if usage:
                        self._last_usage = {
                            "prompt_tokens": usage.get("prompt_tokens"),
                            "completion_tokens": usage.get("completion_tokens"),
                        }
                    content = result["choices"][0]["message"]["content"] or ""
                    # Confirmed live: a broken free provider behind "auto"-
                    # style routing can return a "successful" 200 whose
                    # content is pure punctuation (observed "!", ".", "?"
                    # verbatim, repeatedly, from one specific provider)
                    # instead of a real answer -- not empty, so FallbackLLM's
                    # own empty-response check doesn't catch it. Rejecting
                    # content with no alphanumeric characters at all lets the
                    # chain's normal retry/next-backend logic recover instead
                    # of silently accepting one-character garbage as the
                    # reply (a real short answer like "144" or "Yes" still
                    # has alnum characters, so this doesn't false-positive on
                    # genuinely terse real answers).
                    if not any(ch.isalnum() for ch in content):
                        raise Exception(f"OmniRoute returned no substantive content: {content!r}")
                    return content
                else:
                    text = await resp.text()
                    raise Exception(f"OmniRoute error: {resp.status} - {text}")


class GroqLLM(LLMBackend):
    def __init__(self, model: str | None = None):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            logger.warning("GROQ_API_KEY not set; Groq LLM will not function")
        # `model` lets get_llm_backends() register a SECOND Groq entry on a
        # different model as a real same-vendor fallback -- Groq's rate
        # limits are per-model, so a 429 on the big model doesn't mean the
        # smaller one is unavailable. See GROQ_FALLBACK_MODEL below.
        self.model = model or os.getenv("GROQ_MODEL", "mixtral-8x7b-32768")
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
        # Accept-Encoding: identity -- confirmed live that at least Groq's
        # API can respond with brotli (Content-Encoding: br), which aiohttp
        # advertises support for whenever a brotli decoder happens to be
        # importable in this environment but then fails to actually decode
        # ("Can not decode content-encoding: br"), silently taking that
        # entire backend out of the fallback chain on every real call.
        # Requesting no compression sidesteps it without a new dependency.
        async with aiohttp.ClientSession(headers={"Accept-Encoding": "identity"}) as session:
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

    # Model-level fallback chain WITHIN OpenCode Zen: if the active model
    # fails (rate-limited, out of quota, model retired, reasoning budget
    # exhausted with no content, ...), the next one is tried in order before
    # this whole backend reports failure to FallbackLLM's provider-level
    # chain. Ids are Zen's bare kebab-case form (same convention as
    # 'big-pickle', confirmed against the live /v1/models list -- which
    # _available_models() also re-checks at runtime, so a guessed-wrong or
    # since-retired id is skipped instead of burning a doomed API call).
    # Override without a code change via OPENCODE_FALLBACK_MODELS
    # (comma-separated).
    DEFAULT_FALLBACK_MODELS = [
        "big-pickle",
        "mimo-v2.5-free",
        "nemotron-ultra-3-free",
        "hy3-free",
        "deepseek-v4-flash-free",
        "north-mini-code-free",
    ]

    def __init__(self):
        self.api_key = os.getenv("OPENCODE_API_KEY")
        if not self.api_key:
            logger.warning("OPENCODE_API_KEY not set; OpenCode Zen LLM will not function")
        self.model = os.getenv("OPENCODE_MODEL", "big-pickle")
        env_fallbacks = os.getenv("OPENCODE_FALLBACK_MODELS", "")
        self.fallback_models = (
            [m.strip() for m in env_fallbacks.split(",") if m.strip()]
            if env_fallbacks.strip()
            else list(self.DEFAULT_FALLBACK_MODELS)
        )
        self._last_usage: dict | None = None
        # Live /v1/models id set, fetched lazily on the first primary-model
        # failure and cached for the process lifetime. None = not fetched
        # yet or fetch failed (in which case candidates are tried raw --
        # an unknown id just errors and the loop moves on).
        self._live_model_ids: set[str] | None = None
        logger.info(
            f"OpenCodeLLM initialized with model={self.model}, "
            f"fallbacks={self.fallback_models}"
        )

    async def _available_models(self) -> set[str] | None:
        """Fetch (once) the live model-id list so fallback candidates that
        don't actually exist are skipped rather than tried. Best-effort:
        returns None if the endpoint can't be reached, which callers treat
        as 'no filtering'."""
        if self._live_model_ids is not None:
            return self._live_model_ids
        import aiohttp
        try:
            async with aiohttp.ClientSession(headers={"Accept-Encoding": "identity"}) as session:
                async with session.get(
                    "https://opencode.ai/zen/v1/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
            ids = {str(m.get("id", "")) for m in data.get("data", []) if m.get("id")}
            if ids:
                self._live_model_ids = ids
            return self._live_model_ids
        except Exception as e:
            logger.debug("OpenCode Zen /v1/models fetch failed (fallbacks tried unfiltered): %s", e)
            return None

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        # Primary model first, then the fallback chain (minus any duplicate
        # of the primary), each candidate tried at most once.
        candidates = [self.model] + [m for m in self.fallback_models if m != self.model]
        last_error: Exception | None = None
        for i, model in enumerate(candidates):
            if i > 0:
                # First failure just happened -- lazily check the live model
                # list so retired/mistyped fallback ids get skipped.
                live = await self._available_models()
                if live is not None and model not in live:
                    logger.info("OpenCode Zen fallback '%s' not in live model list, skipping", model)
                    continue
            try:
                return await self._generate_once(model, prompt, max_tokens, temperature)
            except Exception as e:
                last_error = e
                logger.warning("OpenCode Zen model '%s' failed (%s)%s", model, e,
                               " -- trying next fallback model" if i < len(candidates) - 1 else "")
        raise Exception(f"OpenCode Zen: all models failed ({len(candidates)} tried). Last error: {last_error}")

    async def _generate_once(self, model: str, prompt: str, max_tokens: int, temperature: float) -> str:
        import aiohttp
        url = "https://opencode.ai/zen/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        # Accept-Encoding: identity -- confirmed live that at least Groq's
        # API can respond with brotli (Content-Encoding: br), which aiohttp
        # advertises support for whenever a brotli decoder happens to be
        # importable in this environment but then fails to actually decode
        # ("Can not decode content-encoding: br"), silently taking that
        # entire backend out of the fallback chain on every real call.
        # Requesting no compression sidesteps it without a new dependency.
        async with aiohttp.ClientSession(headers={"Accept-Encoding": "identity"}) as session:
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
        # Accept-Encoding: identity -- confirmed live that at least Groq's
        # API can respond with brotli (Content-Encoding: br), which aiohttp
        # advertises support for whenever a brotli decoder happens to be
        # importable in this environment but then fails to actually decode
        # ("Can not decode content-encoding: br"), silently taking that
        # entire backend out of the fallback chain on every real call.
        # Requesting no compression sidesteps it without a new dependency.
        async with aiohttp.ClientSession(headers={"Accept-Encoding": "identity"}) as session:
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
        # Accept-Encoding: identity -- confirmed live that at least Groq's
        # API can respond with brotli (Content-Encoding: br), which aiohttp
        # advertises support for whenever a brotli decoder happens to be
        # importable in this environment but then fails to actually decode
        # ("Can not decode content-encoding: br"), silently taking that
        # entire backend out of the fallback chain on every real call.
        # Requesting no compression sidesteps it without a new dependency.
        async with aiohttp.ClientSession(headers={"Accept-Encoding": "identity"}) as session:
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
    # Once a backend fails with a non-transient error (quota/credit/auth --
    # see is_transient_llm_error), skip it for this long instead of paying
    # its real network round-trip cost again on every single subsequent
    # message. Confirmed live: Gemini's free tier hit a hard "20 requests
    # per DAY" quota and Anthropic's credit balance was exhausted, and both
    # failures are only ever going to repeat identically until something
    # external changes (quota reset tomorrow, credits purchased) -- without
    # this, every message pays ~2 guaranteed-dead real HTTP round trips
    # before ever reaching a backend that works, which measured live as
    # several extra seconds added to every single reply.
    NON_TRANSIENT_COOLDOWN_S = 300.0

    def __init__(self, backends):
        self.backends = backends
        self._cooldown_until: Dict[str, float] = {}
        logger.info(f"FallbackLLM initialized with {len(self.backends)} backends")

    async def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
        last_exception = None
        for backend in self.backends:
            # Cooldown/skip key includes the MODEL, not just the class.
            # Two instances of the same backend class on different models are
            # now genuinely independent (see GROQ_FALLBACK_MODEL in
            # get_llm_backends): Groq rate-limits per model, so a 429 on
            # llama-3.3-70b says nothing about llama-3.1-8b. Keying the
            # cooldown by class name alone made the 70b failure suppress its
            # own healthy 8b sibling for the full 5-minute window, which
            # defeated the entire point of having a same-vendor fallback.
            name = f"{backend.__class__.__name__}:{getattr(backend, 'model', '')}"
            # Cloud backends set self.api_key from an env var and always fail
            # the same way when it's missing -- skip immediately instead of
            # burning up to BACKEND_TIMEOUT_S waiting on a call that can never
            # succeed. Local/no-key backends (Ollama, Fury, llama.cpp, Dummy)
            # have no api_key attribute at all, so they're never skipped here.
            if hasattr(backend, "api_key") and not backend.api_key:
                logger.info(f"Skipping LLM backend {name}: no API key configured")
                continue
            cooldown_until = self._cooldown_until.get(name)
            if cooldown_until and time.monotonic() < cooldown_until:
                logger.info(
                    f"Skipping LLM backend {name}: in cooldown for another "
                    f"{cooldown_until - time.monotonic():.0f}s (last failure was quota/credit/auth, not transient)"
                )
                continue
            call_start = time.monotonic()
            try:
                logger.info(f"Trying LLM backend: {name}")
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
                # A provider can return HTTP 200 with nothing in it -- a
                # content filter, a refusal, a malformed tool call, or
                # `content: null`, which several OpenAI-compatible providers
                # emit routinely. That used to count as success, so the chain
                # stopped dead on it and the empty string travelled all the
                # way to the user: no reply at all on Telegram, a raw JSON
                # blob in the CLI. Treat it as this backend failing so the
                # next one actually gets a turn.
                if not (result or "").strip():
                    raise RuntimeError(f"{backend.__class__.__name__} returned an empty response")
                logger.info(f"LLM backend {backend.__class__.__name__} succeeded")
                self._cooldown_until.pop(name, None)  # clear any stale cooldown now that it's working again
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
                if not is_transient_llm_error(e):
                    self._cooldown_until[name] = time.monotonic() + self.NON_TRANSIENT_COOLDOWN_S
                last_exception = e
                continue
        # If all backends failed, raise the last exception. `last_exception`
        # is still None when every backend was skipped by the no-key guard
        # above -- raising that gave the user "exceptions must derive from
        # BaseException" instead of anything about LLMs.
        logger.error("All LLM backends failed")
        raise last_exception or RuntimeError(
            "No LLM backend was usable -- none is configured with a working key."
        )

# Real, declarative catalog of cloud LLM providers -- single source of truth
# for get_llm_backends()'s PHASE 1 below AND for main_new.py's /config/keys
# catalog endpoint (the Keys page's credential list). Adding a new provider
# here is the *only* place it needs to be added: it's simultaneously wired
# into the live fallback chain and automatically offered as a configurable
# credential in the UI, with real live status -- no separate list to keep in
# sync by hand.
LLM_PROVIDER_CATALOG: list[tuple[str, str, type, str]] = [
    # Groq ahead of Anthropic: confirmed live this session that Anthropic's
    # credit balance is exhausted (guaranteed 400 on every call) while Groq
    # has worked reliably throughout. This tier is now only reached when
    # OmniRoute (Phase 0, above everything here) is itself unavailable, so
    # the cost of the old order was small, but non-zero -- a guaranteed-fail
    # attempt before ever reaching a backend that works. Move Anthropic back
    # above Groq once real credits exist again, if its quality edge is worth
    # it for this rarely-reached tier.
    ("GROQ_API_KEY", "Groq", GroqLLM, "fast cloud backend"),
    ("ANTHROPIC_API_KEY", "Anthropic (Claude)", AnthropicLLM, "primary backend (best quality)"),
    ("OPENAI_API_KEY", "OpenAI", OpenAILLM, "general-purpose cloud backend"),
    ("GEMINI_API_KEY", "Gemini", GeminiLLM, "multimodal cloud backend"),
    ("OPENROUTER_API_KEY", "OpenRouter", OpenRouterLLM, "aggregator backend"),
    ("OPENCODE_API_KEY", "OpenCode Zen", OpenCodeLLM, "coding-focused cloud backend"),
    ("CLAWROUTER_API_KEY", "ClawRouter", ClawRouterLLM, "managed multi-provider backend"),
    # Last of the cloud tier, but deliberately still IN the cloud tier: a
    # datacenter-hosted 120B+ open model beats anything a CPU-only box can
    # run locally, so Ollama Cloud must be tried before the local Ollama
    # daemon (Phase 2 below), which stays as the true offline last resort.
    ("OLLAMA_CLOUD_API_KEY", "Ollama Cloud", OllamaCloudLLM, "hosted open-model backend"),
]


# Factory to create a list of backends from the environment variable LLM_BACKENDS
def get_llm_backends():
    """Build backend chain in priority order.

    Default chain (quality-first; local Ollama is the offline fallback, not primary):
    0) OmniRoute: local free 290+-provider gateway with its own real
       fallback/circuit-breaking (unless DISABLE_OMNIROUTE=1)
    1) Groq: Fast cloud inference (if GROQ_API_KEY set) -- ahead of Anthropic
       while its credit balance is exhausted (see LLM_PROVIDER_CATALOG)
    2) Anthropic: Claude for complex/coding tasks (if ANTHROPIC_API_KEY set)
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

    # ---- PHASE 0: OmniRoute (local free multi-provider gateway) ----
    # Tried before every single-vendor cloud backend below: it already does
    # its own internal fallback across 290+ providers (90+ free, keyless)
    # with real circuit breakers, so one exhausted quota doesn't take the
    # whole chain down to slow local inference the way a single dead cloud
    # backend used to. See OmniRouteLLM's docstring for the live incidents
    # that motivated this.
    if os.getenv("DISABLE_OMNIROUTE", "0").strip() != "1":
        logger.info("Adding OmniRouteLLM as first-priority backend (local multi-provider gateway)")
        backends.append(OmniRouteLLM())

    # ---- PHASE 1: Cloud (best quality first, in LLM_PROVIDER_CATALOG order) ----
    for env_var, _label, backend_cls, role in LLM_PROVIDER_CATALOG:
        if os.getenv(env_var):
            logger.info(f"Adding {backend_cls.__name__} as {role}")
            backends.append(backend_cls())
            # Real free-tier fallback for Gemini specifically: GEMINI_MODEL
            # is very commonly a Pro-tier model (e.g. the "-latest" alias
            # resolves to one), and Pro tiers have had a genuine zero free
            # quota since Google's April 2026 pricing change -- confirmed
            # live via this exact deployment's own logs ("Quota exceeded...
            # limit: 0, model: gemini-3.1-pro"). GEMINI_FREE_MODEL defaults
            # to the "-latest" Flash alias, which (unlike Pro) keeps a real
            # working free-tier quota, so a 429/400 on the configured model
            # above has an actual working fallback instead of just failing
            # straight through to Ollama/local models. Only added when it's
            # a genuinely different model (skips a pointless duplicate call
            # if someone already points GEMINI_MODEL at a flash model).
            if backend_cls is GeminiLLM:
                free_model = os.getenv("GEMINI_FREE_MODEL", "gemini-flash-latest")
                if free_model != backends[-1].model:
                    logger.info(f"Adding GeminiLLM as free-tier fallback (model={free_model})")
                    backends.append(GeminiLLM(model=free_model))

            # Same idea for Groq, and confirmed live as a real need: Groq
            # enforces its token-per-day limit PER MODEL, and a day of heavy
            # use exhausted llama-3.3-70b-versatile ("Limit 100000, Used
            # 98817") while every other Groq model still had full quota. With
            # no same-vendor fallback, that 429 dropped the whole chain down
            # to a much slower backend and reply latency went from ~1s to
            # 3-9s. llama-3.1-8b-instant has its own separate (far larger)
            # allowance and is faster still, so it's a genuinely good
            # next-best rather than a token gesture.
            if backend_cls is GroqLLM:
                groq_fallback = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
                if groq_fallback and groq_fallback != backends[-1].model:
                    logger.info(f"Adding GroqLLM as same-vendor fallback (model={groq_fallback})")
                    backends.append(GroqLLM(model=groq_fallback))

    # Ollama Cloud via the OLLAMA_API_KEY spelling (the one Ollama's own
    # tooling uses) -- the catalog entry above only checks
    # OLLAMA_CLOUD_API_KEY, so this catches the other real way people set
    # it. Still added HERE, before the local daemon below: hosted 120B+
    # models outrank anything local, but local stays the offline fallback.
    if os.getenv("OLLAMA_API_KEY") and not any(isinstance(b, OllamaCloudLLM) for b in backends):
        logger.info("Adding OllamaCloudLLM (via OLLAMA_API_KEY) ahead of local Ollama")
        backends.append(OllamaCloudLLM())

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

    backends = apply_primary_preference(backends)

    logger.info(f"LLM backend chain initialized with {len(backends)} backends: {[b.__class__.__name__ for b in backends]}")
    return backends


def matches_backend_name(cls_name: str, want: str) -> bool:
    """Does `want` name this backend class? Accepts the full class name, its
    lowercase stem ('anthropic' for AnthropicLLM), and the stem with the
    OllamaAutoModels suffix dropped, which is how the CLI and UI refer to a
    local daemon."""
    want = (want or "").strip().lower().replace(" ", "")
    if not want:
        return False
    stem = cls_name.lower().removesuffix("llm")
    return want in (cls_name.lower(), stem) or want == stem.removesuffix("automodels")


def apply_primary_preference(backends: list) -> list:
    """Move the backend named by LLM_PRIMARY to the front of the chain.

    /llm/primary and /llm/model used to reorder the live list in memory only,
    so an explicit model choice silently reverted to the catalog's default
    (Claude first) on the next restart -- and `docker compose watch` restarts
    on any backend edit, so 'the next restart' was often minutes away. The
    choice is written to .env; this is what honours it on the way back up.
    """
    want = os.getenv("LLM_PRIMARY", "").strip()
    if not want or not backends:
        return backends
    for i, b in enumerate(backends):
        if matches_backend_name(b.__class__.__name__, want):
            if i:
                backends.insert(0, backends.pop(i))
                logger.info("LLM_PRIMARY=%s honoured; %s leads the chain", want, b.__class__.__name__)
            # Keep same-vendor siblings directly behind the primary. Without
            # this, promoting one backend strands its own alternate-model
            # fallback behind unrelated providers -- confirmed live: with
            # LLM_PRIMARY=groq the chain became [Groq-70b, OmniRoute,
            # Groq-8b, ...], so a 70b rate-limit fell through to a much
            # slower provider even though the 8b sibling (separate quota,
            # faster) was sitting right there. A vendor's own second model is
            # nearly always the best next try after its first one fails.
            primary_cls = backends[0].__class__
            insert_at = 1
            for j in range(1, len(backends)):
                if backends[j].__class__ is primary_cls:
                    if j != insert_at:
                        backends.insert(insert_at, backends.pop(j))
                        logger.info(
                            "Moved same-vendor fallback %s(model=%s) directly behind the primary",
                            primary_cls.__name__, getattr(backends[insert_at], "model", "?"),
                        )
                    insert_at += 1
            return backends
    logger.warning("LLM_PRIMARY=%s is not in the live chain (%s); leaving default order",
                   want, [b.__class__.__name__ for b in backends])
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