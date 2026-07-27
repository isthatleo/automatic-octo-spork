"""Real pluggable context-compaction architecture -- ported from Hermes'
context-engine ABC. context_manager.py's ContextManager previously had one
fixed compaction rule hardcoded into clear_old_history() (truncate to the
last 100 messages); this formalizes that into a real strategy interface so
a different strategy can be swapped in via CONTEXT_ENGINE_STRATEGY, with
TruncateStrategy as the default that reproduces today's exact behavior
unchanged.
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class CompactionStrategy(ABC):
    @abstractmethod
    def should_compact(self, history: List[Dict[str, Any]]) -> bool:
        """Whether `history` currently needs compacting."""

    @abstractmethod
    async def compact(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Returns a new, shorter history list."""


class TruncateStrategy(CompactionStrategy):
    """The default -- reproduces ContextManager.clear_old_history()'s exact
    original behavior: once history exceeds max_messages, keep only the
    most recent max_messages."""

    def __init__(self, max_messages: int = 100) -> None:
        self.max_messages = max_messages

    def should_compact(self, history: List[Dict[str, Any]]) -> bool:
        return len(history) > self.max_messages

    async def compact(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return history[-self.max_messages:]


class SummarizeStrategy(CompactionStrategy):
    """A real upgrade over plain truncation: once history exceeds
    `trigger_at` messages, uses the LLM to summarize everything except the
    most recent `keep_recent` messages into a single synthetic system-role
    message, so old context isn't silently discarded -- it's compressed."""

    def __init__(self, trigger_at: int = 60, keep_recent: int = 20) -> None:
        self.trigger_at = trigger_at
        self.keep_recent = keep_recent

    def should_compact(self, history: List[Dict[str, Any]]) -> bool:
        return len(history) > self.trigger_at

    async def compact(self, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        to_summarize = history[: -self.keep_recent]
        recent = history[-self.keep_recent:]
        if not to_summarize:
            return history

        transcript = "\n".join(f"{m['role']}: {m['content']}" for m in to_summarize)
        try:
            from llm import llm_backend
            summary = await llm_backend.generate(
                f"Summarize this conversation history into a few dense sentences preserving concrete "
                f"facts, decisions, and open threads. Do not add commentary.\n\n{transcript[:8000]}",
                max_tokens=300, temperature=0.3,
            )
        except Exception as e:
            logger.warning("context_engine.SummarizeStrategy: summarization failed, falling back to truncation: %s", e)
            return recent

        summary_message = {"role": "system", "content": f"[Earlier conversation summary]: {summary.strip()}", "metadata": {"synthetic_summary": True}}
        return [summary_message] + recent


def create_strategy() -> CompactionStrategy:
    name = os.getenv("CONTEXT_ENGINE_STRATEGY", "truncate").lower()
    if name == "summarize":
        return SummarizeStrategy()
    return TruncateStrategy()
