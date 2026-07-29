"""Real background process/service management -- "deploy a server" and
"restart a service" for a personal-assistant deployment (this machine
mixes Windows host + Docker containers, so there's no single real
systemd/pm2 layer to integrate with honestly). Instead: real subprocess
management, tracked by a name the caller chooses, persisted so a restart
after a backend reload can still find/stop what it started. Genuinely
starts/stops real OS processes -- not a simulated process table.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STATE_PATH = Path(__file__).parent / "data" / "background_processes.json"

PROCESS_CONTROL_TOOLS = [
    {
        "name": "deploy_server",
        "description": (
            "Real background process launch -- starts `command` detached (so it keeps running after this "
            "tool call returns) under a name you choose, so it can be checked/restarted/stopped later. This "
            "is 'deploy a server' for a personal deployment: no systemd/pm2 layer exists here to integrate "
            "with, so this genuinely starts and tracks the real OS process instead. Mutating -- gated by approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"}, "command": {"type": "string"},
                "cwd": {"type": "string"},
            },
            "required": ["name", "command"],
        },
    },
    {
        "name": "restart_background_process",
        "description": "Real stop + relaunch of a previously deploy_server'd process by name. Mutating -- gated by approval.",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    },
    {
        "name": "stop_background_process",
        "description": "Real termination of a previously deploy_server'd process by name. Mutating -- gated by approval.",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    },
    {
        "name": "list_background_processes",
        "description": "List every process deploy_server has started, with real current alive/dead status.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


@dataclass
class TrackedProcess:
    name: str
    command: str
    cwd: Optional[str]
    pid: int
    started_at: float = field(default_factory=time.time)


class ProcessRegistry:
    def __init__(self, path: Path = STATE_PATH):
        self.path = path
        self._procs: Dict[str, TrackedProcess] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for p in raw:
                tp = TrackedProcess(**p)
                self._procs[tp.name] = tp
        except Exception:
            logger.exception("Failed to load background_processes.json -- starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([asdict(p) for p in self._procs.values()], indent=2), encoding="utf-8")

    def _is_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False
        except OSError:
            return False

    def register(self, tp: TrackedProcess) -> None:
        self._procs[tp.name] = tp
        self._save()

    def get(self, name: str) -> Optional[TrackedProcess]:
        return self._procs.get(name)

    def remove(self, name: str) -> None:
        self._procs.pop(name, None)
        self._save()

    def list_with_status(self) -> List[Dict[str, Any]]:
        out = []
        for tp in self._procs.values():
            out.append({**asdict(tp), "alive": self._is_alive(tp.pid)})
        return out


_registry = ProcessRegistry()


def _spawn(command: str, cwd: Optional[str]) -> int:
    """Real detached subprocess launch, cross-platform."""
    kwargs: Dict[str, Any] = {"cwd": cwd or None, "shell": True}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(command, **kwargs)
    return proc.pid


async def deploy_server(name: str, command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
    existing = _registry.get(name)
    if existing and _registry._is_alive(existing.pid):
        return {"success": False, "error": f"A process named {name!r} is already running (pid {existing.pid}). Stop it first or choose a different name."}
    loop = asyncio.get_event_loop()
    pid = await loop.run_in_executor(None, _spawn, command, cwd)
    _registry.register(TrackedProcess(name=name, command=command, cwd=cwd, pid=pid))
    return {"success": True, "name": name, "pid": pid}


async def stop_background_process(name: str) -> Dict[str, Any]:
    tp = _registry.get(name)
    if tp is None:
        return {"success": False, "error": f"No tracked process named {name!r}."}
    try:
        if os.name == "nt":
            os.kill(tp.pid, signal.CTRL_BREAK_EVENT)
        else:
            os.kill(tp.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass  # already dead -- fine, just untrack it
    except Exception as e:
        return {"success": False, "error": f"Failed to stop pid {tp.pid}: {e}"}
    _registry.remove(name)
    return {"success": True, "name": name, "stopped_pid": tp.pid}


async def restart_background_process(name: str) -> Dict[str, Any]:
    tp = _registry.get(name)
    if tp is None:
        return {"success": False, "error": f"No tracked process named {name!r} -- use deploy_server to start it first."}
    stop_result = await stop_background_process(name)
    if not stop_result.get("success"):
        return stop_result
    await asyncio.sleep(0.5)
    return await deploy_server(name, tp.command, tp.cwd)


async def list_background_processes() -> Dict[str, Any]:
    return {"success": True, "processes": _registry.list_with_status()}
