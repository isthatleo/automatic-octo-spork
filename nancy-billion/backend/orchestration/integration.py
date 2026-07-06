from __future__ import annotations

import os
from typing import Any, Optional

from .orchestrator import NancyOrchestrator
from ..llm import llm_backend
from ..agent_executor import run_specialized_agent


async def run_nancy_hierarchy(user_text: str, session_context: Optional[str] = None) -> dict[str, Any]:
    """Entry point used by backend/main.py.

    Returns a JSON-serializable dict.
    """

    orchestrator = NancyOrchestrator(
        llm_callable=llm_backend.generate,
        run_specialized_agent_callable=run_specialized_agent,
    )

    # llm_backend.generate signature: (prompt, max_tokens, temperature)
    async def llm_callable(prompt: str, max_tokens: int = 800, temperature: float = 0.4) -> str:
        return await llm_backend.generate(prompt, max_tokens=max_tokens, temperature=temperature)

    orchestrator = NancyOrchestrator(
        llm_callable=llm_callable,
        run_specialized_agent_callable=run_specialized_agent,
    )

    out = await orchestrator.orchestrate(user_request=user_text, session_context=session_context)

    return {
        "decision": out.decision,
        "final_response": out.final_response,
        "debug": out.debug,
    }

