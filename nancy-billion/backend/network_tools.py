"""Real network diagnostic utilities -- ping, TCP port checks, DNS
resolution, public IP lookup, a LAN ping sweep, traceroute, and this
container's own interfaces. Genuine network I/O throughout (real
ICMP-via-subprocess ping, real TCP connects, real DNS resolution, a real
outbound HTTP call for the public IP) -- nothing simulated. Every function
here degrades to {"success": False, "error": ...} rather than raising, same
convention as the rest of the tool layer.
"""
from __future__ import annotations

import asyncio
import ipaddress
import platform
import socket
import time
from typing import Any, Dict, List

import httpx
import psutil

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
    {
        "name": "dns_lookup",
        "description": "Real DNS resolution of a hostname to its IP address(es).",
        "input_schema": {
            "type": "object",
            "properties": {"host": {"type": "string"}},
            "required": ["host"],
        },
    },
    {
        "name": "get_public_ip",
        "description": "Real lookup of this deployment's current public (WAN) IP address.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "lan_scan",
        "description": (
            "Real ping sweep of a LAN subnet (e.g. '192.168.1.0/24') to discover which "
            "hosts currently respond -- useful for finding a device's IP to register with "
            "register_presence_device. Capped at a /24 (254 hosts) to keep it fast."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subnet": {"type": "string", "description": "CIDR, e.g. '192.168.1.0/24'."},
            },
            "required": ["subnet"],
        },
    },
    {
        "name": "traceroute",
        "description": "Real traceroute showing the network hops between this server and a host.",
        "input_schema": {
            "type": "object",
            "properties": {"host": {"type": "string"}},
            "required": ["host"],
        },
    },
    {
        "name": "get_network_interfaces",
        "description": (
            "Real network interfaces and their IP addresses on THIS server (the backend's own "
            "host/container, not necessarily your personal device)."
        ),
        "input_schema": {"type": "object", "properties": {}},
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


async def dns_lookup(host: str) -> Dict[str, Any]:
    try:
        loop = asyncio.get_event_loop()
        infos = await loop.run_in_executor(None, lambda: socket.getaddrinfo(host, None))
        ips = sorted({info[4][0] for info in infos})
        return {"success": True, "host": host, "addresses": ips}
    except socket.gaierror as e:
        return {"success": False, "error": f"Could not resolve {host}: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_public_ip() -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://api.ipify.org?format=json")
            resp.raise_for_status()
            return {"success": True, "public_ip": resp.json().get("ip")}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def lan_scan(subnet: str) -> Dict[str, Any]:
    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError as e:
        return {"success": False, "error": f"Invalid subnet '{subnet}': {e}"}
    if network.num_addresses > 256:
        return {"success": False, "error": "Subnet too large -- pass a /24 (max 256 addresses) or smaller."}

    hosts = list(network.hosts())
    semaphore = asyncio.Semaphore(32)

    async def _check(ip: str) -> Dict[str, Any]:
        async with semaphore:
            result = await ping_host(ip, count=1)
            return {"ip": ip, "reachable": bool(result.get("success") and result.get("reachable"))}

    results = await asyncio.gather(*(_check(str(ip)) for ip in hosts))
    live = [r["ip"] for r in results if r["reachable"]]
    return {"success": True, "subnet": str(network), "scanned": len(hosts), "live_hosts": live}


async def traceroute(host: str) -> Dict[str, Any]:
    is_windows = platform.system() == "Windows"
    cmd = ["tracert", "-h", "20", host] if is_windows else ["traceroute", "-m", "20", host]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, _ = await asyncio.wait_for(proc.communicate(), timeout=45)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"success": False, "error": "Traceroute timed out."}
        return {"success": True, "host": host, "output": stdout_b.decode(errors="replace")[-3000:]}
    except FileNotFoundError:
        return {"success": False, "error": "traceroute/tracert binary not available on this server."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_network_interfaces() -> Dict[str, Any]:
    try:
        interfaces: Dict[str, List[Dict[str, Any]]] = {}
        for name, addrs in psutil.net_if_addrs().items():
            interfaces[name] = [
                {"family": str(a.family), "address": a.address}
                for a in addrs
                if a.family in (socket.AF_INET, socket.AF_INET6)
            ]
        return {"success": True, "interfaces": interfaces}
    except Exception as e:
        return {"success": False, "error": str(e)}
