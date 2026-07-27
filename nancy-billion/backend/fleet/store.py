"""Real persisted cell metadata -- same JSON-file XStore pattern as every
other store in this codebase (missions_store.py is the reference). Docker
itself is the source of truth for whether a container actually exists; this
store is Nancy's own record of which cells belong to which tenant, so
listing/backup/restore operations don't need the daemon running just to
answer "what cells exist."
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

STORE_PATH = Path(__file__).parent.parent / "data" / "fleet_cells.json"


def _load() -> Dict[str, Dict[str, Any]]:
    if not STORE_PATH.exists():
        return {}
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: Dict[str, Dict[str, Any]]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def record_cell(cell_id: str, tenant_id: str, container_id: str, image: str, mem_limit: str, nano_cpus: float, allowed_env_keys: List[str]) -> None:
    data = _load()
    data[cell_id] = {
        "cell_id": cell_id, "tenant_id": tenant_id, "container_id": container_id, "image": image,
        "mem_limit": mem_limit, "nano_cpus": nano_cpus, "allowed_env_keys": allowed_env_keys,
        "created_at": time.time(), "status": "running",
    }
    _save(data)


def update_status(cell_id: str, status: str) -> None:
    data = _load()
    if cell_id in data:
        data[cell_id]["status"] = status
        _save(data)


def remove_cell_record(cell_id: str) -> None:
    data = _load()
    if cell_id in data:
        del data[cell_id]
        _save(data)


def get_cell(cell_id: str) -> Optional[Dict[str, Any]]:
    return _load().get(cell_id)


def list_cells(tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    cells = list(_load().values())
    if tenant_id is not None:
        cells = [c for c in cells if c["tenant_id"] == tenant_id]
    return cells
