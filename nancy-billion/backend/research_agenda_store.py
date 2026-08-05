"""Real, rotating research topic list for the fleet-sweep loop's two
open-domain research agents (general_research, science_research).

Before this, both agents had zero fleet-sweep-safe task types at all (see
main_new.py's _SWEEP_SAFE_TASK_TYPES) -- their real "brief"/"literature-
synthesis" handlers both require a 'topic' the sweep loop has no way to
invent safely, so they received zero autonomous background work. This store
supplies that missing parameter: a fixed, seeded list of real topics, each
tracked by when it was last actually run, so the sweep loop can hand out
"next due" topics the same fair, least-recently-used way it already picks
agents (see _fleet_sweep_loop's roster sort).

Same tiny JSON-store pattern as watch_store.py/digest_store.py.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "research_agenda.json"

# Deliberately excludes crypto/forex/sports/cars/music -- those already have
# real, API-grounded specialists (forex_intelligence, basketball_intelligence,
# football_intelligence, automotive_specs, music_knowledge). These topics are
# the ones the user asked for that have no dedicated agent, so they land on
# the two general Wikipedia-grounded research agents instead.
_DEFAULT_TOPICS: Dict[str, List[str]] = {
    "general_research": [
        "politics", "history", "general physics", "Rust (programming language)",
        "Next.js", "React (software)", "cybersecurity", "cloud computing",
        "database", "vector database", "knowledge graph", "memory management",
        "robotics", "speech synthesis", "large language model", "design system",
    ],
    "science_research": [
        "thermodynamics", "classical mechanics", "organic chemistry", "cell biology",
    ],
}

_TASK_TYPE_FOR_AGENT: Dict[str, str] = {
    "general_research": "brief",
    "science_research": "literature-synthesis",
}


@dataclass
class ResearchTopic:
    id: str
    agent_key: str
    topic: str
    task_type: str = "brief"
    last_run_at: Optional[float] = None
    run_count: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ResearchAgendaStore:
    def __init__(self, path: Path = STORE_PATH) -> None:
        self.path = path
        self._topics: Dict[str, ResearchTopic] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._seed_defaults()
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for t in raw:
                topic = ResearchTopic(**t)
                self._topics[topic.id] = topic
        except Exception:
            logger.exception("Failed to load research_agenda.json -- reseeding defaults")
            self._seed_defaults()

    def _seed_defaults(self) -> None:
        for agent_key, topics in _DEFAULT_TOPICS.items():
            task_type = _TASK_TYPE_FOR_AGENT.get(agent_key, "brief")
            for topic in topics:
                t = ResearchTopic(id=uuid.uuid4().hex[:12], agent_key=agent_key, topic=topic, task_type=task_type)
                self._topics[t.id] = t
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [t.to_dict() for t in self._topics.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list_for(self, agent_key: str) -> List[ResearchTopic]:
        return [t for t in self._topics.values() if t.agent_key == agent_key]

    def next_due(self, agent_key: str) -> Optional[ResearchTopic]:
        """Least-recently-run topic for this agent -- never-run (None) sorts
        first, so a fresh topic always gets its turn before a repeat."""
        candidates = self.list_for(agent_key)
        if not candidates:
            return None
        return min(candidates, key=lambda t: (t.last_run_at is not None, t.last_run_at or 0.0))

    def mark_run(self, topic_id: str) -> None:
        topic = self._topics.get(topic_id)
        if topic is None:
            return
        topic.last_run_at = time.time()
        topic.run_count += 1
        self._save()


research_agenda_store = ResearchAgendaStore()
