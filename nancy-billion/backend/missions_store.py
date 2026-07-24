"""Real, persisted AI missions -- the backend entity behind the Workflow
Orchestrator. Same JSON-file persistence pattern as cron_store.py/
skills_store.py/webhooks_store.py (see webhooks_store.py's docstring).

A mission moves through exactly the pipeline the product spec defines:
    planning -> reasoning -> dependency_resolution -> agent_assignment ->
    execution -> validation -> human_approval -> deployment -> completed

This module is pure persistence + validation -- it does not know about
event_bus or WebSockets. main_new.py's /missions endpoints call this store
and then publish the real event (MISSION_CREATED, MISSION_ASSIGNED, ...),
the same layering cron_store/webhook_store already use with _fire_webhooks.
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

STORE_PATH = Path(__file__).parent / "data" / "missions.json"

# Ordered -- this IS the pipeline. Index order is used for "forward/backward"
# checks and by the frontend's column layout. `mission_created` is the real
# intake moment (create() lands here, before any real planning has
# happened); `archive` replaces the old terminal `completed` name -- see
# _load()'s migration for the one-time rename of any already-persisted rows.
VALID_STAGES: tuple[str, ...] = (
    "mission_created", "planning", "reasoning", "dependency_resolution", "agent_assignment",
    "execution", "validation", "human_approval", "deployment", "archive",
)
_LEGACY_STAGE_MAP = {"completed": "archive"}
VALID_PRIORITIES = {"low", "medium", "high", "critical"}
VALID_RISKS = {"low", "medium", "high"}


class MissionError(ValueError):
    """Raised for a real validation failure (bad stage, unmet dependency, ...) --
    callers (main_new.py) turn this into an HTTP 400/409, never silently
    swallow it into a fabricated success."""


@dataclass
class Mission:
    id: str
    title: str
    description: str = ""
    stage: str = "mission_created"
    assigned_agent: Optional[str] = None
    owner: str = ""
    priority: str = "medium"
    risk: str = "low"
    estimated_cost: Optional[float] = None
    due_date: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    subtasks: List[Dict[str, Any]] = field(default_factory=list)
    order: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    dispatched_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    cancelled: bool = False
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_public_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MissionStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._missions: Dict[str, Mission] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for item in raw:
                # One-time forward-migration for rows persisted before the
                # mission_created/archive stage rename -- real prior data,
                # never dropped, just relabelled to the current pipeline.
                if item.get("stage") in _LEGACY_STAGE_MAP:
                    item["stage"] = _LEGACY_STAGE_MAP[item["stage"]]
                for entry in item.get("history", []):
                    if entry.get("stage") in _LEGACY_STAGE_MAP:
                        entry["stage"] = _LEGACY_STAGE_MAP[entry["stage"]]
                m = Mission(**item)
                self._missions[m.id] = m
        except Exception:
            logger.exception("Failed to load missions.json — starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(m) for m in self._missions.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    def list(self) -> List[Mission]:
        return sorted(self._missions.values(), key=lambda m: m.order)

    def get(self, mission_id: str) -> Optional[Mission]:
        return self._missions.get(mission_id)

    def create(
        self,
        title: str,
        *,
        description: str = "",
        owner: str = "",
        priority: str = "medium",
        risk: str = "low",
        estimated_cost: Optional[float] = None,
        due_date: Optional[str] = None,
        tags: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        subtasks: Optional[List[Dict[str, Any]]] = None,
        assigned_agent: Optional[str] = None,
    ) -> Mission:
        if priority not in VALID_PRIORITIES:
            raise MissionError(f"priority must be one of {sorted(VALID_PRIORITIES)}")
        if risk not in VALID_RISKS:
            raise MissionError(f"risk must be one of {sorted(VALID_RISKS)}")
        now = time.time()
        mission = Mission(
            id=uuid.uuid4().hex[:12],
            title=title,
            description=description,
            owner=owner,
            priority=priority,
            risk=risk,
            estimated_cost=estimated_cost,
            due_date=due_date,
            tags=tags or [],
            dependencies=dependencies or [],
            subtasks=subtasks or [],
            assigned_agent=assigned_agent,
            order=now,
            created_at=now,
            updated_at=now,
            history=[{"stage": "mission_created", "at": now}],
        )
        self._missions[mission.id] = mission
        self._save()
        return mission

    def update(self, mission_id: str, **fields: Any) -> Optional[Mission]:
        """Partial update of editable fields -- never touches stage/history/
        result (those go through transition()/record_result() so every real
        state change has a matching event)."""
        mission = self._missions.get(mission_id)
        if mission is None:
            return None
        editable = {
            "title", "description", "owner", "priority", "risk", "estimated_cost",
            "due_date", "tags", "dependencies", "subtasks", "order",
        }
        for key, value in fields.items():
            if key not in editable:
                continue
            if key == "priority" and value not in VALID_PRIORITIES:
                raise MissionError(f"priority must be one of {sorted(VALID_PRIORITIES)}")
            if key == "risk" and value not in VALID_RISKS:
                raise MissionError(f"risk must be one of {sorted(VALID_RISKS)}")
            setattr(mission, key, value)
        mission.updated_at = time.time()
        self._save()
        return mission

    def assign(self, mission_id: str, agent_key: Optional[str]) -> Optional[Mission]:
        mission = self._missions.get(mission_id)
        if mission is None:
            return None
        mission.assigned_agent = agent_key
        mission.updated_at = time.time()
        self._save()
        return mission

    def transition(self, mission_id: str, stage: str) -> Mission:
        mission = self._missions.get(mission_id)
        if mission is None:
            raise MissionError(f"mission '{mission_id}' not found")
        if stage not in VALID_STAGES:
            raise MissionError(f"stage must be one of {VALID_STAGES}")
        if stage == "execution":
            unmet = [
                dep_id for dep_id in mission.dependencies
                if (dep := self._missions.get(dep_id)) is None or dep.stage != "archive" or dep.cancelled
            ]
            if unmet:
                raise MissionError(
                    f"cannot enter execution — {len(unmet)} unresolved dependenc{'y' if len(unmet) == 1 else 'ies'}: {unmet}"
                )
        if stage == "agent_assignment" and not mission.assigned_agent:
            raise MissionError("cannot enter agent_assignment without an assigned_agent — assign one first")
        mission.stage = stage
        mission.updated_at = time.time()
        mission.history.append({"stage": stage, "at": mission.updated_at})
        self._save()
        return mission

    def record_result(self, mission_id: str, *, success: bool, text: str, saved_file: Optional[str] = None) -> Optional[Mission]:
        mission = self._missions.get(mission_id)
        if mission is None:
            return None
        mission.result = {"success": success, "text": text, "at": time.time(), "savedFile": saved_file}
        mission.updated_at = time.time()
        self._save()
        return mission

    def set_dispatched(self, mission_id: str) -> Optional[Mission]:
        mission = self._missions.get(mission_id)
        if mission is None:
            return None
        mission.dispatched_at = time.time()
        self._save()
        return mission

    def cancel(self, mission_id: str) -> Optional[Mission]:
        mission = self._missions.get(mission_id)
        if mission is None:
            return None
        mission.cancelled = True
        mission.updated_at = time.time()
        self._save()
        return mission

    def delete(self, mission_id: str) -> bool:
        if mission_id not in self._missions:
            return False
        del self._missions[mission_id]
        for m in self._missions.values():
            if mission_id in m.dependencies:
                m.dependencies = [d for d in m.dependencies if d != mission_id]
        self._save()
        return True


mission_store = MissionStore()
