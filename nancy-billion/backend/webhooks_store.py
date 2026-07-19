"""Real, persisted outbound webhook subscriptions.

Same JSON-file persistence pattern as cron_store.py/skills_store.py/
statusline_store.py. A webhook is a real URL that gets a real HTTP POST
when a real event happens in this backend -- not a form that writes to a
list nothing ever reads. Two real events currently wired up (see
main_new.py's _cron_execution_loop and /agents/run): "cron_job_ran" and
"agent_task_completed".
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "webhooks.json"

WebhookEvent = Literal["cron_job_ran", "agent_task_completed"]
VALID_EVENTS: set[str] = {"cron_job_ran", "agent_task_completed"}


@dataclass
class Webhook:
    id: str
    url: str
    event: str
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_fired_at: Optional[float] = None
    last_status: Optional[str] = None  # "ok" | "http_<code>" | "error: <msg>"
    fire_count: int = 0


class WebhookStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._hooks: dict[str, Webhook] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for item in raw:
                hook = Webhook(**item)
                self._hooks[hook.id] = hook
        except Exception:
            logger.exception("Failed to load webhooks.json — starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(h) for h in self._hooks.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list(self) -> list[Webhook]:
        return sorted(self._hooks.values(), key=lambda h: h.created_at, reverse=True)

    def for_event(self, event: str) -> list[Webhook]:
        return [h for h in self._hooks.values() if h.enabled and h.event == event]

    def create(self, url: str, event: str) -> Webhook:
        hook = Webhook(id=uuid.uuid4().hex[:12], url=url, event=event)
        self._hooks[hook.id] = hook
        self._save()
        return hook

    def delete(self, hook_id: str) -> bool:
        if hook_id not in self._hooks:
            return False
        del self._hooks[hook_id]
        self._save()
        return True

    def set_enabled(self, hook_id: str, enabled: bool) -> Optional[Webhook]:
        hook = self._hooks.get(hook_id)
        if not hook:
            return None
        hook.enabled = enabled
        self._save()
        return hook

    def mark_fired(self, hook_id: str, status: str) -> None:
        hook = self._hooks.get(hook_id)
        if not hook:
            return
        hook.last_fired_at = time.time()
        hook.last_status = status
        hook.fire_count += 1
        self._save()


webhook_store = WebhookStore()
