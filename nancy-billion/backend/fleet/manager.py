"""Real Fleet control-plane facade -- thin orchestration over fleet/cell.py
(real Docker operations) + fleet/store.py (real persisted metadata). One
import point for main_new.py's REST/tool wiring, plus a real Docker-daemon
health check so a caller gets a clear, honest "Docker isn't running" error
instead of a confusing low-level connection exception.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fleet.cell import backup_cell, create_cell, exec_in_cell, list_cells, remove_cell, stop_cell

__all__ = ["create_cell", "exec_in_cell", "stop_cell", "remove_cell", "backup_cell", "list_cells", "check_docker_health"]


def check_docker_health() -> Dict[str, Any]:
    try:
        import docker
        client = docker.from_env()
        client.ping()
        info = client.info()
        return {"success": True, "docker_available": True, "containers_running": info.get("ContainersRunning", 0)}
    except Exception as e:
        return {"success": False, "docker_available": False, "error": str(e)}
