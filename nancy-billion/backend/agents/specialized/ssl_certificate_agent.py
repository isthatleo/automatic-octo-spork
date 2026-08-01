"""
SSL Certificate Agent for Nancy/Billion.
Real TLS handshake against a real host:port -- the actual certificate the
server presents right now (via Python's stdlib ssl module), never a
fabricated expiry date or issuer.
"""
from __future__ import annotations

import ssl
import socket
from datetime import datetime, timezone
from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent


class SslCertificateAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "SSL Certificate Agent", "ssl-certificate")
        self.capabilities.update({
            "description": "Real TLS certificate inspection (expiry, issuer, subject) via an actual handshake against the host",
            "confidence": 0.85,
            "specializations": ["tls-inspection", "certificate-expiry"],
            "tools": ["ssl", "socket"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "inspect":
            return self._inspect(task_data.get("host", ""), int(task_data.get("port", 443)))
        if task_type == "status":
            return {"success": True, "status": "ready"}
        return await self._general(task_data)

    def _inspect(self, host: str, port: int) -> Dict[str, Any]:
        host = host.strip()
        if not host:
            return {"success": False, "error": "host is required"}
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, port), timeout=10.0) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as tls:
                    cert = tls.getpeercert()
        except Exception as e:
            return {"success": False, "error": f"Could not complete a real TLS handshake with {host}:{port}: {e}"}

        not_after = cert.get("notAfter")
        not_before = cert.get("notBefore")
        expires_at = None
        days_remaining = None
        if not_after:
            expires_at = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            days_remaining = (expires_at - datetime.now(timezone.utc)).days

        subject = dict(x[0] for x in cert.get("subject", []))
        issuer = dict(x[0] for x in cert.get("issuer", []))
        san = [v for k, v in cert.get("subjectAltName", []) if k == "DNS"]

        return {
            "success": True,
            "host": host, "port": port,
            "subject_common_name": subject.get("commonName"),
            "issuer": issuer.get("organizationName") or issuer.get("commonName"),
            "valid_from": not_before,
            "valid_until": not_after,
            "days_remaining": days_remaining,
            "expiring_soon": days_remaining is not None and days_remaining < 30,
            "expired": days_remaining is not None and days_remaining < 0,
            "subject_alt_names": san[:20],
        }

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I inspect a real TLS certificate via an actual handshake -- give me a host and I'll tell you "
            "the real expiry date, issuer, and days remaining."
        )}
