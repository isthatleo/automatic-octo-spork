"""Real shell command execution for Claude's tool-use loop.

This is the capability gap that made Nancy unable to "actually do stuff on
the machine": tools.py's Fury-framework tools are all placeholders/stubs, and
file_access.py only covers individual file read/write/delete/move -- nothing
could run an arbitrary command. This closes that gap, using the same
human-approval safety pattern already established for file writes
(main_new.py's _execute_file_tool / telegram_notifier.request_approval): a
small allowlist of safe, read-only commands runs immediately, everything else
requires the user's explicit yes/no first.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = float(os.getenv("TERMINAL_TOOL_TIMEOUT_S", "30"))
MAX_OUTPUT_CHARS = 8000

# Command *prefixes* (matched against the lowercased, whitespace-collapsed
# command string) that are read-only / side-effect-free enough to run without
# asking first. Deliberately narrow -- extend it as real needs come up rather
# than guessing every safe command up front.
TERMINAL_SAFE_PREFIXES = (
    "git status", "git log", "git diff", "git show", "git branch",
    "git remote", "git rev-parse", "git rev-list", "git blame", "git fetch --dry-run",
    "dir", "ls", "pwd", "cd", "whoami", "hostname", "echo",
    "type ", "cat ", "where ", "which ",
    "python --version", "python -V", "node --version", "node -v",
    "npm --version", "npm -v", "pip --version", "pip list", "pip show",
    "systeminfo", "tasklist", "ps ", "df ", "du ",
)


def _is_safe_command(command: str) -> bool:
    normalized = " ".join(command.strip().lower().split())
    return any(normalized.startswith(prefix) for prefix in TERMINAL_SAFE_PREFIXES)


async def execute_command(command: str, cwd: str | None = None, timeout: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """Run `command` in a real shell and return its stdout/stderr/exit code.
    No sandboxing -- same "no folder sandbox, gate destructive action behind
    human approval" choice file_access.py already made for this machine."""
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd or None,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"success": False, "error": f"Command timed out after {timeout:.0f}s", "command": command}

        stdout = stdout_b.decode(errors="replace")[:MAX_OUTPUT_CHARS]
        stderr = stderr_b.decode(errors="replace")[:MAX_OUTPUT_CHARS]
        return {
            "success": proc.returncode == 0,
            "command": command,
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
    except Exception as e:
        logger.exception("execute_command failed for %r", command)
        return {"success": False, "error": str(e), "command": command}


TERMINAL_TOOLS = [
    {
        "name": "execute_command",
        "description": (
            "Run a real shell command on the user's computer and return its stdout, stderr, "
            "and exit code. Read-only commands (git status/log/diff, dir/ls, whoami, --version "
            "checks, etc.) run immediately. Anything else (installing packages, deleting files, "
            "git commit/push, starting/stopping processes) requires the user's explicit yes/no "
            "approval, sent to their phone, before it executes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The full shell command to run."},
                "cwd": {"type": "string", "description": "Optional working directory to run it from."},
            },
            "required": ["command"],
        },
    },
]
