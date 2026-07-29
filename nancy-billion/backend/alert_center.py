"""Real green/yellow/red status for Billion's monitored categories -- system
health, LLM backend reliability, dependency vulnerabilities, and
authentication/webhook-signature failure bursts (a real attack signal).

Not a fabricated severity scale bolted onto nothing: every color here is
driven by a signal some other real module already computes --
system_monitor.py's psutil-backed thresholds, self_maintenance.py's live
OSV.dev vulnerability query results, usage_analytics.json's real per-backend
success/failure counts, and a real rolling-window counter of failed
auth/webhook-signature attempts (see main_new.py's `_record_security_failure`
and the loops that call `set_status` below for exactly which signal drives
which category). This module only stores/serves the current color per
category -- it never decides what "red" means on its own.

One CategoryStatus per monitored key, upserted in place (not an
ever-growing log) -- the frontend renders this as a live traffic-light
dashboard, not a dismissible alert feed. `since` tracks when a category's
color last actually changed, so the UI can show "red for 12 minutes"
instead of just "red."
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "alert_center.json"

SEVERITY_ORDER = {"green": 0, "yellow": 1, "red": 2}


@dataclass
class CategoryStatus:
    key: str
    category: str
    title: str
    severity: str
    detail: str
    updated_at: float = field(default_factory=time.time)
    since: float = field(default_factory=time.time)

    def to_public_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AlertCenter:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._statuses: Dict[str, CategoryStatus] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for s in raw:
                status = CategoryStatus(**s)
                self._statuses[status.key] = status
        except Exception:
            logger.exception("Failed to load alert_center.json -- starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(s) for s in self._statuses.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def set_status(self, key: str, category: str, title: str, severity: str, detail: str) -> CategoryStatus:
        if severity not in SEVERITY_ORDER:
            raise ValueError(f"Invalid severity {severity!r} -- must be green/yellow/red")
        existing = self._statuses.get(key)
        now = time.time()
        changed = existing is None or existing.severity != severity
        since = now if changed else existing.since
        status = CategoryStatus(
            key=key, category=category, title=title, severity=severity, detail=detail,
            updated_at=now, since=since,
        )
        self._statuses[key] = status
        self._save()
        return status

    def list(self) -> List[CategoryStatus]:
        return sorted(self._statuses.values(), key=lambda s: (-SEVERITY_ORDER[s.severity], s.key))

    def overall_severity(self) -> str:
        if not self._statuses:
            return "green"
        return max(self._statuses.values(), key=lambda s: SEVERITY_ORDER[s.severity]).severity


alert_center = AlertCenter()
