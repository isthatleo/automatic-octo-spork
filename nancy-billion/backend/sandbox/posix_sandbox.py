"""Real POSIX sandbox backends -- the Linux/macOS counterparts to
sandbox/mxc_windows.py's Windows Job Objects, using each platform's own
standard, built-in isolation primitive rather than a third-party dependency:

- Linux: `unshare` (part of util-linux, present on effectively every distro)
  -- real PID/mount/network/UTS namespace isolation, no special package or
  root privilege needed for user namespaces on a modern kernel.
- macOS: `sandbox-exec` (Apple's built-in Seatbelt sandboxing, present on
  every macOS install since 10.5) with a real restrictive profile denying
  network access and file writes outside an explicit allowlist.

IMPORTANT PROVENANCE NOTE: unlike every other feature built this session,
these two paths were implemented against each tool's real documented
behavior but could NOT be live-executed and verified here -- this
development machine is Windows, with no Linux/macOS host available to run
them against. sandbox/mxc_windows.py's Windows path, by contrast, WAS
run and verified live (real Job Object, real restricted token, real
captured stdout/exit codes, real timeout-triggered termination). Treat
this file as reviewed-but-unverified until it's actually exercised on a
real Linux or macOS machine.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 30.0
MAX_OUTPUT_CHARS = 8000


async def _run_subprocess(argv: list[str], cwd: Optional[str], timeout: float) -> Dict[str, Any]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"success": False, "error": f"sandboxed command timed out after {timeout:.0f}s"}
        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": stdout_b.decode(errors="replace")[:MAX_OUTPUT_CHARS],
            "stderr": stderr_b.decode(errors="replace")[:MAX_OUTPUT_CHARS],
        }
    except FileNotFoundError as e:
        return {"success": False, "error": f"sandbox tool not found: {e}"}
    except Exception as e:
        logger.exception("posix_sandbox: execution failed")
        return {"success": False, "error": str(e)}


async def run_linux_namespace_sandbox(command: str, cwd: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """Real Linux namespace isolation via `unshare`. --pid --fork gives the
    command its own PID namespace (can't see/signal real host processes);
    --net gives it its own (loopback-only, no real network) net namespace;
    --mount-proc keeps /proc consistent with the new PID namespace, which
    `unshare --pid` requires to behave correctly rather than showing the
    host's real process table."""
    if shutil.which("unshare") is None:
        return {"success": False, "error": "unshare is not available on this system (expected on Linux, part of util-linux)"}
    argv = ["unshare", "--pid", "--fork", "--net", "--mount-proc", "--", "sh", "-c", command]
    return await _run_subprocess(argv, cwd, timeout)


_MACOS_SEATBELT_PROFILE = """
(version 1)
(deny default)
(allow process-fork)
(allow process-exec)
(allow file-read*)
(allow file-write* (subpath "/tmp"))
(allow sysctl-read)
"""


async def run_macos_seatbelt_sandbox(command: str, cwd: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """Real macOS sandboxing via Apple's built-in `sandbox-exec` (Seatbelt).
    The profile above is deliberately conservative: no network sockets, no
    file writes outside /tmp, but reads/exec/fork allowed so a normal
    command (not requiring network or writing real project files) can still
    run and produce real output."""
    if shutil.which("sandbox-exec") is None:
        return {"success": False, "error": "sandbox-exec is not available on this system (expected on macOS)"}
    argv = ["sandbox-exec", "-p", _MACOS_SEATBELT_PROFILE, "sh", "-c", command]
    return await _run_subprocess(argv, cwd, timeout)


async def run_native_sandbox(command: str, cwd: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """Real cross-platform entry point -- picks whichever real sandbox
    primitive actually exists on this host OS. Callers that don't care which
    specific backend runs (just "isolate this command, whatever platform
    we're on") should call this instead of a platform-named function directly."""
    import platform
    system = platform.system()

    if system == "Windows":
        from sandbox.mxc_windows import run_sandboxed
        return await run_sandboxed(command, cwd=cwd, timeout=timeout)
    if system == "Linux":
        return await run_linux_namespace_sandbox(command, cwd=cwd, timeout=timeout)
    if system == "Darwin":
        return await run_macos_seatbelt_sandbox(command, cwd=cwd, timeout=timeout)
    return {"success": False, "error": f"no sandbox backend implemented for platform: {system}"}
