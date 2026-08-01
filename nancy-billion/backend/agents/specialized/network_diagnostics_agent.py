"""
Network Diagnostics Agent for Nancy/Billion.
Real network checks -- reuses network_tools.py's actual ICMP ping, TCP port
probe, DNS resolution, and public-IP lookup rather than fabricating results.
"""
from __future__ import annotations

from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent


class NetworkDiagnosticsAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Network Diagnostics Agent", "network-diagnostics")
        self.capabilities.update({
            "description": "Real network diagnostics: ping, DNS resolution, TCP port checks, public IP lookup",
            "confidence": 0.85,
            "specializations": ["ping", "dns", "port-scanning", "connectivity"],
            "tools": ["icmp-ping", "tcp-connect", "dns-resolve"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        import network_tools as nt

        if task_type == "ping":
            return await nt.ping_host(task_data.get("host", ""), task_data.get("count", 4))
        if task_type == "dns_lookup":
            return await nt.dns_lookup(task_data.get("host", ""))
        if task_type == "port_check":
            return await nt.check_port_open(
                task_data.get("host", ""), int(task_data.get("port", 0)),
                float(task_data.get("timeout_s", 5.0)),
            )
        if task_type == "public_ip":
            return await nt.get_public_ip()
        if task_type == "status":
            return {"success": True, "status": "ready", "capabilities": self.capabilities["specializations"]}
        return await self._general(task_data)

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I run real network diagnostics -- ping, dns_lookup, port_check, or public_ip."
        )}
