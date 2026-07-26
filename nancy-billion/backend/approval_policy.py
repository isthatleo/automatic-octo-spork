"""Real persisted allow-once/allow-always/deny approval policy -- ported
from OpenClaw's node-host exec-policy engine. The evolution of Nancy's
existing one-off Telegram approval (telegram_bot.py's request_approval):
instead of asking every single time, a user can grant "always allow" for a
specific command pattern on a specific node, persisted across restarts, so
routine safe operations on a trusted paired device stop requiring a fresh
prompt every time while still gating anything novel.

Windows-shell-wrapper detection is the real security property this module
adds beyond a plain lookup table: a command that invokes a shell wrapper
(cmd /c, powershell -Command/-EncodedCommand, wsl) can carry an arbitrary
payload the wrapper itself interprets -- prefix-matching against a stored
pattern would otherwise be trivially bypassable by wrapping an unapproved
command so it happens to share a prefix with an approved one. Wrapped
commands NEVER match a stored "always allow" policy, full stop -- they
always fall through to requiring a fresh explicit approval.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, Literal, Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "approval_policy.json"

ApprovalDecision = Literal["allow_once", "allow_always", "deny"]

# Real, deliberately broad detection -- any of these prefixes means "this
# command hands control to a second interpreter that can run arbitrary
# further commands," which a fixed-prefix pattern match can never safely
# vouch for. Matched case-insensitively against the normalized command.
_SHELL_WRAPPER_PATTERNS = [
    re.compile(r"^cmd(\.exe)?\s+/[ck]\b", re.IGNORECASE),
    re.compile(r"^powershell(\.exe)?\s+.*-(e|enc|encodedcommand|command)\b", re.IGNORECASE),
    re.compile(r"^pwsh(\.exe)?\s+.*-(e|enc|encodedcommand|command)\b", re.IGNORECASE),
    re.compile(r"^wsl(\.exe)?\b", re.IGNORECASE),
    re.compile(r"^bash\s+-c\b", re.IGNORECASE),
    re.compile(r"^sh\s+-c\b", re.IGNORECASE),
    re.compile(r"^(start|start-process)\b", re.IGNORECASE),
]

# How many leading whitespace-separated tokens form the stored "pattern" --
# e.g. "git push origin main" -> pattern "git push", matching the same
# granularity terminal_tool.py's own safe-command allowlist already uses.
PATTERN_TOKEN_COUNT = 2


def is_wrapped_command(command: str) -> bool:
    normalized = command.strip()
    return any(p.search(normalized) for p in _SHELL_WRAPPER_PATTERNS)


def _pattern_for(command: str) -> str:
    tokens = command.strip().lower().split()
    return " ".join(tokens[:PATTERN_TOKEN_COUNT])


def _load() -> Dict[str, str]:
    if not STORE_PATH.exists():
        return {}
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: Dict[str, str]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _key(node_id: str, pattern: str) -> str:
    return f"{node_id}::{pattern}"


def check_policy(node_id: str, command: str) -> Optional[ApprovalDecision]:
    """Returns the stored decision for this (node, command-pattern) pair,
    or None if there's no matching policy yet (caller should prompt for a
    fresh approval). A wrapped command ALWAYS returns None regardless of
    what's stored -- see module docstring."""
    if is_wrapped_command(command):
        return None
    data = _load()
    decision = data.get(_key(node_id, _pattern_for(command)))
    return decision  # type: ignore[return-value]


def set_policy(node_id: str, command: str, decision: ApprovalDecision) -> None:
    """Persists a decision. allow_once is deliberately NOT persisted (by
    definition it only applies to the one invocation that triggered it) --
    only allow_always/deny are worth remembering for next time."""
    if decision == "allow_once":
        return
    data = _load()
    data[_key(node_id, _pattern_for(command))] = decision
    _save(data)
    logger.info("approval_policy: %s set for node=%s pattern=%r", decision, node_id, _pattern_for(command))


def list_policies(node_id: Optional[str] = None) -> Dict[str, str]:
    data = _load()
    if node_id is None:
        return data
    prefix = f"{node_id}::"
    return {k[len(prefix):]: v for k, v in data.items() if k.startswith(prefix)}


def revoke_policy(node_id: str, pattern: str) -> bool:
    data = _load()
    key = _key(node_id, pattern)
    if key in data:
        del data[key]
        _save(data)
        return True
    return False
