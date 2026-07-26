"""Real, persisted skill bundles -- a named group of skills invoked as one
unit, per Hermes's real bundle concept (hermes_cli/bundles.py wraps
agent/skill_bundles.py: a small YAML file naming a set of skills, triggered
as one `/<bundle>` command). Nancy's version: a bundle names existing
skill_loader.py skills by name; running it (via cron's run_skill action or
directly) injects every named skill's real instructions into one prompt
instead of skill_loader's normal keyword-matched top-2 selection -- useful
for a job that should always follow several specific procedures together
(e.g. a "morning-ops" bundle of system-monitoring + trading-analysis),
without needing trigger keywords to coincidentally match all of them.

Same JSON-file persistence pattern as cron_store.py/canvas_store.py.
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

STORE_PATH = Path(__file__).parent / "data" / "skill_bundles.json"


@dataclass
class SkillBundle:
    id: str
    name: str
    skill_names: List[str] = field(default_factory=list)
    description: str = ""
    created_at: float = field(default_factory=time.time)

    def to_public_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SkillBundleStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._bundles: Dict[str, SkillBundle] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for item in raw:
                b = SkillBundle(**item)
                self._bundles[b.id] = b
        except Exception:
            logger.exception("Failed to load skill_bundles.json — starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(b) for b in self._bundles.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list(self) -> List[SkillBundle]:
        return sorted(self._bundles.values(), key=lambda b: b.name)

    def get(self, bundle_id: str) -> Optional[SkillBundle]:
        return self._bundles.get(bundle_id)

    def get_by_name(self, name: str) -> Optional[SkillBundle]:
        return next((b for b in self._bundles.values() if b.name == name), None)

    def create(self, name: str, skill_names: List[str], description: str = "") -> SkillBundle:
        bundle = SkillBundle(id=uuid.uuid4().hex[:12], name=name, skill_names=skill_names, description=description)
        self._bundles[bundle.id] = bundle
        self._save()
        return bundle

    def delete(self, bundle_id: str) -> bool:
        if bundle_id not in self._bundles:
            return False
        del self._bundles[bundle_id]
        self._save()
        return True


skill_bundle_store = SkillBundleStore()
