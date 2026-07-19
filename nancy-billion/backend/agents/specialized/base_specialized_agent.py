"""
Base Specialized Agent for Nancy/Billion
Provides the foundation for all 29+ specialized Python agents.
Fixes: _process_queue task_data bug, missing initialize()/process_query()/shutdown().
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import abstractmethod
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional

from ..base import BaseAgent

logger = logging.getLogger(__name__)


class SpecializedAgent(BaseAgent):
    """
    Base class for all specialized agents in the Nancy/Billion system.

    Subclasses must implement:
        process_task(task_data: Dict) -> Dict

    All other lifecycle methods have sensible defaults.
    """

    def __init__(self, settings, agent_name: str, domain: str):
        super().__init__(settings)
        self.agent_name   = agent_name
        self.domain       = domain
        self.capabilities: Dict[str, Any] = {
            "name":        agent_name,
            "domain":      domain,
            "description": f"Specialized {agent_name} agent for {domain}",
            "version":     "2.0.0",
            "confidence":  0.8,
            "specializations": [],
            "tools":       [],
        }
        self.task_queue: Deque[Dict[str, Any]] = deque()
        self.is_processing: bool = False
        self._task_history: Deque[Dict[str, Any]] = deque(maxlen=200)
        self._total_tasks:  int  = 0
        self._failed_tasks: int  = 0
        self._started_at:   float = time.time()

    # ------------------------------------------------------------------
    # BaseAgent abstract method implementations
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Initialise the agent -- marks it as ready."""
        self._initialized = True
        self.logger.info("Agent '%s' initialised (domain=%s)", self.agent_name, self.domain)

    async def process_query(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Natural-language query interface required by BaseAgent.
        Wraps the query as a generic 'query' task and delegates to process_task().
        """
        task_data: Dict[str, Any] = {
            "type":    "query",
            "query":   query,
            "context": context or {},
        }
        try:
            result = await self.process_task(task_data)
            return {
                "response":   str(result.get("result") or result.get("response") or result),
                "agents_used": [self.agent_name],
                "confidence":  self.capabilities.get("confidence", 0.8),
                "raw":         result,
            }
        except Exception as exc:
            self.logger.error("process_query error in %s: %s", self.agent_name, exc)
            return {
                "response":   f"Agent {self.agent_name} encountered an error: {exc}",
                "agents_used": [self.agent_name],
                "confidence":  0.0,
                "error":       str(exc),
            }

    async def _llm_answer(self, query: str, *, max_tokens: int = 500, temperature: float = 0.5) -> Optional[str]:
        """
        Real LLM-backed answer to a free-text query, scoped to this agent's
        domain. Used by subclasses' generic/fallback task handlers so an
        ad-hoc question actually gets answered instead of only returning a
        static capabilities blurb that ignores what was asked.

        Returns None (never raises) on failure so callers can fall back to
        their existing static response rather than surfacing an error for
        what should be a soft-fail enhancement.
        """
        if not query or not query.strip():
            return None
        try:
            from llm import llm_backend  # deferred: avoid import-order coupling with the registry
            system = (
                f"You are {self.agent_name}, a specialist in {self.domain.replace('-', ' ')}. "
                f"{self.capabilities.get('description', '')} "
                "Answer the user's specific question or request directly and concretely, "
                "drawing on your domain expertise. Do not just list your capabilities."
            )
            prompt = f"{system}\n\nUser: {query}\n\nResponse:"
            return await asyncio.wait_for(
                llm_backend.generate(prompt, max_tokens=max_tokens, temperature=temperature),
                timeout=20.0,
            )
        except Exception as exc:
            self.logger.warning("_llm_answer failed for %s: %s", self.agent_name, exc)
            return None

    async def shutdown(self) -> None:
        """Graceful shutdown -- drains the task queue."""
        self.logger.info("Shutting down agent '%s' (%d tasks in queue)...",
                         self.agent_name, len(self.task_queue))
        self.task_queue.clear()
        self._running = False
        self.logger.info("Agent '%s' shutdown complete.", self.agent_name)

    # ------------------------------------------------------------------
    # Task queue interface
    # ------------------------------------------------------------------

    async def add_task(self, task_data: Dict[str, Any]) -> str:
        """Enqueue a task and return its task_id."""
        task_id = f"{self.agent_name}_{uuid.uuid4().hex[:8]}"
        task = {
            "id":        task_id,
            "timestamp": time.time(),
            "data":      task_data,
            "status":    "pending",
        }
        self.task_queue.append(task)

        if not self.is_processing:
            asyncio.create_task(self._process_queue())

        return task_id

    async def run_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run a task immediately (bypasses queue) and return result."""
        start = time.time()
        self._total_tasks += 1
        try:
            result = await self.process_task(task_data)
            latency = time.time() - start
            self._task_history.append({
                "task_type": task_data.get("type", "unknown"),
                "success":   result.get("success", True),
                "latency_s": round(latency, 3),
                "timestamp": time.time(),
            })
            return result
        except Exception as exc:
            self._failed_tasks += 1
            self.logger.exception("run_task error in %s: %s", self.agent_name, exc)
            return {"success": False, "error": str(exc), "timestamp": time.time()}

    async def _process_queue(self) -> None:
        """Drain the task queue sequentially."""
        if self.is_processing:
            return

        self.is_processing = True
        try:
            while self.task_queue:
                task = self.task_queue.popleft()
                task["status"] = "running"
                start = time.time()
                self._total_tasks += 1

                try:
                    result = await self.process_task(task["data"])
                    task["status"]  = "done"
                    task["result"]  = result
                    task["latency"] = round(time.time() - start, 3)

                    # Fire optional callback
                    cb: Optional[Callable] = task["data"].get("callback")
                    if cb is not None:
                        try:
                            if asyncio.iscoroutinefunction(cb):
                                await cb(result)
                            else:
                                cb(result)
                        except Exception as cb_exc:
                            self.logger.warning("Task callback error: %s", cb_exc)

                except Exception as exc:
                    self._failed_tasks += 1
                    task["status"] = "failed"
                    task["error"]  = str(exc)
                    self.logger.error("Queue task %s failed: %s", task["id"], exc)

                self._task_history.append({
                    "id":      task["id"],
                    "status":  task["status"],
                    "latency": task.get("latency"),
                })
        finally:
            self.is_processing = False

    # ------------------------------------------------------------------
    # Abstract interface -- subclasses must implement this
    # ------------------------------------------------------------------

    @abstractmethod
    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a structured task dict.
        task_data always contains at least {"type": <str>}.
        Must return a dict with at least {"success": bool}.
        """

    # ------------------------------------------------------------------
    # Status and introspection
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Full status snapshot for the agent service and frontend."""
        uptime = round(time.time() - self._started_at, 1)
        success_rate = (
            round((self._total_tasks - self._failed_tasks) / self._total_tasks, 4)
            if self._total_tasks > 0 else 1.0
        )
        return {
            **self.capabilities,
            "status":        "online" if self._running or self._initialized else "idle",
            "queue_length":  len(self.task_queue),
            "is_processing": self.is_processing,
            "total_tasks":   self._total_tasks,
            "failed_tasks":  self._failed_tasks,
            "success_rate":  success_rate,
            "uptime_s":      uptime,
            "initialized":   self._initialized,
        }

    def get_info(self) -> Dict[str, Any]:
        """Lightweight info for the frontend agent list."""
        return {
            "key":             self.domain.replace("-", "_"),
            "name":            self.agent_name,
            "domain":          self.domain,
            "description":     self.capabilities.get("description", ""),
            "confidence":      self.capabilities.get("confidence", 0.8),
            "specializations": self.capabilities.get("specializations", []),
            "status":          "online" if self._initialized else "idle",
            "load":            min(100, len(self.task_queue) * 10 + (10 if self.is_processing else 0)),
            "total_tasks":     self._total_tasks,
            # Honesty flags (default real/production for most agents; agents
            # working with hardware that isn't connected, or that are pure
            # internal simulations, override these in their own capabilities
            # dict — see e.g. neural_interface_agent.py, multi_agent_swarm_coordinator.py).
            "mode":              self.capabilities.get("mode", "production"),
            "hardware_connected": self.capabilities.get("hardware_connected"),
        }
