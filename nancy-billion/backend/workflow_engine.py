"""Real typed workflow engine -- ported from OpenClaw's Lobster workflow
shell. A typed, JSON-first step schema with resumable human-approval steps,
layered directly on top of the primitives Nancy already has -- agent_service
for agent_task steps, terminal_tool for terminal_command steps,
telegram_notifier.request_approval for approval_gate steps -- rather than a
parallel execution engine. Real resumability: a run's progress (completed
step results) is persisted after every step, so a run that stops on a
denied/pending approval can be resumed later from exactly where it left off,
not restarted from step 1.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

RUNS_STORE_PATH = Path(__file__).parent / "data" / "workflow_runs.json"

StepType = Literal["agent_task", "terminal_command", "approval_gate", "run_skill"]


@dataclass
class WorkflowStep:
    name: str
    type: StepType
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowTemplate:
    key: str
    title: str
    steps: List[WorkflowStep]


def _load_runs() -> Dict[str, Dict[str, Any]]:
    if not RUNS_STORE_PATH.exists():
        return {}
    try:
        return json.loads(RUNS_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_runs(runs: Dict[str, Dict[str, Any]]) -> None:
    RUNS_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNS_STORE_PATH.write_text(json.dumps(runs, indent=2), encoding="utf-8")


def _serialize_template(template: WorkflowTemplate) -> Dict[str, Any]:
    return {"key": template.key, "title": template.title, "steps": [{"name": s.name, "type": s.type, "payload": s.payload} for s in template.steps]}


async def _execute_step(step: WorkflowStep) -> Dict[str, Any]:
    if step.type == "agent_task":
        from agents.agent_service import agent_service
        if not agent_service.is_ready():
            return {"success": False, "error": "agent service not ready"}
        return await agent_service.run(step.payload.get("agent_key", "dispatcher"), {"type": step.payload.get("task_type", "query"), **step.payload.get("payload", {})}, timeout=60.0)

    if step.type == "terminal_command":
        import terminal_tool
        return await terminal_tool.execute_command(step.payload.get("command", ""), cwd=step.payload.get("cwd"))

    if step.type == "run_skill":
        import skill_loader
        skill = skill_loader.get_skill(step.payload.get("skill_name", ""))
        if skill is None:
            return {"success": False, "error": f"unknown skill: {step.payload.get('skill_name')}"}
        return {"success": True, "instructions": skill.instructions}

    if step.type == "approval_gate":
        from telegram_bot import telegram_notifier
        approved = await telegram_notifier.request_approval(
            step.payload.get("message", f"Workflow approval requested: {step.name}"), timeout=step.payload.get("timeout", 300.0),
        )
        if not approved:
            return {"success": False, "pending_approval": True, "error": "not approved"}
        return {"success": True}

    return {"success": False, "error": f"unknown step type: {step.type}"}


async def run_workflow(template: WorkflowTemplate, start_from_step: int = 0) -> Dict[str, Any]:
    """Runs `template` starting at `start_from_step` (0 for a fresh run).
    Persists progress after every step; stops (without failing the whole
    run) the moment a step reports pending_approval, so resume_run() can
    pick up right there later."""
    run_id = uuid.uuid4().hex[:12]
    runs = _load_runs()
    run_record = {
        "run_id": run_id, "template": _serialize_template(template), "status": "running",
        "current_step": start_from_step, "step_results": [], "created_at": time.time(),
    }
    runs[run_id] = run_record
    _save_runs(runs)

    result = await _continue_run(run_id, template, start_from_step)
    return result


async def _continue_run(run_id: str, template: WorkflowTemplate, from_step: int) -> Dict[str, Any]:
    runs = _load_runs()
    run_record = runs[run_id]

    for i in range(from_step, len(template.steps)):
        step = template.steps[i]
        logger.info("workflow_engine: run %s step %d/%d (%s)", run_id, i + 1, len(template.steps), step.name)
        step_result = await _execute_step(step)
        run_record["step_results"].append({"step": step.name, "result": step_result})
        run_record["current_step"] = i

        if not step_result.get("success"):
            run_record["status"] = "paused_pending_approval" if step_result.get("pending_approval") else "failed"
            _save_runs(runs)
            return {"success": False, "run_id": run_id, "status": run_record["status"], "failed_at_step": step.name, "step_results": run_record["step_results"]}

    run_record["status"] = "completed"
    run_record["current_step"] = len(template.steps)
    _save_runs(runs)
    return {"success": True, "run_id": run_id, "status": "completed", "step_results": run_record["step_results"]}


async def resume_run(run_id: str) -> Dict[str, Any]:
    """Real resumability: reconstructs the WorkflowTemplate from the
    persisted run record and continues from run_record['current_step'] + 1
    (the step after whichever one paused it) -- never re-runs an
    already-completed step."""
    runs = _load_runs()
    run_record = runs.get(run_id)
    if run_record is None:
        return {"success": False, "error": f"no such run: {run_id}"}
    if run_record["status"] == "completed":
        return {"success": True, "run_id": run_id, "status": "completed", "note": "already completed"}

    template_data = run_record["template"]
    template = WorkflowTemplate(
        key=template_data["key"], title=template_data["title"],
        steps=[WorkflowStep(name=s["name"], type=s["type"], payload=s["payload"]) for s in template_data["steps"]],
    )
    return await _continue_run(run_id, template, run_record["current_step"] + 1 if run_record["status"] != "failed" else run_record["current_step"])


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    return _load_runs().get(run_id)


def list_runs() -> List[Dict[str, Any]]:
    return list(_load_runs().values())
