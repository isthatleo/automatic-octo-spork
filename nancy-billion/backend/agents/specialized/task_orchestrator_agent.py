"""
Task Orchestrator Agent for Nancy/Billion.

Distinct from DispatcherAgent (which reactively routes ONE incoming user
query to 1-3 relevant agents and synthesizes their answers): this agent is
the PROACTIVE, self-directed half of "always something to do" -- it
generates its OWN batch of concrete task assignments across the agent
roster and dispatches them, rather than waiting for a query to route.

This is the real engine behind main_new.py's proactive-agent scheduling:
called periodically, it looks at the real, currently-registered agent
roster, asks a local LLM (no cloud-API cost/rate-limit competition with
real user chat -- see main_new.py's _proactive_local_llm) to propose a
handful of concrete, genuinely useful tasks naming real agent keys, then
actually runs them concurrently via agent_service.run() and reports what
each one really found. A hallucinated/invalid agent key is dropped rather
than silently guessed at.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)

MAX_TASKS_PER_BATCH = 12


class TaskOrchestratorAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Task Orchestrator Agent", "task-orchestration")
        self.capabilities.update({
            "description": "Proactively generates concrete tasks and delegates them across the real agent roster, concurrently",
            "confidence": 0.8,
            "specializations": ["task-generation", "multi-agent-delegation", "batch-orchestration"],
            "tools": ["agent_service.run"],
        })
        self._last_batch: Dict[str, Any] = {}

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "generate_and_delegate":
            return await self._generate_and_delegate(int(task_data.get("max_tasks", MAX_TASKS_PER_BATCH)))
        if task_type == "delegate":
            # Direct delegation with an explicit, already-decided task list --
            # skips the LLM task-generation step for a caller that already
            # knows exactly what it wants run (e.g. a user-triggered batch).
            return await self._delegate(task_data.get("tasks", []))
        if task_type == "status":
            return {"success": True, "last_batch": self._last_batch or None}
        return await self._general(task_data)

    async def _generate_and_delegate(self, max_tasks: int) -> Dict[str, Any]:
        from agents.agent_service import agent_service

        real_agents = [
            a for a in agent_service.list_agents()
            if a.get("key") not in ("task_orchestration", "dispatcher", "planning")
        ]
        if not real_agents:
            return {"success": False, "error": "No agents available to delegate to yet"}

        # Least-used agents first, not registration order -- confirmed live
        # as the actual cause of "almost all agents show 0 completed tasks":
        # with no ordering signal, the model kept proposing the same handful
        # of "obviously useful" agents every cycle, so the other ~60 never
        # got picked even after many real cycles. Sorting by total_tasks
        # ascending and saying so explicitly in the prompt biases genuinely
        # idle agents to the front of what the model sees, so the fleet
        # actually rotates through everyone over time instead of a fixed set.
        real_agents.sort(key=lambda a: a.get("total_tasks", 0))
        roster_block = "\n".join(
            f"- {a['key']}: {a.get('description', a.get('domain', ''))} "
            f"(completed {a.get('total_tasks', 0)} tasks so far)"
            for a in real_agents[:40]
        )
        prompt = (
            "You coordinate a team of specialist AI agents. Here is the real roster (key: description "
            "(tasks completed so far)), listed LEAST-USED FIRST:\n\n"
            f"{roster_block}\n\n"
            f"Propose up to {max_tasks} concrete, genuinely useful tasks to run right now, each assigned to "
            "ONE agent key from the list above that's actually well-suited to it. All else equal, prefer an "
            "agent with fewer completed tasks over one that's already been used many times, so the whole "
            "roster gets real, genuine use over time rather than the same few agents repeatedly -- but never "
            "force a task onto an agent it's a poor fit for just because it's idle. Prefer tasks that produce "
            "a real, checkable finding (a specific real-world fact, a real computation, a real check) over "
            "vague reflection. Respond with ONLY a JSON array, no prose, no markdown fences, in this exact "
            'shape:\n[{"agent_key": "...", "task": "..."}]'
        )

        from main_new import _proactive_local_llm
        raw = await _proactive_local_llm(prompt, max_tokens=400)
        if not raw:
            return {"success": False, "error": "Local LLM unavailable for task generation"}

        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return {"success": False, "error": f"Could not parse a task list from the model's response: {raw[:200]}"}
        try:
            proposed = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError) as e:
            return {"success": False, "error": f"Invalid JSON task list: {e}"}

        valid_keys = {a["key"] for a in real_agents}
        tasks = [
            t for t in proposed
            if isinstance(t, dict) and t.get("agent_key") in valid_keys and t.get("task")
        ][:max_tasks]
        if not tasks:
            return {"success": False, "error": "Model proposed no valid (real agent_key, task) pairs"}

        return await self._delegate(tasks)

    async def _delegate(self, tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        from agents.agent_service import agent_service

        valid_keys = set(agent_service._agents.keys())
        tasks = [t for t in tasks if isinstance(t, dict) and t.get("agent_key") in valid_keys and t.get("task")]
        if not tasks:
            return {"success": False, "error": "No valid tasks (each needs a real agent_key and a task string)"}

        async def _run_one(t: Dict[str, Any]) -> Dict[str, Any]:
            try:
                result = await agent_service.run(
                    t["agent_key"], {"type": "query", "query": t["task"]}, timeout=120.0,
                )
                return {
                    "agent_key": t["agent_key"], "task": t["task"], "success": bool(result.get("success", True)),
                    "result": str(result.get("response") or result.get("result") or result)[:600],
                }
            except Exception as e:
                return {"agent_key": t["agent_key"], "task": t["task"], "success": False, "result": str(e)}

        results = await asyncio.gather(*(_run_one(t) for t in tasks))
        self._last_batch = {"ran_at": time.time(), "results": results}
        return {"success": True, "tasks_run": len(results), "results": results}

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I proactively generate real tasks and delegate them across the actual agent roster, concurrently -- "
            "ask me to 'generate_and_delegate', or give me an explicit task list to 'delegate'."
        )}
