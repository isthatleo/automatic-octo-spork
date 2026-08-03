"""Semantic capability index over the live agent roster.

Answers "who is actually the right specialist for this?" -- the thing the
collaboration layer needed to stop requiring hardcoded agent keys, and the
thing an agent needs to recognise that a question sits outside its own
expertise.

WHY SEMANTIC AND NOT KEYWORDS: agent_service._ROUTE_RULES already does
keyword matching, and its limits are exactly why this exists. Keywords
match "docker" to a DevOps agent whether the user wants a container
inspected or the desktop app launched, and they match nothing at all for a
question phrased in words nobody happened to list. Each agent already
publishes a real self-description (name, domain, description,
specializations); embedding that and comparing it to the question is a
truer answer to "is this yours?" than substring presence.

Cost is near-zero at query time: the roster is embedded ONCE and cached
(agents are registered at startup and do not change), leaving a single
short embed per lookup. It reuses memory/graph.py's
SentenceTransformerEmbedding, whose model is a class-level shared
singleton -- so this adds no second model load and no extra RAM.
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Thresholds calibrated against MEASURED scores on this roster and model
# (all-MiniLM-L6-v2), not guessed. Real top-1 results:
#
#   "gravitational lensing ... galaxy cluster mass" -> astrophysics    0.325
#   "position sizing in leveraged forex"            -> crypto_trading  0.276
#   "is my SSL certificate expiring"                -> ssl_certificate 0.575
#   ...with unrelated agents landing at 0.10-0.19 in every case.
#
# The correct specialist ranks #1 every time, but absolute cosine values sit
# low because a terse domain profile and a natural-language question are
# lexically far apart even when semantically right. An earlier 0.30 bar
# therefore rejected a correct 0.276 match outright. What actually
# discriminates is rank plus the margin over the runner-up (0.325 vs 0.162,
# 0.575 vs 0.188 -- roughly 2-3x), so the absolute floor only needs to
# exclude the 0.10-0.19 noise band.
MIN_EXPERT_SCORE = 0.20

# A reviewer is held to a LOWER bar than a producer, deliberately. The
# second-best agent scores lower than the best by definition, so reusing the
# producer's threshold made a reviewer unfindable for exactly the queries
# with one strong specialist -- e.g. ssl_certificate (0.575) had no eligible
# reviewer because the next candidate, security, scored 0.188. Critique is
# also substantially domain-general: _CRITIQUE_PROMPT asks for unsupported
# figures, unanswered parts and reasoning that does not follow, which a
# competent adjacent specialist can judge. This floor only rules out an
# agent with no relationship to the topic at all.
MIN_REVIEWER_SCORE = 0.10

# How much better another agent must score before an agent treats a question
# as outside its own expertise. Lowered from 0.15 for the same reason as
# above -- the useful signal lives in a compressed range, so 0.15 demanded a
# gap most genuine handoffs never show. A consult still costs a real agent
# run, so this stays large enough that borderline questions are answered
# rather than passed around.
DEFAULT_HANDOFF_MARGIN = 0.10


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class CapabilityIndex:
    """Embeds each agent's own published capabilities and ranks them
    against a question."""

    def __init__(self) -> None:
        self._vectors: Dict[str, List[float]] = {}
        self._profiles: Dict[str, str] = {}
        self._engine = None
        self._lock = threading.Lock()
        self._built = False

    # -- construction ---------------------------------------------------

    def _get_engine(self):
        if self._engine is None:
            from memory.graph import SentenceTransformerEmbedding

            # Model is a class-level shared singleton inside that class, so
            # this reuses whatever the memory graph already loaded.
            self._engine = SentenceTransformerEmbedding()
        return self._engine

    @staticmethod
    def _profile_text(info: Dict[str, Any]) -> str:
        """The agent's own words about itself -- never a hand-written label
        here, so a newly registered agent is indexed correctly with no
        change to this file."""
        parts = [
            str(info.get("name") or ""),
            str(info.get("domain") or "").replace("-", " "),
            str(info.get("description") or ""),
            " ".join(str(s).replace("-", " ") for s in (info.get("specializations") or [])),
        ]
        return ". ".join(p for p in parts if p.strip())

    def _build_sync(self, roster: List[Dict[str, Any]]) -> None:
        engine = self._get_engine()
        vectors: Dict[str, List[float]] = {}
        profiles: Dict[str, str] = {}
        for info in roster:
            key = info.get("key")
            if not key or info.get("status") == "offline":
                continue
            text = self._profile_text(info)
            if not text.strip():
                continue
            try:
                vectors[key] = engine.embed(text)
                profiles[key] = text
            except Exception:
                logger.exception("capability_index: failed to embed agent %s", key)
        self._vectors = vectors
        self._profiles = profiles
        self._built = True
        logger.info("capability_index: embedded %d agent capability profiles", len(vectors))

    async def ensure_built(self) -> None:
        """Builds the index once, off the event loop.

        Embedding ~70 short profiles is real CPU work; doing it inline on
        the loop would stall every concurrent request, which is exactly the
        class of GIL/blocking problem that already cost this codebase real
        latency in the TTS path.
        """
        if self._built:
            return
        from .agent_service import agent_service

        with self._lock:
            if self._built:
                return
        roster = agent_service.list_agents()
        await asyncio.get_event_loop().run_in_executor(None, self._build_sync, roster)

    def invalidate(self) -> None:
        """Drop the cache -- call if the roster ever changes at runtime."""
        self._built = False

    # -- queries --------------------------------------------------------

    async def rank(
        self, query: str, *, exclude: Optional[set] = None, k: int = 5,
    ) -> List[Tuple[str, float]]:
        """Agents ranked by genuine semantic fit to `query`."""
        await self.ensure_built()
        if not self._vectors or not (query or "").strip():
            return []
        engine = self._get_engine()
        qv = await asyncio.get_event_loop().run_in_executor(None, engine.embed, query)
        exclude = exclude or set()
        scored = [
            (key, _cosine(qv, vec))
            for key, vec in self._vectors.items()
            if key not in exclude
        ]
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored[:k]

    async def best_expert(
        self, query: str, *, exclude: Optional[set] = None, min_score: float = MIN_EXPERT_SCORE,
    ) -> Optional[Tuple[str, float]]:
        """The single best-fitting agent, or None if nobody fits convincingly."""
        ranked = await self.rank(query, exclude=exclude, k=1)
        if not ranked or ranked[0][1] < min_score:
            return None
        return ranked[0]

    async def score_for(self, agent_key: str, query: str) -> float:
        """How well one specific agent fits a question -- used by an agent to
        judge its OWN fit before deciding to hand off."""
        await self.ensure_built()
        vec = self._vectors.get(agent_key)
        if not vec:
            return 0.0
        engine = self._get_engine()
        qv = await asyncio.get_event_loop().run_in_executor(None, engine.embed, query)
        return _cosine(qv, vec)

    async def should_hand_off(
        self, agent_key: str, query: str, *, margin: float = DEFAULT_HANDOFF_MARGIN,
    ) -> Optional[Tuple[str, float, float]]:
        """Is this question materially better suited to someone else?

        Returns (expert_key, expert_score, own_score) when another agent is
        a clearly better fit, else None. Requires BOTH a convincing absolute
        score and a real margin over this agent's own fit -- a marginally
        better peer is not worth the cost and latency of a handoff.
        """
        await self.ensure_built()
        if agent_key not in self._vectors:
            return None
        ranked = await self.rank(query, k=2)
        if not ranked:
            return None
        own = await self.score_for(agent_key, query)
        for key, score in ranked:
            if key == agent_key:
                continue
            if score >= MIN_EXPERT_SCORE and (score - own) >= margin:
                return key, score, own
            break  # only the top non-self candidate is worth considering
        return None

    async def pick_reviewer(self, producer_key: str, goal: str) -> Optional[str]:
        """A genuinely qualified reviewer for a producer's work on `goal`.

        Deliberately excludes the producer: an agent reviewing its own
        output is not a critique, and the whole value of the review step is
        that it comes from somewhere else.
        """
        ranked = await self.rank(goal, exclude={producer_key}, k=1)
        if not ranked or ranked[0][1] < MIN_REVIEWER_SCORE:
            return None
        return ranked[0][0]


capability_index = CapabilityIndex()
