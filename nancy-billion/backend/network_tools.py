"""Real network diagnostic utilities -- ping and TCP port checks, for
"is this host up" / "is this service listening" style requests. Genuine
network I/O (real ICMP-via-subprocess ping, real TCP connect attempts),
not simulated.
"""
from __future__ import annotations

import asyncio
import platform
import socket
import time
from typing import Any, Dict

NETWORK_TOOLS = [
    {
        "name": "ping_host",
        "description": "Real ICMP ping to check if a host is reachable and measure round-trip latency.",
        "input_schema": {
            "type": "object",
            "properties": {
                "host": {"type": "string"},
                "count": {"type": "integer", "description": "Number of pings, default 4."},
            },
            "required": ["host"],
        },
    },
    {
        "name": "check_port_open",
        "description": "Real TCP connection attempt to check whether a specific port is open/listening on a host.",
        "input_schema": {
            "type": "object",
            "properties": {"host": {"type": "string"}, "port": {"type": "integer"}},
            "required": ["host", "port"],
        },
    },
]


async def ping_host(host: str, count: int = 4) -> Dict[str, Any]:
    count = max(1, min(count or 4, 10))
    is_windows = platform.system() == "Windows"
    cmd = ["ping", "-n" if is_windows else "-c", str(count), host]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, _ = await asyncio.wait_for(proc.communicate(), timeout=count * 3 + 5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"success": False, "error": "Ping timed out."}
        output = stdout_b.decode(errors="replace")
        reachable = proc.returncode == 0
        return {"success": True, "host": host, "reachable": reachable, "output": output[-1200:]}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def check_port_open(host: str, port: int, timeout_s: float = 5.0) -> Dict[str, Any]:
    start = time.monotonic()
    try:
        conn = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(conn, timeout=timeout_s)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return {"success": True, "host": host, "port": port, "open": True, "latency_ms": round((time.monotonic() - start) * 1000, 1)}
    except (asyncio.TimeoutError, ConnectionRefusedError, socket.gaierror, OSError) as e:
        return {"success": True, "host": host, "port": port, "open": False, "error": str(e)}
