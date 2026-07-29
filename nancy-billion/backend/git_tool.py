"""Real, dedicated Git operations -- previously only reachable through
execute_command's raw shell strings (still works, but the model has to
remember exact syntax and terminal_tool.py's safe-prefix gating every
time). Same real subprocess execution, same safe/gated split as
terminal_tool.py: read-only commands run unapproved, anything that changes
repo state goes through the same phone-approval gate every other mutating
tool call does.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

READ_ONLY_SUBCOMMANDS = {"status", "diff", "log", "show", "branch", "remote", "blame", "shortlog"}
MUTATING_SUBCOMMANDS = {"add", "commit", "push", "pull", "checkout", "merge", "rebase", "reset", "stash", "tag", "fetch"}

GIT_TOOLS = [
    {
        "name": "git_status",
        "description": "Real `git status` in the given (or current) directory.",
        "input_schema": {"type": "object", "properties": {"cwd": {"type": "string"}}},
    },
    {
        "name": "git_diff",
        "description": "Real `git diff` (working tree vs. index, or `--staged` if requested).",
        "input_schema": {
            "type": "object",
            "properties": {"cwd": {"type": "string"}, "staged": {"type": "boolean"}, "path": {"type": "string"}},
        },
    },
    {
        "name": "git_log",
        "description": "Real `git log` (oneline, most recent commits first).",
        "input_schema": {"type": "object", "properties": {"cwd": {"type": "string"}, "count": {"type": "integer"}}},
    },
    {
        "name": "git_branch",
        "description": "Real `git branch` -- list local branches, or create/switch with `create`/`checkout`.",
        "input_schema": {
            "type": "object",
            "properties": {"cwd": {"type": "string"}, "create": {"type": "string"}, "checkout": {"type": "string"}},
        },
    },
    {
        "name": "git_commit",
        "description": "Real `git add` (given paths, or all) + `git commit -m`. Mutating -- gated by approval.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string"}, "message": {"type": "string"},
                "paths": {"type": "array", "items": {"type": "string"}, "description": "Defaults to all changed files."},
            },
            "required": ["message"],
        },
    },
    {
        "name": "git_push",
        "description": "Real `git push`. Mutating -- gated by approval.",
        "input_schema": {"type": "object", "properties": {"cwd": {"type": "string"}, "remote": {"type": "string"}, "branch": {"type": "string"}}},
    },
    {
        "name": "git_pull",
        "description": "Real `git pull`. Mutating -- gated by approval.",
        "input_schema": {"type": "object", "properties": {"cwd": {"type": "string"}, "remote": {"type": "string"}, "branch": {"type": "string"}}},
    },
]


async def _run_git(args: List[str], cwd: str | None) -> Dict[str, Any]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=cwd or None,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"success": False, "error": "git command timed out"}
        output = (stdout_b.decode(errors="replace") + stderr_b.decode(errors="replace"))[-6000:]
        return {"success": proc.returncode == 0, "returncode": proc.returncode, "output": output}
    except FileNotFoundError:
        return {"success": False, "error": "git is not installed on this server."}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def git_status(cwd: str | None = None) -> Dict[str, Any]:
    return await _run_git(["status"], cwd)


async def git_diff(cwd: str | None = None, staged: bool = False, path: str | None = None) -> Dict[str, Any]:
    args = ["diff"] + (["--staged"] if staged else [])
    if path:
        args += ["--", path]
    return await _run_git(args, cwd)


async def git_log(cwd: str | None = None, count: int = 15) -> Dict[str, Any]:
    return await _run_git(["log", f"-{max(1, min(count, 100))}", "--oneline"], cwd)


async def git_branch(cwd: str | None = None, create: str | None = None, checkout: str | None = None) -> Dict[str, Any]:
    if create:
        return await _run_git(["checkout", "-b", create], cwd)
    if checkout:
        return await _run_git(["checkout", checkout], cwd)
    return await _run_git(["branch"], cwd)


async def git_commit(message: str, cwd: str | None = None, paths: List[str] | None = None) -> Dict[str, Any]:
    add_result = await _run_git(["add"] + (paths if paths else ["-A"]), cwd)
    if not add_result["success"]:
        return add_result
    return await _run_git(["commit", "-m", message], cwd)


async def git_push(cwd: str | None = None, remote: str = "origin", branch: str | None = None) -> Dict[str, Any]:
    args = ["push", remote] + ([branch] if branch else [])
    return await _run_git(args, cwd)


async def git_pull(cwd: str | None = None, remote: str = "origin", branch: str | None = None) -> Dict[str, Any]:
    args = ["pull", remote] + ([branch] if branch else [])
    return await _run_git(args, cwd)
