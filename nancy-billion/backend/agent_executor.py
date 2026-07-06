import json
import logging
import os
import asyncio
from typing import Any, Dict, Optional, Tuple

from fury import Agent

from agent_registry import load_registry, filter_tools_by_ids

logger = logging.getLogger(__name__)


def _get_registry() -> Any:
    return load_registry()


def _create_specialized_agent(agent_key: str) -> Agent:
    reg = _get_registry()
    spec = reg.get(agent_key)

    # Import here to avoid circular import at module import time.
    from tools import get_tools

    all_tools = get_tools()
    allowed_tools = filter_tools_by_ids(all_tools, spec.tool_ids)

    model_path = os.getenv("LLM_MODEL_PATH", "llamafactory/Llama-3-8B-Instruct-GGUF")
    # Keep temperature control outside; Fury agent runner uses its own params.
    return Agent(
        model=model_path,
        system_prompt=spec.system_prompt,
        tools=allowed_tools,
    )


async def run_specialized_agent(agent_key: str, input_text: str, max_tokens: int = 512, temperature: float = 0.7) -> str:
    """Instantiate a specialized agent on demand and run it for input_text."""
    # Fury's runner interface is async iterable.
    agent = _create_specialized_agent(agent_key)
    runner = agent.runner()

    history = [{"role": "user", "content": input_text}]

    buffer = ""
    # Fury runner signature may not accept max_tokens/temperature.
    # Call with the simplest supported interface.
    async for event in runner.chat(history):

        if getattr(event, "content", None):
            buffer += event.content

    if not buffer:
        raise RuntimeError(f"Specialized agent {agent_key} produced empty output")
    return buffer

