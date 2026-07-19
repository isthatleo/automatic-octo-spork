"""
Statusline Setup Agent for Nancy/Billion Backend

Honest adaptation of Claude Code's "statusline-setup" agent. Billion is a
web dashboard, not a terminal, so there's no literal statusline -- the real
equivalent is configuring which live metrics appear in the dashboard's
status strips. Reads/writes a real persisted config (statusline_store.py,
same JSON-file pattern as cron_store.py/skills_store.py) that the frontend
actually reads, not a stub.
"""
from __future__ import annotations

from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent


class StatuslineSetupAgent(SpecializedAgent):
    """Configures which live metrics appear in the dashboard's status strips."""

    def __init__(self, settings):
        super().__init__(settings, "Statusline Setup Agent", "statusline-setup")
        self.capabilities.update({
            "description": "Configures which live metrics appear in Billion's dashboard status strips (the real equivalent of a CLI statusline here)",
            "confidence": 0.9,
            "specializations": ["dashboard-configuration", "status-display"],
            "tools": ["statusline-store"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "get-config")

        # Deferred import -- keeps this agent module free of a hard
        # dependency on the backend package layout at import time.
        from statusline_store import statusline_store, VALID_METRICS

        if task_type in ("get-config", "query"):
            cfg = statusline_store.get()
            return {
                "success": True,
                "task_type": "get-config",
                "metrics": cfg.metrics,
                "refresh_ms": cfg.refresh_ms,
                "valid_metrics": sorted(VALID_METRICS),
            }

        if task_type == "set-config":
            metrics = task_data.get("metrics")
            refresh_ms = task_data.get("refresh_ms")
            try:
                cfg = statusline_store.set(metrics=metrics, refresh_ms=refresh_ms)
            except ValueError as e:
                return {"success": False, "error": str(e)}
            return {
                "success": True,
                "task_type": "set-config",
                "metrics": cfg.metrics,
                "refresh_ms": cfg.refresh_ms,
            }

        return {"success": False, "error": f"Unknown task type '{task_type}' for statusline-setup agent"}
