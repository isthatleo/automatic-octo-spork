"""Real, persisted, user-creatable scheduled jobs.

Distinct from the single hardcoded daily-briefing loop in main_new.py
(_daily_briefing_loop) -- this is a general job store backing the Cron
Jobs page: create/list/toggle/delete jobs, each of which actually runs on
schedule via _cron_execution_loop in main_new.py. No fake "create job"
button that doesn't do anything -- jobs created here are real dicts on
disk, checked and fired every minute.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "cron_jobs.json"

ActionType = Literal["telegram_message", "agent_task"]


@dataclass
class CronJob:
    id: str
    name: str
    description: str
    hour: int
    minute: int
    action_type: ActionType
    # telegram_message: {"text": str}
    # agent_task: {"agent_key": str, "task_type": str, "payload": dict}
    action_payload: dict = field(default_factory=dict)
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_run: Optional[str] = None
    last_result: Optional[str] = None

    def next_run(self) -> str:
        now = datetime.now()
        candidate = now.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate.isoformat()

    def to_public_dict(self) -> dict:
        d = asdict(self)
        d["next_run"] = self.next_run()
        return d


class CronStore:
    """Simple JSON-file-backed job list -- same persistence pattern as
    memory.graph.MemoryGraph, just for scheduled jobs instead of memories."""

    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._jobs: dict[str, CronJob] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for item in raw:
                job = CronJob(**item)
                self._jobs[job.id] = job
        except Exception:
            logger.exception("Failed to load cron_jobs.json — starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(j) for j in self._jobs.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list(self) -> list[CronJob]:
        return sorted(self._jobs.values(), key=lambda j: (j.hour, j.minute))

    def create(self, name: str, description: str, hour: int, minute: int,
               action_type: ActionType, action_payload: dict) -> CronJob:
        job = CronJob(
            id=uuid.uuid4().hex[:12],
            name=name,
            description=description,
            hour=hour,
            minute=minute,
            action_type=action_type,
            action_payload=action_payload,
        )
        self._jobs[job.id] = job
        self._save()
        return job

    def delete(self, job_id: str) -> bool:
        if job_id not in self._jobs:
            return False
        del self._jobs[job_id]
        self._save()
        return True

    def set_enabled(self, job_id: str, enabled: bool) -> Optional[CronJob]:
        job = self._jobs.get(job_id)
        if not job:
            return None
        job.enabled = enabled
        self._save()
        return job

    def mark_run(self, job_id: str, result: str) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        job.last_run = datetime.now().isoformat()
        job.last_result = result[:500]
        self._save()

    def due_jobs(self, now: datetime) -> list[CronJob]:
        """Jobs whose hour/minute matches right now and haven't already
        fired in this exact minute (checked via last_run)."""
        due = []
        for job in self._jobs.values():
            if not job.enabled:
                continue
            if job.hour != now.hour or job.minute != now.minute:
                continue
            if job.last_run:
                last = datetime.fromisoformat(job.last_run)
                if last.date() == now.date() and last.hour == now.hour and last.minute == now.minute:
                    continue
            due.append(job)
        return due


cron_store = CronStore()
