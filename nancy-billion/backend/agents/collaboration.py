"""Peer collaboration layer -- the primitive the agent fleet was missing.

Every existing execution path is TOP-DOWN: agent_service.run() dispatches
into an agent, DispatcherAgent fans out to 1-3 agents in parallel and merges
their answers, TaskOrchestratorAgent generates work and delegates it. In all
three, agents run in isolation: none can see another's output, none can ask
another a question mid-task, and nothing ever reviews anything. That gives a
hierarchy of workers, not a society of specialists.

This module adds the sideways edge, and three things composed from it:

    consult(...)            one agent asks another a real question mid-task
    critique(...)           one agent reviews another's work against the task
    produce_and_refine(...) produce -> critique -> revise, bounded

plus a Blackboard so agents working the same goal can actually read each
other's contributions instead of duplicating them.

WHY A SEPARATE MODULE, NOT METHODS ON BaseAgent: the cycle-safety state has
to be shared across every agent in a call chain, and agents are instantiated
independently by the registry. A ContextVar carries the chain through
arbitrarily deep async dispatch without threading a parameter through all
~70 agent files -- the same pattern this codebase already uses for
_current_conversation_context, _current_voice_match and _current_turn_audio.

CYCLE SAFETY IS THE LOAD-BEARING PART. The moment agents can call each
other, A -> B -> A becomes reachable, and with LLM-chosen targets it WILL be
reached. Every consult records its chain in a ContextVar; re-entering an
agent already in the chain is refused outright, and the chain is hard-capped
by depth. Without both, one bad routing decision is an unbounded recursion
that costs real money per hop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# The chain of agent keys currently on the stack for this async task, e.g.
# ("dispatcher", "economics"). Read to refuse cycles, and to bound depth.
_delegation_chain: ContextVar[Tuple[str, ...]] = ContextVar("_delegation_chain", default=())

# A consult costs a real agent run (often an LLM call). Three hops is enough
# for "ask a specialist, who asks one more" without letting a routing mistake
# turn into an expensive tree.
MAX_DELEGATION_DEPTH = 3
CONSULT_TIMEOUT_S = 45.0
CRITIQUE_TIMEOUT_S = 45.0


def current_chain() -> Tuple[str, ...]:
    """The agent keys currently on the delegation stack."""
    return _delegation_chain.get()


class DelegationRefused(Exception):
    """Raised when a consult would cycle or exceed the depth cap. Callers
    should treat this as 'answer it yourself', not as a hard failure."""


@dataclass
class Contribution:
    """One agent's real contribution to a shared goal, with provenance --
    who produced it, when, and off the back of which delegation chain."""
    agent_key: str
    content: str
    kind: str = "finding"  # finding | critique | revision
    chain: Tuple[str, ...] = ()
    at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_key": self.agent_key, "content": self.content, "kind": self.kind,
            "chain": list(self.chain), "at": self.at,
        }


class Blackboard:
    """Shared working memory for one goal.

    The 'collaborate' half of the philosophy: agents assigned the same goal
    write here and read what peers have already established, so a second
    agent builds on the first instead of re-deriving it in parallel
    ignorance. Deliberately in-memory and per-goal -- durable findings go to
    the memory graph via the caller, not here; this is scratch space for a
    single piece of work.
    """

    def __init__(self, goal: str) -> None:
        self.goal = goal
        self.contributions: List[Contribution] = []

    def add(self, agent_key: str, content: str, kind: str = "finding") -> None:
        content = (content or "").strip()
        if not content:
            return
        self.contributions.append(
            Contribution(agent_key=agent_key, content=content, kind=kind, chain=current_chain())
        )

    def digest(self, *, exclude: Optional[str] = None, limit: int = 8, max_chars: int = 500) -> str:
        """What peers have established so far, as prompt-ready text. Excludes
        the requesting agent's own contributions so it isn't fed its own words
        back as if they were peer input."""
        rows = [c for c in self.contributions if c.agent_key != exclude]
        if not rows:
            return ""
        lines = [
            f"- [{c.agent_key}] ({c.kind}) {c.content[:max_chars]}"
            for c in rows[-limit:]
        ]
        return "What your peers have established so far:\n" + "\n".join(lines)

    def to_list(self) -> List[Dict[str, Any]]:
        return [c.to_dict() for c in self.contributions]


async def consult(
    to_agent_key: str,
    question: str,
    *,
    from_agent_key: str = "unknown",
    timeout: float = CONSULT_TIMEOUT_S,
) -> Dict[str, Any]:
    """Ask another agent a real question, mid-task. The 'delegate' pillar.

    Refuses (DelegationRefused) rather than recursing if the target is
    already on the current chain, or if the chain is at MAX_DELEGATION_DEPTH.
    Both are genuine safety limits, not politeness: an LLM-chosen target can
    and will eventually point back at its own caller.
    """
    from .agent_service import agent_service

    chain = current_chain()
    if to_agent_key in chain:
        raise DelegationRefused(
            f"'{to_agent_key}' is already on the delegation chain {chain} -- refusing to cycle"
        )
    if len(chain) >= MAX_DELEGATION_DEPTH:
        raise DelegationRefused(
            f"delegation depth {len(chain)} would exceed MAX_DELEGATION_DEPTH={MAX_DELEGATION_DEPTH}"
        )
    if to_agent_key not in agent_service._agents:
        raise DelegationRefused(f"no such agent '{to_agent_key}'")

    token = _delegation_chain.set(chain + (from_agent_key,) if from_agent_key not in chain else chain)
    try:
        logger.info("consult: %s -> %s (chain=%s)", from_agent_key, to_agent_key, current_chain())
        return await agent_service.run(
            to_agent_key, {"type": "query", "query": question}, timeout=timeout,
        )
    finally:
        _delegation_chain.reset(token)


@dataclass
class Critique:
    """A reviewing agent's real assessment of another agent's work."""
    reviewer: str
    approved: bool
    issues: List[str]
    suggestion: str
    raw: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reviewer": self.reviewer, "approved": self.approved,
            "issues": self.issues, "suggestion": self.suggestion,
        }


_CRITIQUE_PROMPT = """You are reviewing another specialist's work. Be rigorous and specific -- your job is to catch what is wrong, unsupported, or missing, not to be agreeable.

The original task:
{goal}

The work produced by {producer}:
{work}

Assess it against the task. Judge ONLY what is actually there. In particular flag:
- claims presented as measured fact that could not have been measured
- specific figures with no stated source
- parts of the task left unanswered
- reasoning that does not follow

Respond with ONLY a JSON object, no prose and no markdown fences:
{{"approved": true/false, "issues": ["..."], "suggestion": "how to fix it, or empty if approved"}}"""


def _parse_critique(reviewer: str, raw: str) -> Critique:
    """Parse a reviewer's JSON verdict, degrading safely.

    A malformed critique must never be read as approval -- silently
    approving on a parse failure would make the whole review step
    decorative. Unparseable output is treated as 'not approved, reason
    unknown' so the refine loop still surfaces it.
    """
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return Critique(reviewer, False, ["reviewer returned no parseable verdict"], "", raw or "")
    try:
        data = json.loads(match.group(0))
    except (json.JSONDecodeError, ValueError):
        return Critique(reviewer, False, ["reviewer returned malformed JSON"], "", raw or "")
    issues = data.get("issues") or []
    if isinstance(issues, str):
        issues = [issues]
    return Critique(
        reviewer=reviewer,
        approved=bool(data.get("approved", False)),
        issues=[str(i) for i in issues],
        suggestion=str(data.get("suggestion") or ""),
        raw=raw or "",
    )


async def critique(
    reviewer_key: str,
    goal: str,
    work: str,
    *,
    producer_key: str = "another agent",
    timeout: float = CRITIQUE_TIMEOUT_S,
) -> Critique:
    """Have one agent review another's work. The 'critique' pillar.

    Returns a not-approved Critique rather than raising on any failure --
    a review step that can crash the work it reviews is worse than useless.
    """
    from .agent_service import agent_service

    if reviewer_key not in agent_service._agents:
        return Critique(reviewer_key, False, [f"no such reviewer '{reviewer_key}'"], "")
    prompt = _CRITIQUE_PROMPT.format(goal=goal, producer=producer_key, work=work[:4000])
    try:
        result = await agent_service.run(
            reviewer_key, {"type": "query", "query": prompt}, timeout=timeout,
        )
    except Exception as e:
        return Critique(reviewer_key, False, [f"reviewer failed: {e}"], "")
    raw = str(result.get("response") or result.get("result") or "")
    return _parse_critique(reviewer_key, raw)


async def produce_and_refine(
    goal: str,
    producer_key: str,
    reviewer_key: str,
    *,
    rounds: int = 2,
    board: Optional[Blackboard] = None,
    timeout: float = CONSULT_TIMEOUT_S,
) -> Dict[str, Any]:
    """produce -> critique -> revise, bounded. The 'improve one another' pillar.

    This is the loop that makes critique matter: a reviewer's objections are
    fed back to the producer as a real revision request, and the result is
    reviewed again. Bounded by `rounds` because each pass costs two real
    agent runs, and in practice a specialist that cannot satisfy a reviewer
    in two passes is not going to on the fifth.
    """
    from .agent_service import agent_service

    board = board or Blackboard(goal)
    history: List[Dict[str, Any]] = []
    work = ""

    for round_no in range(1, max(1, rounds) + 1):
        if round_no == 1:
            ask = goal
            peers = board.digest(exclude=producer_key)
            if peers:
                ask = f"{goal}\n\n{peers}"
        else:
            last = history[-1]["critique"]
            ask = (
                f"{goal}\n\nYour previous answer was reviewed by {reviewer_key} and needs revision.\n\n"
                f"Your previous answer:\n{work}\n\n"
                f"Issues raised:\n" + "\n".join(f"- {i}" for i in last["issues"]) + "\n\n"
                f"Reviewer's suggestion: {last['suggestion']}\n\n"
                "Produce a corrected, complete answer addressing every issue."
            )

        produced = await agent_service.run(
            producer_key, {"type": "query", "query": ask}, timeout=timeout,
        )
        work = str(produced.get("response") or produced.get("result") or "").strip()
        if not work:
            history.append({"round": round_no, "error": "producer returned nothing"})
            break
        board.add(producer_key, work, kind="finding" if round_no == 1 else "revision")

        verdict = await critique(reviewer_key, goal, work, producer_key=producer_key)
        board.add(reviewer_key, verdict.suggestion or "; ".join(verdict.issues) or "approved", kind="critique")
        history.append({"round": round_no, "work": work, "critique": verdict.to_dict()})

        if verdict.approved:
            break

    return {
        "success": bool(work),
        "goal": goal,
        "producer": producer_key,
        "reviewer": reviewer_key,
        "final": work,
        "approved": bool(history and history[-1].get("critique", {}).get("approved")),
        "rounds_used": len(history),
        "history": history,
        "contributions": board.to_list(),
    }
