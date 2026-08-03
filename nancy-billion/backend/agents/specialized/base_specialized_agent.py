"""
Base Specialized Agent for Nancy/Billion
Provides the foundation for all 29+ specialized Python agents.
Fixes: _process_queue task_data bug, missing initialize()/process_query()/shutdown().
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from abc import abstractmethod
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional

from ..base import BaseAgent, _current_conversation_context

logger = logging.getLogger(__name__)

# A plain domain question answers well inside 20s, but a collaboration
# revision round (see agents/collaboration.py) sends the previous answer,
# every issue raised and the reviewer's suggestion back in one prompt --
# several times longer, and it reliably blew a hardcoded 20s ceiling,
# returning nothing and reading as "the agent had no answer". Configurable
# and defaulted high enough for that real worst case.
_LLM_ANSWER_TIMEOUT_S = float(os.getenv("AGENT_LLM_TIMEOUT_S", "60"))

# Autonomous peer consultation (see _maybe_consult_expert). On by default --
# it is the behaviour that makes the fleet a society rather than a rotation
# -- but a single switch matters: every handoff is a real extra agent run,
# so a cost-sensitive or offline deployment needs to turn it off without
# editing code.
AGENT_AUTO_CONSULT = os.getenv("AGENT_AUTO_CONSULT", "1").strip().lower() in ("1", "true", "yes")


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
        self._current_task_type: Optional[str] = None
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

    async def consult(self, agent_key: str, question: str, *, timeout: float = 45.0) -> Optional[str]:
        """Ask another specialist a real question mid-task.

        The sideways edge every agent previously lacked -- see
        agents/collaboration.py. Inherited by all ~70 specialists, so an
        agent that hits a genuine gap in its own expertise can consult the
        specialist who has it instead of guessing (or worse, fabricating).

        Returns None rather than raising when the consult is refused
        (cycle, depth cap, unknown agent) or fails: a peer being
        unavailable must degrade to "answer it yourself", never break the
        task that asked.
        """
        from ..collaboration import DelegationRefused, consult as _consult

        try:
            result = await _consult(
                agent_key, question, from_agent_key=self._registry_key(), timeout=timeout,
            )
        except DelegationRefused as e:
            self.logger.info("consult refused (%s -> %s): %s", self.agent_name, agent_key, e)
            return None
        except Exception as e:
            self.logger.warning("consult failed (%s -> %s): %s", self.agent_name, agent_key, e)
            return None
        answer = str(result.get("response") or result.get("result") or "").strip()
        return answer or None

    async def _maybe_consult_expert(self, query: str) -> str:
        """Recognise a question outside this agent's expertise and consult
        the specialist who actually owns it, unprompted.

        This is the step from "can collaborate" to "does collaborate". It
        lives in _llm_answer's path deliberately: that is the one method all
        ~70 specialists inherit, so autonomous consultation arrives fleet-
        wide without editing 70 files -- and it only ever fires on the
        FREE-TEXT fallback path, never on an agent's real structured
        capabilities, which by definition already sit inside its expertise.

        Returns prompt-ready peer input, or "" to answer alone. Deliberately
        conservative -- a consult costs a real agent run, so it fires only
        when another agent is BOTH a convincing fit in absolute terms AND
        materially better than this agent (see CapabilityIndex.should_hand_off).

        Never raises: an unavailable peer must degrade to answering alone.
        """
        if not AGENT_AUTO_CONSULT:
            return ""
        try:
            from ..capability_index import capability_index
            from ..collaboration import current_chain

            # Only originate a consult at the top of a chain. Without this,
            # a consulted agent could consult onward on the same question,
            # turning one handoff into a cascade -- the depth cap would
            # eventually stop it, but only after paying for every hop.
            if current_chain():
                return ""

            me = self._registry_key()
            verdict = await capability_index.should_hand_off(me, query)
            if not verdict:
                return ""
            expert_key, expert_score, own_score = verdict
            self.logger.info(
                "auto-consult: %s (fit %.2f) deferring to %s (fit %.2f)",
                me, own_score, expert_key, expert_score,
            )
            answer = await self.consult(expert_key, query)
            if not answer:
                return ""
            return (
                f"\n\nYou consulted {expert_key}, the specialist whose domain this question "
                f"genuinely belongs to. Their input:\n{answer[:1500]}\n\n"
                "Use it where it is sound, and say plainly that you drew on their expertise. "
                "Do not contradict it without a concrete reason."
            )
        except Exception as e:
            self.logger.debug("auto-consult skipped for %s: %s", self.agent_name, e)
            return ""

    def _registry_key(self) -> str:
        """This agent's key as agent_service knows it -- needed so a consult
        can record an accurate delegation chain. Falls back to the domain,
        which is what the registry keys are derived from."""
        try:
            from ..agent_service import agent_service

            for key, agent in agent_service._agents.items():
                if agent is self:
                    return key
        except Exception:
            pass
        return self.domain.replace("-", "_")

    async def _llm_answer(self, query: str, *, max_tokens: int = 900, temperature: float = 0.5) -> Optional[str]:
        """
        Real LLM-backed answer to a free-text query, scoped to this agent's
        domain. Used by subclasses' generic/fallback task handlers so an
        ad-hoc question actually gets answered instead of only returning a
        static capabilities blurb that ignores what was asked.

        Includes real recent conversation history when main_new.py's
        keyword router (_auto_route) sent this turn here -- see
        _current_conversation_context in agents/base.py. Confirmed live:
        without this, a message that happened to match this agent's
        routing keywords got answered in total isolation from whatever the
        user had just been talking about, reading as Nancy abruptly
        changing the subject mid-conversation.

        Returns None (never raises) on failure so callers can fall back to
        their existing static response rather than surfacing an error for
        what should be a soft-fail enhancement.
        """
        if not query or not query.strip():
            return None
        try:
            from llm import llm_backend  # deferred: avoid import-order coupling with the registry
            # Confirmed live as a real, separate bug from the conversation-
            # continuity one above: this system prompt used to be ONLY the
            # bare specialization framing below, with none of Nancy's core
            # identity, "Sir" address, personality, or (critically) the
            # brief-for-casual/deep-for-real-questions calibration guidance
            # every other reply path gets -- so any message that happened to
            # match a specialized agent's routing keywords came back
            # clinical and generically short, reading as "gone back to being
            # short and boring" even though the main conversational path was
            # working fine. _system_prompt_for_channel("voice")'s brevity
            # calibration is a genuine calibration (short for small talk,
            # real depth for real questions), not a length cap, so reusing
            # it here doesn't cost anything for questions that deserve depth.
            try:
                from main_new import _system_prompt_for_channel
                base_prompt = _system_prompt_for_channel("voice")
            except Exception:
                base_prompt = ""  # main_new not importable in this context (e.g. a standalone test) -- degrade to the bare framing below rather than failing the whole answer
            system = (
                f"{base_prompt}\n\n"
                f"For this reply specifically, you're drawing on your specialization as {self.agent_name}, "
                f"an expert in {self.domain.replace('-', ' ')}. {self.capabilities.get('description', '')} "
                "Answer the user's specific question or request directly and concretely, "
                "drawing on your domain expertise. Do not just list your capabilities. If recent "
                "conversation history is given below, treat this as a continuation of that same "
                "conversation, not a fresh, unrelated question."
            )
            history = _current_conversation_context.get()
            history_block = f"\n\nRecent conversation so far:\n{history}" if history.strip() else ""
            peer_block = await self._maybe_consult_expert(query)
            prompt = f"{system}{history_block}{peer_block}\n\nUser: {query}\n\nResponse:"
            return await asyncio.wait_for(
                llm_backend.generate(prompt, max_tokens=max_tokens, temperature=temperature),
                timeout=_LLM_ANSWER_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            # Logged distinctly: asyncio.TimeoutError stringifies to an EMPTY
            # string, so the generic handler below reported it as
            # "_llm_answer failed for X: " with no reason at all -- which is
            # exactly how a real collaboration revision round silently
            # produced nothing and looked like the agent had no answer.
            self.logger.warning(
                "_llm_answer TIMED OUT after %.0fs for %s (%d-char prompt) -- raise "
                "AGENT_LLM_TIMEOUT_S if this is a long prompt rather than a hang",
                _LLM_ANSWER_TIMEOUT_S, self.agent_name, len(prompt),
            )
            return None
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
        """Run a task immediately (bypasses queue) and return result.

        `is_processing` used to only be set by the queue path
        (`_process_queue`), so a task run directly through this method --
        which is what /agents/run and /agents/auto actually use -- left
        `get_info()`'s `status`/`load` reporting "idle" the entire time a
        real task was executing. Setting it here too means the fleet roster
        genuinely reflects live execution regardless of which path a task
        came in through, instead of only being honest for the queue path
        nothing currently calls from the REST API.
        """
        start = time.time()
        self._total_tasks += 1
        self.is_processing = True
        self._current_task_type = str(task_data.get("type", "unknown"))
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
        finally:
            self.is_processing = False
            self._current_task_type = None

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
                self._current_task_type = str(task["data"].get("type", "unknown"))

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
            self._current_task_type = None

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
            "status":        "executing" if self.is_processing else ("online" if self._running or self._initialized else "idle"),
            "current_task_type": self._current_task_type,
            "queue_length":  len(self.task_queue),
            "is_processing": self.is_processing,
            "total_tasks":   self._total_tasks,
            "failed_tasks":  self._failed_tasks,
            "success_rate":  success_rate,
            "uptime_s":      uptime,
            "initialized":   self._initialized,
        }

    def get_info(self) -> Dict[str, Any]:
        """Lightweight info for the frontend agent list. `status` is
        "executing" for the real duration of an in-flight task (see
        run_task/_process_queue), not a decorative value -- the frontend's
        snake-border animation speed is driven directly by this field."""
        return {
            "key":             self.domain.replace("-", "_"),
            "name":            self.agent_name,
            "domain":          self.domain,
            "description":     self.capabilities.get("description", ""),
            "confidence":      self.capabilities.get("confidence", 0.8),
            "specializations": self.capabilities.get("specializations", []),
            "status":          "executing" if self.is_processing else ("online" if self._initialized else "idle"),
            "current_task_type": self._current_task_type,
            "load":            min(100, len(self.task_queue) * 10 + (10 if self.is_processing else 0)),
            "total_tasks":     self._total_tasks,
            # Honesty flags (default real/production for most agents; agents
            # working with hardware that isn't connected, or that are pure
            # internal simulations, override these in their own capabilities
            # dict — see e.g. neural_interface_agent.py, multi_agent_swarm_coordinator.py).
            "mode":              self.capabilities.get("mode", "production"),
            "hardware_connected": self.capabilities.get("hardware_connected"),
        }
