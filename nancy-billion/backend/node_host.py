"""Real paired-node dispatch -- this backend's client side for talking to a
node_agent_stub.py running on a second, paired machine. Every dispatched
action is gated by approval_policy.py's allow-once/allow-always/deny engine
first (falling back to a fresh Telegram approval when no policy exists yet),
so a second machine can be driven remotely without every single command
requiring a fresh prompt, while still refusing anything novel or wrapped.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

NODES_STORE_PATH = Path(__file__).parent / "data" / "nodes.json"


def _load_nodes() -> Dict[str, Dict[str, Any]]:
    if not NODES_STORE_PATH.exists():
        return {}
    try:
        return json.loads(NODES_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_nodes(nodes: Dict[str, Dict[str, Any]]) -> None:
    NODES_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    NODES_STORE_PATH.write_text(json.dumps(nodes, indent=2), encoding="utf-8")


def register_node(node_id: str, base_url: str, shared_secret: str) -> None:
    nodes = _load_nodes()
    nodes[node_id] = {"base_url": base_url.rstrip("/"), "shared_secret": shared_secret}
    _save_nodes(nodes)
    logger.info("node_host: registered node %r at %s", node_id, base_url)


def list_nodes() -> Dict[str, Dict[str, Any]]:
    # Never expose a node's shared secret back out through this listing.
    return {nid: {"base_url": cfg["base_url"]} for nid, cfg in _load_nodes().items()}


def remove_node(node_id: str) -> bool:
    nodes = _load_nodes()
    if node_id in nodes:
        del nodes[node_id]
        _save_nodes(nodes)
        return True
    return False


async def _call_node(node_id: str, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    nodes = _load_nodes()
    node = nodes.get(node_id)
    if node is None:
        return {"success": False, "error": f"node {node_id!r} is not registered"}
    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            resp = await client.post(
                f"{node['base_url']}{path}", json=payload, headers={"X-Node-Secret": node["shared_secret"]},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning("node_host: call to node %r%s failed: %s", node_id, path, e)
        return {"success": False, "error": str(e)}


async def dispatch_command(node_id: str, command: str, cwd: Optional[str] = None, timeout: float = 30.0) -> Dict[str, Any]:
    """The real gated dispatch path: checks approval_policy first; only
    consults Telegram for a fresh approval when there's no stored policy
    (or the command is a shell-wrapper invocation, which never uses a
    stored policy -- see approval_policy.is_wrapped_command)."""
    import approval_policy

    decision = approval_policy.check_policy(node_id, command)
    if decision == "deny":
        return {"success": False, "error": "denied by stored policy"}
    if decision is None:
        from telegram_bot import telegram_notifier
        wrapped_note = " (shell-wrapper command -- always requires fresh approval)" if approval_policy.is_wrapped_command(command) else ""
        approved = await telegram_notifier.request_approval(
            f"Nancy wants to run on node '{node_id}':\n\n{command}{wrapped_note}", timeout=120.0,
        )
        if not approved:
            return {"success": False, "error": "user did not approve this node command"}
        # A single approval here is an allow_once by construction -- the
        # user can separately call set_node_policy() to make it sticky.

    return await _call_node(node_id, "/execute_command", {"command": command, "cwd": cwd, "timeout": timeout})


def set_node_policy(node_id: str, command: str, decision: str) -> None:
    import approval_policy
    approval_policy.set_policy(node_id, command, decision)  # type: ignore[arg-type]


async def dispatch_read_file(node_id: str, path: str) -> Dict[str, Any]:
    return await _call_node(node_id, "/read_file", {"path": path})


async def dispatch_screenshot(node_id: str) -> Dict[str, Any]:
    return await _call_node(node_id, "/screenshot", {})


async def dispatch_open_application(node_id: str, target: str, args: Optional[list] = None) -> Dict[str, Any]:
    return await _call_node(node_id, "/open_application", {"target": target, "args": args})


async def check_node_health(node_id: str) -> Dict[str, Any]:
    nodes = _load_nodes()
    node = nodes.get(node_id)
    if node is None:
        return {"success": False, "error": f"node {node_id!r} is not registered"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{node['base_url']}/health")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        return {"success": False, "error": str(e)}
