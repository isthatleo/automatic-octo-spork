"""Real Windows-native process isolation -- ported from OpenClaw's MXC
sandbox backend. Uses real Win32 Job Objects (CreateJobObject +
AssignProcessToJobObject, with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE so nothing
can survive the sandbox handle closing -- no orphaned processes) and a real
restricted access token (CreateRestrictedToken, stripping privileges and
disabling SIDs before launch) -- the practical, available-today equivalent
of Windows `ProcessContainer` isolation on a normal Windows 11 Pro machine.
Full Hyper-V-isolated containers need Windows Server or Docker Desktop with
container support enabled, a much heavier prerequisite than Job Objects +
restricted tokens, which need no elevation and work out of the box.

Runs synchronously in a thread executor (`run_in_executor`) since pywin32's
process/job APIs are blocking Win32 calls, not asyncio-native.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 30.0
MAX_OUTPUT_BYTES = 200_000


def _run_sandboxed_sync(command: str, cwd: Optional[str], timeout: float) -> Dict[str, Any]:
    import win32api
    import win32con
    import win32event
    import win32job
    import win32process
    import win32security
    import pywintypes

    job = None
    proc_handle = None
    thread_handle = None
    restricted_token = None
    read_handle = None

    try:
        # Real Job Object -- KILL_ON_JOB_CLOSE guarantees the sandboxed
        # process (and any children it spawns) can never outlive this
        # function, even if it hangs or forks -- closing the job handle in
        # the `finally` below terminates the whole tree.
        job = win32job.CreateJobObject(None, "")
        limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        limits["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)

        # Real restricted token -- derived from THIS process's own token
        # (not impersonating another user, so CreateProcessAsUser doesn't
        # need SE_ASSIGN_PRIMARY_TOKEN_NAME -- MSDN's documented exception
        # for a restricted version of the caller's own token), with the
        # BUILTIN\Administrators SID disabled and every privilege dropped.
        process_token = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(),
            win32con.TOKEN_DUPLICATE | win32con.TOKEN_QUERY | win32con.TOKEN_ASSIGN_PRIMARY,
        )
        try:
            admins_sid = win32security.CreateWellKnownSid(win32security.WinBuiltinAdministratorsSid)
            sids_to_disable = [(admins_sid, 0)]
        except Exception:
            sids_to_disable = None

        restricted_token = win32security.CreateRestrictedToken(
            process_token,
            0,  # DISABLE_MAX_PRIVILEGE not used -- privileges_to_delete below covers it explicitly
            sids_to_disable,
            win32security.GetTokenInformation(process_token, win32security.TokenPrivileges),
            None,
        )

        # Real anonymous pipe for capturing stdout+stderr, with the write
        # end marked inheritable so the child process can actually write to
        # it (CreateProcessAsUser inherits handles explicitly, unlike
        # subprocess's own higher-level plumbing).
        sa = win32security.SECURITY_ATTRIBUTES()
        sa.bInheritHandle = True
        read_handle, write_handle = win32pipe_create(sa)

        startup_info = win32process.STARTUPINFO()
        startup_info.dwFlags = win32process.STARTF_USESTDHANDLES
        startup_info.hStdOutput = write_handle
        startup_info.hStdError = write_handle

        full_cmd = f'cmd.exe /c "{command}"'
        proc_handle, thread_handle, pid, tid = win32process.CreateProcessAsUser(
            restricted_token, None, full_cmd, None, None, True,
            win32con.CREATE_SUSPENDED, None, cwd, startup_info,
        )
        write_handle.Close()  # parent's copy -- only the child's inherited copy should stay open

        win32job.AssignProcessToJobObject(job, proc_handle)
        win32process.ResumeThread(thread_handle)

        wait_result = win32event.WaitForSingleObject(proc_handle, int(timeout * 1000))

        output = b""
        try:
            while True:
                _, data = win32file_read(read_handle, 4096)
                if not data:
                    break
                output += data
                if len(output) > MAX_OUTPUT_BYTES:
                    break
        except Exception:
            pass

        if wait_result == win32event.WAIT_TIMEOUT:
            win32job.TerminateJobObject(job, 1)
            return {"success": False, "error": f"sandboxed command timed out after {timeout:.0f}s", "stdout": output.decode(errors="replace")}

        exit_code = win32process.GetExitCodeProcess(proc_handle)
        return {"success": exit_code == 0, "exit_code": exit_code, "stdout": output.decode(errors="replace"), "stderr": ""}

    except Exception as e:
        logger.exception("mxc_windows: sandboxed execution failed")
        return {"success": False, "error": str(e)}
    finally:
        for handle in (proc_handle, thread_handle, restricted_token, read_handle):
            if handle:
                try:
                    handle.Close()
                except Exception:
                    pass
        if job:
            try:
                win32job.CloseHandle(job)
            except Exception:
                pass


def win32pipe_create(sa):
    import win32pipe
    return win32pipe.CreatePipe(sa, 0)


def win32file_read(handle, size):
    import win32file
    return win32file.ReadFile(handle, size)


async def run_sandboxed(command: str, cwd: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """Real async entry point -- offloads the blocking Win32 job/token/
    process calls to a thread executor so the event loop isn't blocked
    while the sandboxed command runs."""
    if os.name != "nt":
        return {"success": False, "error": "mxc_windows sandbox is only available on Windows"}
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_sandboxed_sync, command, cwd, timeout)
