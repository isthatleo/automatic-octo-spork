"""
General-purpose LLM-backed utility agents for Nancy/Billion Backend

Three real, distinct agents, each a genuine call through the same real LLM
fallback chain used by chat (llm.py's llm_backend) with a different system
prompt/scope -- not scripted responses:

- GeneralPurposeAgent ("general_purpose"): open-ended tasks with no fixed
  domain -- writing, brainstorming, multi-step reasoning, anything that
  doesn't fit a specialist agent.
- ClaudeAgent ("claude"): the plain conversational catch-all -- a direct,
  low-latency Q&A/writing responder, deliberately simpler than
  general_purpose (no attempt at multi-step planning).
- ClaudeCodeGuideAgent ("claude_code_guide"): answers scoped specifically
  to Claude Code, the Claude Agent SDK, and the Claude API -- genuinely
  real, since the underlying model actually has this knowledge; the system
  prompt just focuses it and asks it to say so when it's unsure rather than
  guessing at version-specific details.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)

LLM_TIMEOUT_S = 30.0


async def _call_llm(system_prompt: str, user_text: str, *, max_tokens: int, temperature: float) -> str:
    # Deferred import -- llm.py is a top-level module, not part of the
    # agents package; importing it lazily avoids any import-order coupling
    # with the agent registry that constructs these agents.
    from llm import llm_backend

    prompt = f"{system_prompt}\n\nUser: {user_text}\n\nResponse:"
    return await asyncio.wait_for(
        llm_backend.generate(prompt, max_tokens=max_tokens, temperature=temperature),
        timeout=LLM_TIMEOUT_S,
    )


class GeneralPurposeAgent(SpecializedAgent):
    """Open-ended tasks with no fixed domain -- the real LLM chain with a
    broad system prompt, for anything that doesn't fit a specialist agent."""

    def __init__(self, settings):
        super().__init__(settings, "General Purpose Agent", "general-purpose")
        self.capabilities.update({
            "description": "Handles open-ended tasks that don't fit a specialist domain -- writing, brainstorming, multi-step reasoning",
            "confidence": 0.75,
            "specializations": ["open-ended-tasks", "writing", "brainstorming", "multi-step-reasoning"],
            "tools": ["llm-chain"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "task")
        if task_type not in ("task", "query"):
            return {"success": False, "error": f"Unknown task type '{task_type}' for general-purpose agent"}
        text = task_data.get("task") or task_data.get("query") or ""
        if not text.strip():
            return {"success": False, "error": "A 'task' (or 'query') is required"}
        try:
            response = await _call_llm(
                "You are a capable general-purpose assistant. Handle the following task thoroughly and "
                "practically, whatever domain it touches. If it requires multiple steps, work through them "
                "in order and show your result.",
                text, max_tokens=900, temperature=0.6,
            )
        except asyncio.TimeoutError:
            return {"success": False, "error": f"LLM call exceeded {LLM_TIMEOUT_S:.0f}s"}
        except Exception as e:
            return {"success": False, "error": f"LLM call failed: {e}"}
        return {"success": True, "task_type": "task", "task": text, "response": response.strip()}


class ClaudeAgent(SpecializedAgent):
    """Plain conversational catch-all -- direct Q&A/writing, no attempt at
    multi-step planning (that's general_purpose's job)."""

    def __init__(self, settings):
        super().__init__(settings, "Claude Agent", "claude")
        self.capabilities.update({
            "description": "Direct conversational catch-all for straightforward questions and writing requests",
            "confidence": 0.75,
            "specializations": ["conversation", "direct-qa", "writing"],
            "tools": ["llm-chain"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "query")
        if task_type != "query":
            return {"success": False, "error": f"Unknown task type '{task_type}' for claude agent"}
        text = task_data.get("query") or ""
        if not text.strip():
            return {"success": False, "error": "A 'query' is required"}
        try:
            response = await _call_llm(
                "You are a helpful, direct assistant. Answer the following question or complete the "
                "following writing request clearly and concisely.",
                text, max_tokens=600, temperature=0.7,
            )
        except asyncio.TimeoutError:
            return {"success": False, "error": f"LLM call exceeded {LLM_TIMEOUT_S:.0f}s"}
        except Exception as e:
            return {"success": False, "error": f"LLM call failed: {e}"}
        return {"success": True, "task_type": "query", "query": text, "response": response.strip()}


class ClaudeCodeGuideAgent(SpecializedAgent):
    """Answers scoped to Claude Code, the Claude Agent SDK, and the Claude
    API -- a real, focused LLM call, not a canned FAQ."""

    def __init__(self, settings):
        super().__init__(settings, "Claude Code Guide Agent", "claude-code-guide")
        self.capabilities.update({
            "description": "Answers questions about Claude Code, the Claude Agent SDK, and the Claude API",
            "confidence": 0.7,
            "specializations": ["claude-code", "claude-agent-sdk", "claude-api"],
            "tools": ["llm-chain"],
            # Honesty flag: this agent's knowledge is whatever the
            # underlying model was trained on -- it can be stale on very
            # recent releases, and says so rather than guessing.
            "mode": "knowledge-cutoff-limited",
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "query")
        if task_type != "query":
            return {"success": False, "error": f"Unknown task type '{task_type}' for claude-code-guide agent"}
        text = task_data.get("query") or ""
        if not text.strip():
            return {"success": False, "error": "A 'query' is required"}
        try:
            response = await _call_llm(
                "You answer questions specifically about Claude Code (Anthropic's CLI coding tool), the "
                "Claude Agent SDK, and the Claude API (Messages API, tool use, prompt caching, Managed "
                "Agents). If a question depends on a very recent release you may not have accurate detail "
                "on, say so explicitly rather than guessing at specifics like exact flag names or version "
                "numbers.",
                text, max_tokens=700, temperature=0.3,
            )
        except asyncio.TimeoutError:
            return {"success": False, "error": f"LLM call exceeded {LLM_TIMEOUT_S:.0f}s"}
        except Exception as e:
            return {"success": False, "error": f"LLM call failed: {e}"}
        return {"success": True, "task_type": "query", "query": text, "response": response.strip()}
