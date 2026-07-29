"""Real, dedicated Docker operations -- real `docker`/`docker compose`
subprocess calls (distinct from agents/specialized/devops_agent.py's
DevOps agent, which only generates Dockerfile text and never actually runs
containers). Read-only inspection (ps, logs, images) runs unapproved;
anything that builds/starts/stops/restarts a container is mutating and
gated by the same phone-approval flow every other mutating tool uses.

Honesty note: if this backend is itself running inside a Docker container
without the host's Docker socket mounted in, none of these can see or
control sibling containers -- they'll fail with a real, honest connection
error rather than a fake result. Mount `/var/run/docker.sock` (Linux) or
the named pipe (Windows) into the container to make this genuinely work
against the host's Docker daemon.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DOCKER_TOOLS = [
    {
        "name": "docker_ps",
        "description": "Real `docker ps` -- list running (or all, with all_containers=true) containers.",
        "input_schema": {"type": "object", "properties": {"all_containers": {"type": "boolean"}}},
    },
    {
        "name": "docker_logs",
        "description": "Real `docker logs` for a container -- the dedicated way to read container logs (vs. reading a plain file with read_file).",
        "input_schema": {
            "type": "object",
            "properties": {"container": {"type": "string"}, "tail": {"type": "integer", "description": "Default 100."}},
            "required": ["container"],
        },
    },
    {
        "name": "docker_images",
        "description": "Real `docker images` -- list local images.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "docker_build",
        "description": "Real `docker build` for a given context/Dockerfile. Mutating -- gated by approval.",
        "input_schema": {
            "type": "object",
            "properties": {"context": {"type": "string"}, "tag": {"type": "string"}, "dockerfile": {"type": "string"}},
            "required": ["context", "tag"],
        },
    },
    {
        "name": "docker_compose_up",
        "description": "Real `docker compose up -d` in the given directory (optionally a specific service). Mutating -- gated by approval.",
        "input_schema": {"type": "object", "properties": {"cwd": {"type": "string"}, "service": {"type": "string"}}, "required": ["cwd"]},
    },
    {
        "name": "docker_compose_down",
        "description": "Real `docker compose down` in the given directory. Mutating -- gated by approval.",
        "input_schema": {"type": "object", "properties": {"cwd": {"type": "string"}}, "required": ["cwd"]},
    },
    {
        "name": "docker_restart",
        "description": "Real `docker restart` for a named container. Mutating -- gated by approval.",
        "input_schema": {"type": "object", "properties": {"container": {"type": "string"}}, "required": ["container"]},
    },
]


async def _run_docker(args: List[str], cwd: Optional[str] = None, timeout: float = 60.0) -> Dict[str, Any]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", *args, cwd=cwd or None,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"success": False, "error": f"docker command timed out after {timeout:.0f}s"}
        output = (stdout_b.decode(errors="replace") + stderr_b.decode(errors="replace"))[-8000:]
        return {"success": proc.returncode == 0, "returncode": proc.returncode, "output": output}
    except FileNotFoundError:
        return {"success": False, "error": "docker is not installed/available on this server."}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def docker_ps(all_containers: bool = False) -> Dict[str, Any]:
    args = ["ps"] + (["-a"] if all_containers else [])
    return await _run_docker(args)


async def docker_logs(container: str, tail: int = 100) -> Dict[str, Any]:
    return await _run_docker(["logs", "--tail", str(max(1, min(tail, 2000))), container])


async def docker_images() -> Dict[str, Any]:
    return await _run_docker(["images"])


async def docker_build(context: str, tag: str, dockerfile: Optional[str] = None) -> Dict[str, Any]:
    args = ["build", "-t", tag]
    if dockerfile:
        args += ["-f", dockerfile]
    args.append(context)
    return await _run_docker(args, timeout=600.0)


async def docker_compose_up(cwd: str, service: Optional[str] = None) -> Dict[str, Any]:
    args = ["compose", "up", "-d"] + ([service] if service else [])
    return await _run_docker(args, cwd=cwd, timeout=300.0)


async def docker_compose_down(cwd: str) -> Dict[str, Any]:
    return await _run_docker(["compose", "down"], cwd=cwd, timeout=120.0)


async def docker_restart(container: str) -> Dict[str, Any]:
    return await _run_docker(["restart", container], timeout=60.0)
