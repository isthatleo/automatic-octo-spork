"""Real IP/URL classification for SSRF defense -- ported from OpenClaw's
packages/net-policy (ip.ts), which is more thorough than a bare
ipaddress.is_private check: it also catches CGNAT (100.64.0.0/10), the
RFC 2544 benchmark range, known cloud-metadata addresses, and IPv6
addresses that smuggle a private IPv4 inside via 6to4/Teredo/IPv4-mapped/
IPv4-compatible encoding -- which a naive check on the outer IPv6 address
alone would miss entirely (e.g. ::ffff:169.254.169.254 looks like an
ordinary global IPv6 address unless you unwrap it first).

Single source of truth for "should any tool ever let an LLM-controlled
call reach this address" -- used by web_tool.py's fetch_url today.
terminal_tool.py doesn't need this: a shell command can do far more than
touch the network, so it's gated by its own allowlist/Telegram-approval
split instead, a stronger and more general control for that risk tier.
computer_use_tool.py makes no network calls at all (local input/screen
only), so it has nothing for this module to check.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Optional, Union
from urllib.parse import urlsplit, urlunsplit

IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]

_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_BENCHMARK = ipaddress.ip_network("198.18.0.0/15")  # RFC 2544
_IPV4_MAPPED = ipaddress.ip_network("::ffff:0:0/96")
_SIXTOFOUR = ipaddress.ip_network("2002::/16")
_TEREDO = ipaddress.ip_network("2001::/32")
_KNOWN_METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),  # AWS/GCP/Azure/DigitalOcean instance metadata
    ipaddress.ip_address("fd00:ec2::254"),    # AWS IMDSv2, IPv6
}


def _unwrap_embedded_ipv4(addr: ipaddress.IPv6Address) -> Optional[ipaddress.IPv4Address]:
    """Extracts a real IPv4 address smuggled inside an IPv6 address, so a
    check that only classifies the outer IPv6 address can't be bypassed by
    wrapping a blocked IPv4 target in one of these encodings."""
    packed = addr.packed
    try:
        if addr in _IPV4_MAPPED:
            return ipaddress.IPv4Address(packed[12:16])
        if addr in _SIXTOFOUR:
            return ipaddress.IPv4Address(packed[2:6])
        if addr in _TEREDO:
            # Teredo: client IPv4 is the last 4 bytes, bitwise-obfuscated.
            return ipaddress.IPv4Address(bytes(b ^ 0xFF for b in packed[12:16]))
        # IPv4-compatible ::/96 (deprecated, still parseable) -- anything
        # whose top 96 bits are zero and isn't ::/:: 1 itself.
        if int.from_bytes(packed[:12], "big") == 0 and addr not in (ipaddress.ip_address("::"), ipaddress.ip_address("::1")):
            return ipaddress.IPv4Address(packed[12:16])
    except Exception:
        return None
    return None


def is_blocked_ip(ip: IPAddress) -> bool:
    """True if `ip` (already resolved) must never be reached by an
    LLM-controlled tool call."""
    if ip in _KNOWN_METADATA_IPS:
        return True
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        return True
    if isinstance(ip, ipaddress.IPv4Address) and (ip in _CGNAT or ip in _BENCHMARK):
        return True
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = _unwrap_embedded_ipv4(ip)
        if embedded is not None and is_blocked_ip(embedded):
            return True
    return False


def is_blocked_host(hostname: str) -> bool:
    """Resolves `hostname` and checks every returned address. Fails
    closed: a hostname that won't resolve is refused, not allowed through."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True
    return any(is_blocked_ip(ipaddress.ip_address(info[4][0])) for info in infos)


def redact_url_for_logging(url: str) -> str:
    """Strips embedded userinfo (user:pass@host) from a URL before it's
    ever written to a log line -- a credential embedded in a URL should
    never end up in application logs."""
    parts = urlsplit(url)
    if not parts.username and not parts.password:
        return url
    netloc = parts.hostname or ""
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
