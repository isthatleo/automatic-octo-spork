"""
Planning Agent for Nancy/Billion Backend

Turns a goal into a real, structured implementation plan -- genuinely LLM-
backed (uses the same llm_backend fallback chain as chat, see llm.py), not
a canned template. Every call produces a plan grounded in the actual model's
output for that specific goal; if the model is unreachable or returns
something unparseable, this says so honestly instead of inventing steps.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)

PLANNING_TIMEOUT_S = 30.0

_PLAN_PROMPT = """You are a senior software/project planning assistant. Break the following goal into a concrete, ordered implementation plan.

Goal: {goal}
Context: {context}
Constraints: {constraints}

Respond with ONLY a JSON object (no prose, no markdown fences) in exactly this shape:
{{
  "summary": "one-sentence description of the overall approach",
  "steps": [
    {{"id": 1, "title": "short title", "description": "what to do and why", "depends_on": [], "risk": "low|medium|high"}}
  ],
  "risks": ["key risk 1", "key risk 2"],
  "estimated_effort": "rough estimate, e.g. '2-3 hours' or '1-2 days'"
}}
"""


def _extract_json(text: str) -> Dict[str, Any] | None:
    """LLMs frequently wrap JSON in prose or markdown fences even when asked
    not to -- pull out the first {...} block rather than failing outright."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


class PlanningAgent(SpecializedAgent):
    """Real LLM-backed implementation planner."""

    def __init__(self, settings):
        super().__init__(settings, "Planning Agent", "planning")
        self.capabilities.update({
            "description": "Breaks goals into structured, ordered implementation plans using the real LLM chain",
            "confidence": 0.85,
            "specializations": [
                "implementation-planning",
                "task-decomposition",
                "risk-assessment",
                "effort-estimation",
            ],
            "tools": ["llm-chain"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "create-plan")
        if task_type in ("create-plan", "query"):
            return await self._create_plan(task_data)
        return {"success": False, "error": f"Unknown task type '{task_type}' for planning agent"}

    async def _create_plan(self, params: Dict[str, Any]) -> Dict[str, Any]:
        goal = params.get("goal") or params.get("query") or ""
        if not goal.strip():
            return {"success": False, "error": "A 'goal' (or 'query') is required to plan against"}
        context = params.get("context", "none provided")
        constraints = params.get("constraints", "none provided")

        # Deferred import -- llm.py is a top-level module, not part of the
        # agents package, and importing it lazily here avoids any import-
        # order coupling between the agent registry and the LLM chain.
        from llm import llm_backend

        prompt = _PLAN_PROMPT.format(goal=goal, context=context, constraints=constraints)
        try:
            raw = await asyncio.wait_for(
                llm_backend.generate(prompt, max_tokens=900, temperature=0.4),
                timeout=PLANNING_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Planning LLM call exceeded {PLANNING_TIMEOUT_S:.0f}s"}
        except Exception as e:
            return {"success": False, "error": f"Planning LLM call failed: {e}"}

        parsed = _extract_json(raw)
        if parsed is None or "steps" not in parsed:
            # Honest degrade: surface the real model output rather than
            # inventing a fake structured plan around it.
            return {
                "success": True,
                "task_type": "create-plan",
                "goal": goal,
                "structured": False,
                "note": "Model did not return parseable JSON; showing its raw response instead of fabricating structure.",
                "raw_response": raw,
            }

        steps: List[Dict[str, Any]] = parsed.get("steps", [])
        return {
            "success": True,
            "task_type": "create-plan",
            "goal": goal,
            "structured": True,
            "summary": parsed.get("summary", ""),
            "steps": steps,
            "step_count": len(steps),
            "risks": parsed.get("risks", []),
            "estimated_effort": parsed.get("estimated_effort", "unknown"),
        }
