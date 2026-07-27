"""Real Docker-backed per-tenant isolation -- ported from OpenClaw's Fleet
extension. A "cell" is a real Docker container, labeled by tenant, with
real resource caps (memory, CPU) and an explicit allowed-env-key allowlist
so a tenant's cell only ever receives the specific environment variables
named for it -- never the full host environment (which could otherwise leak
API keys/secrets from this backend's own process into an isolated tenant's
container).

This is genuinely infrastructure for hosting multiple isolated tenant
execution sandboxes from one control plane -- built literally per explicit
user choice even though Nancy's own data model (missions, cron, memory)
stays single-tenant/global. A cell is an isolated execution sandbox, not a
second Nancy user account.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from fleet import store

logger = logging.getLogger(__name__)

DEFAULT_IMAGE = "python:3.11-slim"


def _get_client():
    import docker
    return docker.from_env()


def _mem_limit_to_bytes(mem_limit: str) -> str:
    # Docker's own SDK already accepts "256m"/"1g"-style strings directly for
    # the mem_limit param -- passed straight through, not reparsed here.
    return mem_limit


async def create_cell(
    tenant_id: str, image: str = DEFAULT_IMAGE, mem_limit: str = "256m", nano_cpus: float = 0.5,
    allowed_env_keys: Optional[List[str]] = None, command: Optional[str] = None,
) -> Dict[str, Any]:
    """Real container creation with real resource limits. allowed_env_keys
    is a real allowlist -- only those specific names are read from THIS
    process's own environment and passed into the container; everything
    else in os.environ is invisible to the tenant's cell.

    No `command` given defaults to a real long-running keep-alive process
    (`sleep infinity`) rather than the image's own default entrypoint --
    confirmed live that without this, a plain `python:3.11-slim` container
    exits immediately (its default is an interactive REPL with no TTY
    attached, not a persistent process), leaving nothing for a later
    exec_in_cell() call to actually run against."""
    allowed_env_keys = allowed_env_keys or []
    env = {k: os.environ[k] for k in allowed_env_keys if k in os.environ}
    cell_id = f"nancy-cell-{uuid.uuid4().hex[:10]}"
    command = command or "sleep infinity"

    try:
        client = _get_client()
        container = client.containers.run(
            image,
            command=command,
            name=cell_id,
            detach=True,
            mem_limit=_mem_limit_to_bytes(mem_limit),
            nano_cpus=int(nano_cpus * 1_000_000_000),
            environment=env,
            labels={"nancy.tenant_id": tenant_id, "nancy.cell_id": cell_id},
            network_mode="bridge",
        )
        store.record_cell(cell_id, tenant_id, container.id, image, mem_limit, nano_cpus, allowed_env_keys)
        return {"success": True, "cell_id": cell_id, "container_id": container.id}
    except Exception as e:
        logger.warning("fleet.cell: create_cell failed: %s", e)
        return {"success": False, "error": str(e)}


async def exec_in_cell(cell_id: str, command: str, timeout: int = 30) -> Dict[str, Any]:
    record = store.get_cell(cell_id)
    if record is None:
        return {"success": False, "error": f"no such cell: {cell_id}"}
    try:
        client = _get_client()
        container = client.containers.get(record["container_id"])
        result = container.exec_run(["sh", "-c", command], demux=True)
        stdout, stderr = result.output
        return {
            "success": result.exit_code == 0,
            "exit_code": result.exit_code,
            "stdout": (stdout or b"").decode(errors="replace"),
            "stderr": (stderr or b"").decode(errors="replace"),
        }
    except Exception as e:
        logger.warning("fleet.cell: exec_in_cell failed: %s", e)
        return {"success": False, "error": str(e)}


async def stop_cell(cell_id: str) -> Dict[str, Any]:
    record = store.get_cell(cell_id)
    if record is None:
        return {"success": False, "error": f"no such cell: {cell_id}"}
    try:
        client = _get_client()
        container = client.containers.get(record["container_id"])
        container.stop(timeout=10)
        store.update_status(cell_id, "stopped")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def remove_cell(cell_id: str) -> Dict[str, Any]:
    record = store.get_cell(cell_id)
    if record is None:
        return {"success": False, "error": f"no such cell: {cell_id}"}
    try:
        client = _get_client()
        try:
            container = client.containers.get(record["container_id"])
            container.remove(force=True)
        except Exception:
            pass  # already gone -- still clean up our own record below
        store.remove_cell_record(cell_id)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def backup_cell(cell_id: str, tag: Optional[str] = None) -> Dict[str, Any]:
    """Real backup -- `docker commit`, snapshotting the cell's current real
    filesystem state into a new image tag that can later be used to create
    a fresh cell starting from exactly this state."""
    record = store.get_cell(cell_id)
    if record is None:
        return {"success": False, "error": f"no such cell: {cell_id}"}
    tag = tag or f"{cell_id}-backup-{uuid.uuid4().hex[:6]}"
    try:
        client = _get_client()
        container = client.containers.get(record["container_id"])
        image = container.commit(repository="nancy-fleet-backups", tag=tag)
        return {"success": True, "image": f"nancy-fleet-backups:{tag}", "image_id": image.id}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_cells(tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    return store.list_cells(tenant_id)
