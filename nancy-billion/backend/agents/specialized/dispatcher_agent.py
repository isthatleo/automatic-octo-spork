"""
Dispatcher Agent for Nancy/Billion Backend

Real sub-agent orchestration: given a goal, asks the LLM which of the
*actual currently-registered* agents are relevant, genuinely runs each one
through agent_service.run() (real execution, not simulated), then asks the
LLM to synthesize the real results into one answer. Every step does real
work -- there is no pre-baked "team" of fake sub-agents; the roster it
routes against is whatever agent_service actually has online right now.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)

ROUTE_TIMEOUT_S = 20.0
SUBAGENT_TIMEOUT_S = 45.0
SYNTHESIS_TIMEOUT_S = 25.0
MAX_SUBAGENTS = 3

_ROUTE_PROMPT = """You are routing a task to specialist agents. Here is the real, currently online roster (key: domain -- specializations):
{roster}

Task: {goal}

Pick between 1 and {max_agents} agent keys from the roster above that are genuinely relevant to this task. For each, give a short task_type (a single word or hyphenated phrase describing what to ask it) and any payload fields it might need.

Respond with ONLY a JSON array (no prose, no markdown fences) in exactly this shape:
[{{"agent_key": "research", "task_type": "query", "payload": {{"query": "..."}}}}]

Only use agent_key values that appear in the roster above -- do not invent new ones.
"""

_SYNTHESIS_PROMPT = """A task was split across specialist agents. Combine their real results into one clear, coherent answer for the user.

Original task: {goal}

Agent results:
{results}

Write a concise synthesis (a few sentences to a short paragraph). Do not repeat the raw JSON -- summarize what was actually found/done.
"""


def _extract_json(text: str):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        arr = re.search(r"\[.*\]", text, re.DOTALL)
        obj = re.search(r"\{.*\}", text, re.DOTALL)
        if arr:
            text = arr.group(0)
        elif obj:
            text = obj.group(0)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


class DispatcherAgent(SpecializedAgent):
    """Real multi-agent task orchestrator -- routes to and runs actual
    registered agents, then synthesizes their real outputs."""

    def __init__(self, settings):
        super().__init__(settings, "Dispatcher Agent", "dispatcher")
        self.capabilities.update({
            "description": "Routes a goal across the real agent fleet and synthesizes their genuine outputs",
            "confidence": 0.85,
            "specializations": [
                "task-decomposition",
                "multi-agent-routing",
                "result-synthesis",
            ],
            "tools": ["llm-chain", "agent-fleet"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "dispatch")
        if task_type in ("dispatch", "query"):
            return await self._dispatch(task_data)
        return {"success": False, "error": f"Unknown task type '{task_type}' for dispatcher agent"}

    async def _dispatch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        goal = params.get("goal") or params.get("query") or ""
        if not goal.strip():
            return {"success": False, "error": "A 'goal' (or 'query') is required to dispatch"}

        # Deferred imports -- avoids any import-order coupling with the
        # registry that constructs this very agent, and with the top-level
        # llm module (same pattern as planning_agent.py).
        from llm import llm_backend
        from agents.agent_service import agent_service

        if not agent_service.is_ready():
            return {"success": False, "error": "Agent fleet is not ready yet"}

        roster = [
            a for a in agent_service.list_agents()
            if a.get("key") != self.domain and a.get("status") != "offline"
        ]
        if not roster:
            return {"success": False, "error": "No other online agents to dispatch to"}
        roster_text = "\n".join(
            f"- {a['key']}: {a.get('domain', a['key'])} -- {', '.join(a.get('specializations', [])[:5]) or 'general'}"
            for a in roster
        )

        route_prompt = _ROUTE_PROMPT.format(roster=roster_text, goal=goal, max_agents=MAX_SUBAGENTS)
        try:
            raw_route = await asyncio.wait_for(
                llm_backend.generate(route_prompt, max_tokens=400, temperature=0.2),
                timeout=ROUTE_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Routing LLM call exceeded {ROUTE_TIMEOUT_S:.0f}s"}
        except Exception as e:
            return {"success": False, "error": f"Routing LLM call failed: {e}"}

        route_plan = _extract_json(raw_route)
        valid_keys = {a["key"] for a in roster}
        if not isinstance(route_plan, list) or not route_plan:
            return {
                "success": False,
                "error": "Routing model did not return a usable agent list",
                "raw_routing_response": raw_route,
            }

        # Only dispatch to agents that are genuinely in the live roster --
        # never invent/execute a call against a hallucinated agent_key.
        route_plan = [
            r for r in route_plan
            if isinstance(r, dict) and r.get("agent_key") in valid_keys
        ][:MAX_SUBAGENTS]
        if not route_plan:
            return {
                "success": False,
                "error": "Routing model picked no valid agents from the real roster",
                "raw_routing_response": raw_route,
            }

        async def _run_one(route: Dict[str, Any]) -> Dict[str, Any]:
            agent_key = route["agent_key"]
            task_type = route.get("task_type", "query")
            payload = route.get("payload") if isinstance(route.get("payload"), dict) else {}
            result = await agent_service.run(agent_key, {"type": task_type, **payload}, timeout=SUBAGENT_TIMEOUT_S)
            return {"agent_key": agent_key, "task_type": task_type, "result": result}

        sub_results = await asyncio.gather(*[_run_one(r) for r in route_plan], return_exceptions=True)
        clean_results = []
        for r in sub_results:
            if isinstance(r, Exception):
                clean_results.append({"agent_key": "unknown", "result": {"success": False, "error": str(r)}})
            else:
                clean_results.append(r)

        results_text = "\n\n".join(
            f"[{r['agent_key']}] {json.dumps(r['result'], default=str)[:800]}" for r in clean_results
        )
        synthesis_prompt = _SYNTHESIS_PROMPT.format(goal=goal, results=results_text)
        try:
            synthesis = await asyncio.wait_for(
                llm_backend.generate(synthesis_prompt, max_tokens=500, temperature=0.5),
                timeout=SYNTHESIS_TIMEOUT_S,
            )
        except Exception as e:
            synthesis = f"(Synthesis unavailable: {e}) See raw sub-agent results below."

        return {
            "success": True,
            "task_type": "dispatch",
            "goal": goal,
            "agents_used": [r["agent_key"] for r in clean_results],
            "synthesis": synthesis.strip(),
            "sub_results": clean_results,
        }
