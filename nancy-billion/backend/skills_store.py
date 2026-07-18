"""Real, persisted, user-creatable custom skills.

The Skills page already showed real specializations pulled live from the
29 agents' actual Python-defined capabilities (read-only, since those are
compiled into each agent class). This store adds a second, genuinely
writable layer on top: named skill *references* a user can create, tag
with a category, and assign to one or more real agents -- persisted to
disk, not a form that resets on refresh.

Honesty note: creating a skill here does not reprogram an agent's Python
capabilities (that would require writing/deploying new agent code and
should not be pretended in a config-form). It creates a real, saved,
listable record of an intended capability, assignable to real agents,
which is what "Skills" pages generally provide in agent-fleet tooling.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "skills.json"


@dataclass
class Skill:
    id: str
    name: str
    description: str
    category: str
    agent_keys: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class SkillsStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._skills: dict[str, Skill] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for item in raw:
                skill = Skill(**item)
                self._skills[skill.id] = skill
        except Exception:
            logger.exception("Failed to load skills.json — starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(s) for s in self._skills.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list(self) -> list[Skill]:
        return sorted(self._skills.values(), key=lambda s: s.name.lower())

    def create(self, name: str, description: str, category: str, agent_keys: list[str]) -> Skill:
        skill = Skill(
            id=uuid.uuid4().hex[:12],
            name=name,
            description=description,
            category=category,
            agent_keys=agent_keys,
        )
        self._skills[skill.id] = skill
        self._save()
        return skill

    def update(self, skill_id: str, **fields) -> Optional[Skill]:
        skill = self._skills.get(skill_id)
        if not skill:
            return None
        for k, v in fields.items():
            if v is not None and hasattr(skill, k):
                setattr(skill, k, v)
        self._save()
        return skill

    def delete(self, skill_id: str) -> bool:
        if skill_id not in self._skills:
            return False
        del self._skills[skill_id]
        self._save()
        return True


skills_store = SkillsStore()
