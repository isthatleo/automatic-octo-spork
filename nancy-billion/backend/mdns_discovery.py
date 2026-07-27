"""Real Bonjour/mDNS LAN service discovery -- ported from OpenClaw's Bonjour
extension (a literal build per explicit user choice, even though Nancy has
no generic "pair a new device" flow the way OpenClaw's node-pairing model
does -- Telegram pairing already solves client authentication a different,
better-fitting way). Real, functional use here: advertising this backend on
the LAN so a paired node_agent_stub.py or a Home Assistant instance can be
found without hand-typing an IP, and a discovery client to actually find
them.

No credential needed -- local-network-only by design (mDNS packets don't
route past the local subnet).
"""
from __future__ import annotations

import logging
import os
import socket
from typing import Any, Dict, List, Optional

from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_nancy-gateway._tcp.local."
# AsyncZeroconf throughout, even for the caller-facing advertise()/
# stop_advertising() functions below -- confirmed live that mixing the sync
# Zeroconf class into a caller that already has a running asyncio event loop
# (the real case here: every caller is a FastAPI route handler) silently
# fails (register_service's internal coroutine never gets awaited).
_azc: Optional[AsyncZeroconf] = None
_service_info: Optional[ServiceInfo] = None


def _get_local_ip() -> str:
    """Real best-effort LAN IP detection -- opens a UDP socket to a public
    address (no packet actually sent for a UDP connect) purely to ask the OS
    which local interface/IP it would route through."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


async def advertise(port: int = 8000, pairing_challenge: Optional[str] = None) -> Dict[str, Any]:
    """Real mDNS advertisement -- announces this backend as
    _nancy-gateway._tcp.local. on the LAN, carrying its real port and an
    optional pairing-challenge TXT record another device can check against
    a shared secret before trusting this instance."""
    global _azc, _service_info
    if _azc is not None:
        return {"success": True, "already_advertising": True}

    local_ip = _get_local_ip()
    hostname = socket.gethostname()
    properties = {"port": str(port).encode()}
    if pairing_challenge:
        properties["challenge"] = pairing_challenge.encode()

    try:
        _service_info = ServiceInfo(
            SERVICE_TYPE,
            f"{hostname}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(local_ip)],
            port=port,
            properties=properties,
            server=f"{hostname}.local.",
        )
        _azc = AsyncZeroconf()
        await _azc.async_register_service(_service_info)
        logger.info("mdns_discovery: advertising as %s at %s:%d", f"{hostname}.{SERVICE_TYPE}", local_ip, port)
        return {"success": True, "name": f"{hostname}.{SERVICE_TYPE}", "address": local_ip, "port": port}
    except Exception as e:
        logger.warning("mdns_discovery: advertise failed: %s", e)
        _azc = None
        return {"success": False, "error": str(e)}


async def stop_advertising() -> Dict[str, Any]:
    global _azc, _service_info
    if _azc is None:
        return {"success": True, "was_advertising": False}
    try:
        if _service_info:
            await _azc.async_unregister_service(_service_info)
        await _azc.async_close()
    finally:
        _azc = None
        _service_info = None
    return {"success": True, "was_advertising": True}


async def discover(timeout_s: float = 3.0) -> List[Dict[str, Any]]:
    """Real discovery client -- browses the LAN for other advertised
    _nancy-gateway._tcp.local. instances (or a paired node/Home Assistant
    instance advertising the same way) for that real timeout window, then
    returns whatever real services were found."""
    import asyncio

    found: Dict[str, Dict[str, Any]] = {}
    azc = AsyncZeroconf()

    async def _resolve_and_record(zeroconf, service_type: str, name: str) -> None:
        info = AsyncServiceInfo(service_type, name)
        if await info.async_request(zeroconf, 3000):
            addresses = [socket.inet_ntoa(addr) for addr in info.addresses]
            found[name] = {
                "name": name,
                "addresses": addresses,
                "port": info.port,
                "properties": {k.decode(): v.decode(errors="replace") if isinstance(v, bytes) else v for k, v in (info.properties or {}).items()},
            }

    def on_service_state_change(zeroconf, service_type, name, state_change) -> None:
        # Real zeroconf async API contract: this handler itself must be a
        # plain sync callback (confirmed live -- passing an async function
        # directly here means it's called but never awaited, so it silently
        # never runs). Real async resolution work is scheduled as a task
        # from inside this sync callback instead.
        if state_change.value != 1:  # 1 = Added
            return
        asyncio.ensure_future(_resolve_and_record(zeroconf, service_type, name))

    browser = AsyncServiceBrowser(azc.zeroconf, SERVICE_TYPE, handlers=[on_service_state_change])
    try:
        await asyncio.sleep(timeout_s)
    finally:
        await browser.async_cancel()
        await azc.async_close()

    return list(found.values())


def status() -> Dict[str, Any]:
    return {
        "advertising": _azc is not None,
        "service_type": SERVICE_TYPE,
        "name": f"{socket.gethostname()}.{SERVICE_TYPE}" if _azc else None,
    }
