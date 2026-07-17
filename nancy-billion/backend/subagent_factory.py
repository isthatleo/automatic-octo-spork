"""Lets Nancy create her own new specialized agents (see main_new.py's
Claude tool-use, CREATE_SUBAGENT_TOOL / _execute_create_subagent_tool).

This is a fundamentally different risk tier than the file_access.py tools:
a new agent is arbitrary Python that gets imported and its methods called --
there is no sandbox around what a SpecializedAgent subclass can do once
loaded. Two safeguards, both mandatory, not optional:

1. A static safety scan (syntax validity + a denylist of dangerous imports/
   calls) before anything is written to disk. This is a best-effort net,
   not a real sandbox -- it catches obviously dangerous code, not everything.
2. Telegram approval (separate from the write-approval gate in
   _execute_file_tool) showing the proposed agent's name/domain/description
   and a code preview, required before the file is written.

New agents take effect on the NEXT BACKEND RESTART ONLY -- there is no
hot-reload of a running AgentService (see agents/specialized/dynamic_registry.py).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Dict

DYNAMIC_AGENTS_DIR = Path(__file__).parent / "agents" / "specialized" / "dynamic"

# Best-effort denylist -- not a real sandbox. Blocks the obvious ways
# generated code could do something other than the declared task: shelling
# out, dynamic code execution, raw network sockets, or altering its own
# source. A determined adversarial generation could still evade this; the
# Telegram approval step is the real backstop, not this list.
_DANGEROUS_PATTERNS = [
    r"\bsubprocess\b",
    r"\bos\.system\b",
    r"\bos\.popen\b",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\b__import__\s*\(",
    r"\bsocket\b",
    r"\bctypes\b",
    r"\bpickle\.loads\b",
]

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")


def validate_agent_code(key: str, class_name: str, code: str) -> Dict[str, Any]:
    """Static checks only -- no execution. Returns {"ok": True} or
    {"ok": False, "error": "..."}."""
    if not _KEY_RE.match(key):
        return {"ok": False, "error": f"Invalid agent key {key!r}: must be lowercase snake_case, 3-40 chars."}

    if (DYNAMIC_AGENTS_DIR / f"{key}_agent.py").exists():
        return {"ok": False, "error": f"An agent with key '{key}' already exists in agents/specialized/dynamic/."}

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {"ok": False, "error": f"Generated code has a syntax error: {e}"}

    if class_name not in {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}:
        return {"ok": False, "error": f"Generated code doesn't define a class named '{class_name}'."}

    if "SpecializedAgent" not in code:
        return {"ok": False, "error": "Generated code must subclass SpecializedAgent."}

    if "async def process_task" not in code:
        return {"ok": False, "error": "Generated code must implement 'async def process_task(self, task_data)'."}

    for pattern in _DANGEROUS_PATTERNS:
        if re.search(pattern, code):
            return {
                "ok": False,
                "error": f"Generated code matched a disallowed pattern ({pattern}) -- refusing to create this agent.",
            }

    return {"ok": True}


def write_agent_file(key: str, code: str) -> Dict[str, Any]:
    """Only call after validate_agent_code() passed AND the user approved
    via Telegram. Writes agents/specialized/dynamic/<key>_agent.py."""
    try:
        DYNAMIC_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
        path = DYNAMIC_AGENTS_DIR / f"{key}_agent.py"
        path.write_text(code, encoding="utf-8")
        return {"success": True, "path": str(path)}
    except Exception as e:
        return {"success": False, "error": str(e)}
