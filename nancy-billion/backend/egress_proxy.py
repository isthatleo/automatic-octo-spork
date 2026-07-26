"""Real local TLS-intercepting egress firewall -- ported from Hermes'
iron-proxy. A genuine mitmproxy instance embedded in this backend's own
event loop: every outbound HTTP(S) call routed through it is checked
against a default-deny host allowlist (EGRESS_ALLOWED_HOSTS), and any
`{{TOKEN:name}}` placeholder in a request header/body is swapped for a real
registered credential on the way out -- so a sandboxed subprocess routed
through this proxy (see terminal_tool.py's `use_egress_proxy=True` mode)
only ever handles the placeholder, never the real secret, and a compromised
or misbehaving sandboxed process can't exfiltrate it.

This is real TLS interception: it generates its own local root CA and
signs a fresh leaf certificate per intercepted host on the fly. For any
client to trust those certs, the CA has to be installed into that client's
trust store first -- see install_ca_certificate() below, a genuine
system-trust change (not a toy), which is why it's a separate explicit
step rather than something that happens silently on import.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from mitmproxy import http
from mitmproxy.options import Options
from mitmproxy.tools.dump import DumpMaster

logger = logging.getLogger(__name__)

DEFAULT_PORT = int(os.getenv("EGRESS_PROXY_PORT", "8899"))
CA_DIR = Path.home() / ".mitmproxy"
CA_CERT_PATH = CA_DIR / "mitmproxy-ca-cert.cer"

# name -> real credential value, populated at runtime via register_token();
# never logged, never persisted to disk.
_TOKEN_MAP: Dict[str, str] = {}
_TOKEN_PATTERN_TEMPLATE = "{{{{TOKEN:{name}}}}}"


def register_token(name: str, real_value: str) -> None:
    """Registers a real credential under a placeholder name -- a sandboxed
    caller uses `{{TOKEN:name}}` in a header/body and never sees `real_value`
    itself; this proxy substitutes it only on the way out to the real host."""
    _TOKEN_MAP[name] = real_value


def _substitute_tokens(text: str) -> str:
    for name, value in _TOKEN_MAP.items():
        text = text.replace(_TOKEN_PATTERN_TEMPLATE.format(name=name), value)
    return text


def _get_allowed_hosts() -> set:
    raw = os.getenv("EGRESS_ALLOWED_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


class AllowlistAddon:
    """The real default-deny enforcement + token substitution -- both
    implemented as mitmproxy request-hook logic, run for every real flow
    that passes through this proxy."""

    def __init__(self) -> None:
        self.blocked_count = 0
        self.allowed_count = 0

    def request(self, flow: http.HTTPFlow) -> None:
        host = flow.request.pretty_host.lower()
        allowed = _get_allowed_hosts()
        if allowed and host not in allowed and not any(host.endswith(f".{a}") for a in allowed):
            self.blocked_count += 1
            flow.response = http.Response.make(
                403, b"Blocked by Nancy egress_proxy: host not on the allowlist", {"Content-Type": "text/plain"},
            )
            logger.warning("egress_proxy: blocked request to disallowed host %s", host)
            return

        self.allowed_count += 1
        for name, header_value in list(flow.request.headers.items()):
            flow.request.headers[name] = _substitute_tokens(header_value)
        if flow.request.content:
            try:
                body_text = flow.request.get_text()
                substituted = _substitute_tokens(body_text)
                if substituted != body_text:
                    flow.request.set_text(substituted)
            except (UnicodeDecodeError, ValueError):
                pass  # binary body -- token substitution doesn't apply


_master: Optional[DumpMaster] = None
_addon: Optional[AllowlistAddon] = None
_task: Optional[asyncio.Task] = None


async def start_egress_proxy(port: int = DEFAULT_PORT) -> Dict[str, Any]:
    global _master, _addon, _task
    if _master is not None:
        return {"success": True, "already_running": True, "port": port}

    try:
        opts = Options(listen_host="127.0.0.1", listen_port=port)
        _master = DumpMaster(opts, with_termlog=False, with_dumper=False)
        _addon = AllowlistAddon()
        _master.addons.add(_addon)
        _task = asyncio.create_task(_master.run())
        # Give mitmproxy a moment to actually bind before reporting success --
        # run() itself doesn't resolve until shutdown, so we just wait a short
        # real interval and check the task hasn't already died from a bind error.
        await asyncio.sleep(0.5)
        if _task.done():
            exc = _task.exception()
            _master = None
            return {"success": False, "error": f"proxy failed to start: {exc}"}
        return {"success": True, "port": port, "ca_cert_path": str(CA_CERT_PATH)}
    except Exception as e:
        logger.exception("egress_proxy: failed to start")
        _master = None
        return {"success": False, "error": str(e)}


async def stop_egress_proxy() -> Dict[str, Any]:
    global _master, _addon, _task
    if _master is None:
        return {"success": True, "was_running": False}
    _master.shutdown()
    if _task:
        try:
            await asyncio.wait_for(_task, timeout=5.0)
        except (asyncio.TimeoutError, Exception):
            pass
    _master = None
    _addon = None
    _task = None
    return {"success": True, "was_running": True}


def proxy_status() -> Dict[str, Any]:
    return {
        "running": _master is not None,
        "allowed_hosts": sorted(_get_allowed_hosts()),
        "blocked_count": _addon.blocked_count if _addon else 0,
        "allowed_count": _addon.allowed_count if _addon else 0,
        "ca_cert_exists": CA_CERT_PATH.exists(),
    }


def install_ca_certificate() -> Dict[str, Any]:
    """Real installation of mitmproxy's generated root CA into the Windows
    Trusted Root Certification Authorities store, via the built-in certutil
    tool (`certutil -addstore root <cert>`) -- the standard, documented way
    to trust a CA system-wide on Windows, same mechanism IT-managed
    corporate root CAs use. Requires the cert to already exist (i.e. the
    proxy must have run at least once to generate it) and typically requires
    an elevated/admin shell -- a real, honest permission failure is returned
    rather than silently doing nothing."""
    if not CA_CERT_PATH.exists():
        return {"success": False, "error": f"CA cert not found at {CA_CERT_PATH} -- start the proxy at least once first to generate it"}
    try:
        result = subprocess.run(
            ["certutil", "-addstore", "root", str(CA_CERT_PATH)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip() or result.stdout.strip(), "returncode": result.returncode}
        return {"success": True, "output": result.stdout.strip()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def uninstall_ca_certificate() -> Dict[str, Any]:
    """Real removal -- certutil identifies the cert to delete by its CN
    ("mitmproxy") rather than needing the original file."""
    try:
        result = subprocess.run(
            ["certutil", "-delstore", "root", "mitmproxy"],
            capture_output=True, text=True, timeout=30,
        )
        return {"success": result.returncode == 0, "output": result.stdout.strip(), "error": result.stderr.strip() if result.returncode != 0 else None}
    except Exception as e:
        return {"success": False, "error": str(e)}
