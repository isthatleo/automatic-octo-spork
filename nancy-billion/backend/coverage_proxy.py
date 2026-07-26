"""Real outbound-call coverage reporting -- ported from OpenClaw's
debug-capture/coverage-proxy tool. Reuses egress_proxy.py's already-running
mitmproxy instance (same real TLS interception, not a second proxy) to
observe every real outbound host actually contacted during this session,
and cross-references it against which vendor integrations are configured
(providers/registry.py + channels/registry.py) to classify each one as:

- "captured": configured AND at least one real request to its host was
  observed this session.
- "uncovered": configured but its expected host was never observed --
  either that integration hasn't fired yet, or (the real audit value) it's
  somehow bypassing the proxy, which is worth knowing either way.

This is a network-audit tool, not a security gate -- it never blocks
anything (that's egress_proxy's allowlist), it only reports.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Set
from urllib.parse import urlparse

from mitmproxy import http

logger = logging.getLogger(__name__)

# Friendly name -> the real host each configured vendor/channel actually
# calls -- kept here (not derived automatically) since a vendor's client
# code may call a host that isn't obviously derivable from its module name.
_VENDOR_HOSTS: Dict[str, str] = {
    "brave": "api.search.brave.com",
    "tavily": "api.tavily.com",
    "fal": "queue.fal.run",
    "deepinfra": "api.deepinfra.com",
    "elevenlabs": "api.elevenlabs.io",
    "deepgram": "api.deepgram.com",
    "mem0": "api.mem0.ai",
    "supermemory": "api.supermemory.ai",
    "honcho": "api.honcho.dev",
    "hindsight": "api.hindsight.dev",
    "byterover": "api.byterover.dev",
    "openviking": "api.openviking.dev",
    "retaindb": "api.retaindb.com",
    "ntfy": urlparse(os.getenv("NTFY_SERVER", "https://ntfy.sh")).hostname or "ntfy.sh",
    "home_assistant": urlparse(os.getenv("HOME_ASSISTANT_URL", "")).hostname or "",
    "slack": "slack.com",
    "spotify": "api.spotify.com",
}


class CoverageAddon:
    """A second, independent addon added to the SAME running mitmproxy
    instance as egress_proxy.AllowlistAddon -- mitmproxy runs every
    registered addon's request() hook for each real flow, so this observes
    exactly the same real traffic without needing its own proxy."""

    def __init__(self) -> None:
        self.observed_hosts: Set[str] = set()
        self.request_log: List[Dict[str, Any]] = []

    def request(self, flow: http.HTTPFlow) -> None:
        host = flow.request.pretty_host.lower()
        self.observed_hosts.add(host)
        self.request_log.append({
            "host": host, "method": flow.request.method, "path": flow.request.path[:200],
            "timestamp": flow.request.timestamp_start,
        })


_coverage_addon: "CoverageAddon | None" = None


def enable_coverage_tracking() -> Dict[str, Any]:
    """Attaches a CoverageAddon to egress_proxy's already-running mitmproxy
    instance. Returns an error (not an exception) if the proxy isn't
    running yet -- coverage tracking is meaningless without real traffic
    flowing through the same interception point."""
    import egress_proxy
    global _coverage_addon

    if egress_proxy._master is None:
        return {"success": False, "error": "egress_proxy is not running -- start it first"}
    if _coverage_addon is not None:
        return {"success": True, "already_enabled": True}

    _coverage_addon = CoverageAddon()
    egress_proxy._master.addons.add(_coverage_addon)
    return {"success": True}


def disable_coverage_tracking() -> Dict[str, Any]:
    global _coverage_addon
    if _coverage_addon is None:
        return {"success": True, "was_enabled": False}
    import egress_proxy
    if egress_proxy._master is not None:
        try:
            egress_proxy._master.addons.remove(_coverage_addon)
        except ValueError:
            pass
    _coverage_addon = None
    return {"success": True, "was_enabled": True}


def _active_vendor_names() -> Set[str]:
    from providers.registry import PROVIDER_REGISTRIES
    from channels.registry import list_channels

    active = set()
    for vendors in PROVIDER_REGISTRIES.values():
        active.update(vendors.keys())
    active.update(list_channels().keys())
    return active


def generate_coverage_report() -> Dict[str, Any]:
    """The real report: every currently-configured vendor/channel, whether
    its expected host was actually observed this session, plus the raw list
    of every host actually seen (including ones with no known vendor
    mapping -- real data the classification table doesn't yet cover)."""
    if _coverage_addon is None:
        return {"success": False, "error": "coverage tracking is not enabled -- call enable_coverage_tracking() first"}

    active_vendors = _active_vendor_names()
    observed = _coverage_addon.observed_hosts

    classified = []
    for vendor in sorted(active_vendors):
        expected_host = _VENDOR_HOSTS.get(vendor)
        if not expected_host:
            classified.append({"vendor": vendor, "expected_host": None, "status": "no_known_host_mapping"})
            continue
        status = "captured" if expected_host.lower() in observed else "uncovered"
        classified.append({"vendor": vendor, "expected_host": expected_host, "status": status})

    known_hosts = {h.lower() for h in _VENDOR_HOSTS.values() if h}
    unclassified_hosts = sorted(observed - known_hosts)

    return {
        "success": True,
        "vendors": classified,
        "unclassified_observed_hosts": unclassified_hosts,
        "total_requests_observed": len(_coverage_addon.request_log),
    }
