"""Real, proactive self-monitoring for Billion's own operational health --
distinct from /system/health (passive, only reported when asked) and
evidence_ledger.py (a historical audit log of tool calls): this watches
system resources and LLM-backend reliability on a real interval, takes the
one safe automatic action it can (ephemeral-file disk cleanup), and reports
state CHANGES only -- never every tick -- matching the "need-to-know basis"
standard already set for background-task notifications.

Backend reliability is read from usage_analytics.json rather than probed
separately: every real chat turn already records success/failure per
backend there (see llm.py's FallbackLLM.generate), so this needs no extra
API calls -- and specifically no extra calls to an already-out-of-credit
paid backend just to confirm it's still out of credit.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import disk_cleanup
import usage_analytics
from llm import llm_backend
from system_monitor import SystemMonitor

logger = logging.getLogger(__name__)

_monitor = SystemMonitor()

# In-memory only -- resets on restart. That's fine: a fresh restart is
# itself a natural point to re-establish "is everything currently okay"
# rather than replaying whatever was wrong in a previous run.
_last_state: Dict[str, bool] = {}


def _primary_backend_name() -> str:
    """The backend actually leading the live chain right now (honours
    LLM_PRIMARY and get_llm_backends()'s catalog order) -- NOT a hardcoded
    guess. Confirmed live as a real bug: this used to be a fixed
    PRIMARY_BACKEND_NAME = "AnthropicLLM" constant, so once OmniRouteLLM
    became the actual primary, this check kept watching Anthropic's
    permanently-exhausted credit balance and proactively telling the user
    "my primary reasoning backend appears to be down" -- alarming and just
    plain wrong, since Anthropic wasn't primary anymore and whatever
    genuinely was primary could have been working fine the whole time."""
    return llm_backend.backends[0].__class__.__name__ if llm_backend.backends else "none"


def _transitioned(check_key: str, healthy_now: bool) -> bool:
    """True only the first time a check's healthy/unhealthy state actually
    flips -- the real anti-spam mechanism. Defaults to "was healthy" so a
    check that's unhealthy from the very first run does fire once."""
    was_healthy = _last_state.get(check_key, True)
    _last_state[check_key] = healthy_now
    return was_healthy != healthy_now


def check_resources() -> Dict[str, Any]:
    """Real psutil-backed resource check (system_monitor.py). Auto-recovers
    the one thing that's actually always safe to auto-recover -- old
    ephemeral files under disk_cleanup's designated directory -- when disk
    is under pressure; everything else is alert-only, since there's no
    generally-safe automatic fix for high CPU/memory."""
    health = _monitor.get_comprehensive_health()
    alerts = _monitor.should_trigger_alert(health)
    actions_taken: List[str] = []

    if health.get("disk", {}).get("status") == "warning":
        result = disk_cleanup.run_cleanup()
        if result.get("deleted_count", 0) > 0:
            freed_mb = result["freed_bytes"] / (1024 * 1024)
            actions_taken.append(
                f"Freed {freed_mb:.1f} MB by removing {result['deleted_count']} old ephemeral file(s)."
            )

    return {"health": health, "alerts": alerts, "actions_taken": actions_taken}


def check_backend_coverage() -> Tuple[bool, Dict[str, Any]]:
    """Healthy means at least one CONFIGURED cloud reasoning backend is
    actually reachable right now -- a materially different (and materially
    scarier) question than check_primary_backend's "is the current #1
    backend okay", which says nothing if every OTHER backend also happens
    to be down. See FallbackLLM.cloud_backend_coverage's docstring for the
    real incident that motivated this: Anthropic + OpenAI both fully out of
    credit and Groq daily-quota-exhausted, all at once, discovered only by
    reading logs by hand."""
    coverage = llm_backend.cloud_backend_coverage()
    return coverage["available_now"] > 0, coverage


def check_primary_backend() -> Tuple[bool, Optional[str]]:
    """Real read of usage_analytics.json -- flags the CURRENT primary
    backend (see _primary_backend_name) as degraded only when it has
    actually been called and never once succeeded (an auth/credit/quota
    failure looks exactly like this). Returns (is_healthy, last_error_text_if_not)."""
    primary = _primary_backend_name()
    summary = usage_analytics.get_usage_summary()
    for entry in summary.get("per_backend", []):
        if entry.get("backend") == primary:
            if entry.get("call_count", 0) > 0 and entry.get("success_count", 0) == 0:
                return False, entry.get("last_error")
            return True, None
    return True, None  # never called yet -- nothing to flag


async def run_check_cycle() -> List[str]:
    """Runs every real check once, returns human-readable messages ONLY for
    checks whose healthy/unhealthy state actually changed since the last
    cycle -- this list is what the caller should actually notify about."""
    messages: List[str] = []

    resource_result = check_resources()
    resources_healthy = resource_result["health"].get("overall_status") == "healthy"
    if _transitioned("resources", resources_healthy):
        if resources_healthy:
            messages.append("System resources are back to normal, Sir.")
        else:
            alert_text = "; ".join(resource_result["alerts"]) or "resource usage is elevated"
            messages.append(f"Heads up, Sir -- {alert_text}.")
    if resource_result["actions_taken"]:
        messages.extend(resource_result["actions_taken"])

    backend_healthy, last_error = check_primary_backend()
    if _transitioned("primary_backend", backend_healthy):
        primary = _primary_backend_name()
        if backend_healthy:
            messages.append(f"{primary} (my primary reasoning backend) is back online, Sir.")
        else:
            messages.append(
                f"Sir, my primary reasoning backend ({primary}) appears to be down"
                + (f": {last_error}" if last_error else "")
                + ". I'm currently running on a fallback backend instead."
            )

    coverage_healthy, coverage = check_backend_coverage()
    if _transitioned("backend_coverage", coverage_healthy):
        if coverage_healthy:
            messages.append(
                f"Cloud reasoning backends are healthy again, Sir -- "
                f"{coverage['available_now']}/{coverage['total_configured']} available."
            )
        else:
            unavailable = ", ".join(coverage["unavailable"]) or "none configured"
            messages.append(
                f"Sir, EVERY configured cloud reasoning backend is unavailable right now "
                f"({unavailable}) -- I'm running on local/offline fallback only, which will be "
                f"noticeably slower and lower quality until at least one comes back."
            )

    return messages
