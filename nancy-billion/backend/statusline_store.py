"""Real, persisted status-display configuration.

Honest adaptation of Claude Code's "statusline-setup" concept: Billion is a
web dashboard, not a CLI, so there's no literal terminal statusline to
configure. What genuinely maps is the equivalent real feature -- which live
metrics appear in the dashboard's status strips (Overview's "Mission
Briefing" bar, the Fleet Console header) and in what order. This is real,
saved, and actually read by the frontend -- not a stub standing in for a
CLI feature that doesn't apply here.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "statusline_config.json"

VALID_METRICS = {
    "cpu", "memory", "disk", "network", "uptime",
    "agents_online", "total_tasks", "success_rate", "clock",
}
DEFAULT_METRICS = ["uptime", "agents_online", "total_tasks", "success_rate"]


@dataclass
class StatuslineConfig:
    metrics: list[str] = field(default_factory=lambda: list(DEFAULT_METRICS))
    refresh_ms: int = 5000


class StatuslineStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._config = StatuslineConfig()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._config = StatuslineConfig(
                metrics=[m for m in raw.get("metrics", DEFAULT_METRICS) if m in VALID_METRICS] or list(DEFAULT_METRICS),
                refresh_ms=int(raw.get("refresh_ms", 5000)),
            )
        except Exception:
            logger.exception("Failed to load statusline_config.json — using defaults")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(self._config), indent=2), encoding="utf-8")

    def get(self) -> StatuslineConfig:
        return self._config

    def set(self, metrics: Optional[list[str]] = None, refresh_ms: Optional[int] = None) -> StatuslineConfig:
        if metrics is not None:
            cleaned = [m for m in metrics if m in VALID_METRICS]
            if not cleaned:
                raise ValueError(f"No valid metrics in {metrics}; valid options: {sorted(VALID_METRICS)}")
            self._config.metrics = cleaned
        if refresh_ms is not None:
            if refresh_ms < 1000:
                raise ValueError("refresh_ms must be at least 1000 (1s) to avoid hammering the backend")
            self._config.refresh_ms = refresh_ms
        self._save()
        return self._config


statusline_store = StatuslineStore()
