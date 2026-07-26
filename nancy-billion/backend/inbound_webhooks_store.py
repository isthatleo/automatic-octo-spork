"""Real, persisted INBOUND webhook endpoints -- the reverse of
webhooks_store.py's outbound subscriptions. An external service (GitHub, a
CI pipeline, any HTTP client) POSTs to /webhooks/inbound/{id} and it
actually triggers a real action here (telegram_message, agent_task,
run_skill, terminal_command -- the exact same ActionType vocabulary
cron_store.py already uses, since an inbound webhook is really just "a job
triggered by an external HTTP call instead of a schedule").

Same JSON-file persistence pattern as cron_store.py/webhooks_store.py.
"""
from __future__ import annotations

import json
import logging
import secrets
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "inbound_webhooks.json"


@dataclass
class InboundWebhook:
    id: str
    name: str
    action_type: str  # "telegram_message" | "agent_task" | "run_skill" | "terminal_command"
    action_payload: Dict[str, Any] = field(default_factory=dict)
    # HMAC-SHA256 shared secret -- when set, an incoming request MUST include
    # a matching `X-Nancy-Signature: sha256=<hex>` header (computed over the
    # raw request body) or it's rejected with 401. When unset, the endpoint
    # is intentionally unauthenticated -- the user's own explicit choice
    # (e.g. testing), not a silent default.
    secret: Optional[str] = None
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_triggered_at: Optional[float] = None
    last_result: Optional[str] = None
    trigger_count: int = 0

    def to_public_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["has_secret"] = bool(d.pop("secret"))
        return d


class InboundWebhookStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._hooks: Dict[str, InboundWebhook] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for item in raw:
                hook = InboundWebhook(**item)
                self._hooks[hook.id] = hook
        except Exception:
            logger.exception("Failed to load inbound_webhooks.json — starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(h) for h in self._hooks.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list(self) -> list[InboundWebhook]:
        return sorted(self._hooks.values(), key=lambda h: h.created_at)

    def get(self, hook_id: str) -> Optional[InboundWebhook]:
        return self._hooks.get(hook_id)

    def create(self, name: str, action_type: str, action_payload: Dict[str, Any], generate_secret: bool = True) -> InboundWebhook:
        hook = InboundWebhook(
            id=uuid.uuid4().hex[:12],
            name=name,
            action_type=action_type,
            action_payload=action_payload,
            secret=secrets.token_hex(24) if generate_secret else None,
        )
        self._hooks[hook.id] = hook
        self._save()
        return hook

    def delete(self, hook_id: str) -> bool:
        if hook_id not in self._hooks:
            return False
        del self._hooks[hook_id]
        self._save()
        return True

    def set_enabled(self, hook_id: str, enabled: bool) -> Optional[InboundWebhook]:
        hook = self._hooks.get(hook_id)
        if hook is None:
            return None
        hook.enabled = enabled
        self._save()
        return hook

    def mark_triggered(self, hook_id: str, result: str) -> None:
        hook = self._hooks.get(hook_id)
        if hook is None:
            return
        hook.last_triggered_at = time.time()
        hook.last_result = result[:500]
        hook.trigger_count += 1
        self._save()


inbound_webhook_store = InboundWebhookStore()
