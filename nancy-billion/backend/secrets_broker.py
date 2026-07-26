"""Real secret-reference resolution -- ported in spirit from Hermes' Bitwarden/
1Password secret sources and OpenClaw's 1Password/Vault brokers. Lets any
future credentialed feature accept a `bw://`, `op://`, or `vault://` reference
in its config instead of a raw value, so a real secret never has to sit in
plaintext in `.env`.

Same graceful-degrade idiom as every other credential in this codebase
(llm.py's `os.getenv("X_API_KEY")` construction-time checks): a broker that
isn't configured, or a reference that fails to resolve, returns None and logs
a warning -- it never raises, so a caller can always fall back to treating the
value as absent, exactly like a missing API key today.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# In-process cache so a resolved secret isn't re-shelled-out-for on every use
# within the same run -- cleared only by restart, matching how every other
# credential in this codebase is read once at construction time, not per-call.
_CACHE: dict[str, Optional[str]] = {}


async def _run_cli(cmd: list[str], timeout: int = 15) -> Optional[str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("secrets_broker: %s timed out", cmd[0])
            return None
        if proc.returncode != 0:
            logger.warning("secrets_broker: %s failed: %s", cmd[0], stderr_b.decode(errors="replace").strip())
            return None
        return stdout_b.decode(errors="replace").strip()
    except FileNotFoundError:
        logger.warning("secrets_broker: %s CLI not found on PATH", cmd[0])
        return None
    except Exception as e:
        logger.warning("secrets_broker: %s errored: %s", cmd[0], e)
        return None


async def _resolve_bitwarden(item: str, field: str) -> Optional[str]:
    """bw://<item-name-or-id>/<field> -- requires BW_SESSION (from `bw unlock
    --raw`, exported by the user beforehand; this broker never attempts to
    unlock the vault itself)."""
    if not os.getenv("BW_SESSION"):
        logger.warning("secrets_broker: BW_SESSION not set -- cannot resolve bw:// reference")
        return None
    bw_path = os.getenv("BITWARDEN_CLI_PATH", "bw")
    return await _run_cli([bw_path, "get", field, item])


async def _resolve_onepassword(vault: str, item: str, field: str) -> Optional[str]:
    """op://<vault>/<item>/<field> -- requires either an unlocked `op` CLI
    session or OP_SERVICE_ACCOUNT_TOKEN in the environment (the `op` CLI reads
    that env var itself when present)."""
    op_path = os.getenv("OP_CLI_PATH", "op")
    return await _run_cli([op_path, "read", f"op://{vault}/{item}/{field}"])


async def _resolve_vault(path: str, field: str) -> Optional[str]:
    """vault://<path>#<field> -- a real HashiCorp Vault KV-v2 read via its
    HTTP API (no extra dependency -- plain REST over `httpx`, already a
    project dependency via web_tool.py)."""
    addr = os.getenv("VAULT_ADDR")
    token = os.getenv("VAULT_TOKEN")
    if not addr or not token:
        logger.warning("secrets_broker: VAULT_ADDR/VAULT_TOKEN not set -- cannot resolve vault:// reference")
        return None
    import httpx
    url = f"{addr.rstrip('/')}/v1/secret/data/{path.lstrip('/')}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"X-Vault-Token": token})
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("data", {}).get(field)
    except Exception as e:
        logger.warning("secrets_broker: vault read failed for %s: %s", path, e)
        return None


async def resolve_secret(ref: Optional[str]) -> Optional[str]:
    """Resolves a secret reference. A plain string with no recognized scheme
    is treated as a literal env var NAME and passed through `os.getenv` --
    this is deliberate, so every existing `os.getenv("X_API_KEY")` call site
    can be upgraded to `await resolve_secret(os.getenv("X_API_KEY_REF", "X_API_KEY"))`
    without changing behavior for anyone who hasn't adopted bw://op://vault://."""
    if not ref:
        return None
    if ref in _CACHE:
        return _CACHE[ref]

    value: Optional[str]
    try:
        parsed = urlparse(ref)
        if parsed.scheme == "bw":
            item = parsed.netloc or parsed.path.strip("/").split("/")[0]
            field = parsed.path.strip("/").split("/")[-1] if "/" in ref.split("://", 1)[-1] else "password"
            value = await _resolve_bitwarden(item, field)
        elif parsed.scheme == "op":
            parts = [p for p in parsed.path.split("/") if p]
            vault = parsed.netloc
            item = parts[0] if parts else ""
            field = parts[1] if len(parts) > 1 else "password"
            value = await _resolve_onepassword(vault, item, field)
        elif parsed.scheme == "vault":
            path, _, field = ref[len("vault://"):].partition("#")
            value = await _resolve_vault(path, field or "value")
        else:
            # Not a recognized scheme -- treat as a literal env var name.
            value = os.getenv(ref)
            if value is None:
                logger.warning("secrets_broker: env var %r is not set", ref)
    except Exception as e:
        logger.warning("secrets_broker: failed to resolve %r: %s", ref, e)
        value = None

    _CACHE[ref] = value
    return value


def resolve_secret_sync(ref: Optional[str]) -> Optional[str]:
    """Sync convenience wrapper for construction-time use (module import,
    __init__) where there's no running event loop yet -- mirrors how llm.py
    reads API keys synchronously at construction time."""
    if not ref:
        return None
    if ref in _CACHE:
        return _CACHE[ref]
    parsed = urlparse(ref)
    if parsed.scheme not in ("bw", "op", "vault"):
        return os.getenv(ref)
    try:
        return asyncio.run(resolve_secret(ref))
    except RuntimeError:
        # Already inside a running loop (e.g. imported during an async
        # startup hook) -- can't nest asyncio.run; fall back to treating it
        # as unresolved rather than deadlocking. Callers in this situation
        # should use the async resolve_secret directly instead.
        logger.warning("secrets_broker: cannot sync-resolve %r from within a running event loop", ref)
        return None
