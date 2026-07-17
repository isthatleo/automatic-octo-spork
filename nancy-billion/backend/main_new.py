import os

from dotenv import load_dotenv

# Must run before any local import below -- several modules (llm.py's
# get_llm_backends(), telegram_bot.py's TelegramNotifier) build module-level
# singletons that read os.getenv(...) at import time. Loading .env after
# those imports (as this file used to) meant ANTHROPIC_API_KEY, the Telegram
# credentials, etc. were silently empty for the singleton's whole lifetime,
# even though the same values worked fine in an isolated script that called
# load_dotenv() first.
load_dotenv()

import logging

# Also before any local import: a module-level logger.info/warning call made
# before basicConfig() configures the root logger's handler is not just
# unstyled -- Python's handler-of-last-resort silently drops anything below
# WARNING, so those early messages (e.g. "Adding AnthropicLLM as primary
# backend") never appeared anywhere, not even unformatted.
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

import asyncio
import base64
import json
import threading
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

# Fury imports
try:
    from fury import Agent, HistoryManager
    _FURY_AVAILABLE = True
except ImportError:
    _FURY_AVAILABLE = False
    Agent = None  # type: ignore
    HistoryManager = None  # type: ignore

# Local imports
from stt import stt_backend
from llm import llm_backend, select_llm_for_task, AnthropicLLM
import file_access
import subagent_factory
from tts import tts_backend
from neu_tts import NeuTTSBackend
from tools import get_tools
from wake_word import get_wake_word_detector
from audio_decode import decode_webm_opus_b64_to_pcm, pcm_int16_to_float32
from clap_detection import clap_detector
from telegram_bot import telegram_notifier
from agents.agent_service import agent_service
from context_manager import NancyContextualBrain, IntentType
from memory import MemoryManager, MemoryType
from startup import StartupCoordinator, NancyGreeting
from intelligent_greeting import IntelligentStartupCoordinator, PersonalContext
from trading import (
    ForexDataAggregator,
    TechnicalAnalysisEngine,
    StrategyAdvisor,
    RiskMonitor,
    TradingManager,
)
from system_monitor import SystemMonitor

try:
    from agent_executor import run_specialized_agent as fury_run_agent
    _AGENT_EXEC_AVAILABLE = True
except Exception:
    _AGENT_EXEC_AVAILABLE = False
    async def fury_run_agent(*a, **kw):  # type: ignore
        raise RuntimeError("Fury agent executor not available")

app = FastAPI(title="Nancy/Billion Backend", version="2.0.0")

# CORS — explicit origins only. The previous config included "*" alongside
# named origins, which (a) makes the named origins meaningless and (b) is
# invalid per the CORS spec when combined with allow_credentials=True (browsers
# reject it). Configure NANCY_ALLOWED_ORIGINS as a comma-separated list for
# non-default deployments (e.g. LAN access) instead of adding "*" back.
_allowed_origins = [
    o.strip() for o in os.getenv(
        "NANCY_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Lightweight security: optional shared-secret auth + per-IP rate limiting.
# Both are no-ops by default (localhost dev) and activate via env vars, since
# this backend may end up reachable beyond localhost (LAN, tunnel, etc.).
# ---------------------------------------------------------------------------
from fastapi import Request, Depends
import time as _time
from collections import defaultdict, deque

_BACKEND_AUTH_TOKEN = os.getenv("BACKEND_AUTH_TOKEN", "").strip()


async def require_auth(request: Request) -> None:
    """No-op unless BACKEND_AUTH_TOKEN is set, in which case requests to
    sensitive routes must carry `Authorization: Bearer <token>`."""
    if not _BACKEND_AUTH_TOKEN:
        return
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    if token != _BACKEND_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization bearer token")


class _RateLimiter:
    """Simple in-memory sliding-window limiter, per client IP. Adequate for a
    single-instance personal deployment; not distributed-safe."""

    def __init__(self, max_requests: int = 30, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: Dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> bool:
        now = _time.time()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()
        if len(hits) >= self.max_requests:
            return False
        hits.append(now)
        return True


_rate_limiter = _RateLimiter(
    max_requests=int(os.getenv("BACKEND_RATE_LIMIT_MAX", "30")),
    window_seconds=float(os.getenv("BACKEND_RATE_LIMIT_WINDOW_S", "60")),
)


async def rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded — slow down")

# Global loop reference for thread-safe async calls
main_loop = None

# Nancy's Startup Coordinator
startup_coordinator = StartupCoordinator()

# Real psutil-backed system health monitor (was defined but never wired to any route)
system_monitor = SystemMonitor()

# Nancy's Contextual Brain (handles routing, memory, context)
nancy_brain = NancyContextualBrain(user_id="user")

# Nancy's Memory System (long-term intelligence)
memory_manager = MemoryManager(user_id="user")
memory_manager.set_context_manager(nancy_brain.context)

# Nancy's Trading Intelligence System
forex_aggregator = ForexDataAggregator()
analysis_engine = TechnicalAnalysisEngine()
strategy_advisor = StrategyAdvisor()
risk_monitor = RiskMonitor(account_balance=100000)
trading_manager = TradingManager(user_id="user")

# Log Nancy's startup
logger.info("=" * 70)
logger.info("🎉 NANCY/BILLION AI OPERATING SYSTEM STARTING")
logger.info("=" * 70)
logger.info(f"Version: 2.0.0 - Production Ready")
logger.info(f"Persona: {startup_coordinator.persona.upper()}")
logger.info(f"Timestamp: {datetime.now().isoformat()}")
logger.info("=" * 70)

# ---------------------------------------------------------------------------
# Base system prompt
# ---------------------------------------------------------------------------
BASE_SYSTEM_PROMPT = """
You are Nancy/Billion, a highly intelligent, versatile, and sovereign AI operating system. You are an expert general-purpose assistant capable of reasoning through complex problems, answering a wide range of questions, and controlling the user's computer through voice commands.

CRITICAL: Do NOT assume that a user's query is a map location, address, or city name unless it is explicitly framed as one. Treat every request with a general-purpose intelligence first. If the user asks a basic question, answer it directly and intelligently.

You have access to a variety of tools for system control, coding, web search, media generation, and more. You speak in a clear, confident, and helpful tone. You can spawn specialized agents to handle complex tasks. Always aim to assist the user efficiently and safely.
"""

# ---------------------------------------------------------------------------
# Fury agent (optional)
# ---------------------------------------------------------------------------
if _FURY_AVAILABLE:
    try:
        agent = Agent(
            model=os.getenv("LLM_MODEL_PATH", "llamafactory/Llama-3-8B-Instruct-GGUF"),
            system_prompt=BASE_SYSTEM_PROMPT,
            tools=get_tools(),
        )
        history_root = os.getenv("HISTORY_ROOT", "./data/fury_history")
        history_manager = HistoryManager(
            history_root=history_root,
            persist_to_disk=True,
            agent=agent,
            session_id=os.getenv("HISTORY_SESSION_ID", "nancybillion"),
        )
    except Exception as e:
        logger.warning("Fury agent init failed (non-fatal): %s", e)
        agent = None
        history_manager = None
else:
    agent = None
    history_manager = None


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket connected. Total: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("WebSocket disconnected. Total: %d", len(self.active_connections))

    async def send(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Wake word
# ---------------------------------------------------------------------------
def on_wake_word():
    logger.info("Wake word detected!")
    if main_loop is not None:
        asyncio.run_coroutine_threadsafe(
            manager.broadcast(json.dumps({"type": "wake_word_detected"})),
            main_loop,
        )

try:
    wake_word_detector = get_wake_word_detector()
    threading.Thread(target=lambda: wake_word_detector.start(on_wake_word), daemon=True).start()
    logger.info("Wake word detector started.")
except Exception as e:
    logger.warning("Wake word detector unavailable: %s", e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
LONG_RUNNING_NOTIFY_THRESHOLD_S = float(os.getenv("LONG_RUNNING_NOTIFY_THRESHOLD_S", "15"))


async def _notify_if_long_running(label: str, started_at: float, result: Any) -> None:
    """Push a Telegram summary if a REST-triggered agent task took long enough
    that the user plausibly stepped away before it finished. No-op if
    Telegram isn't configured -- this is a best-effort convenience, not a
    hard requirement for the endpoint to work."""
    elapsed = _time.monotonic() - started_at
    if elapsed < LONG_RUNNING_NOTIFY_THRESHOLD_S:
        return
    summary = str(result.get("response") or result.get("result") or result)[:300]
    await telegram_notifier.send(f"Finished {label} ({elapsed:.0f}s):\n\n{summary}")


def _maybe_gate_self_improvement(agent_key: str, result: Dict[str, Any]) -> None:
    """RecursiveSelfImprovementEngine requires an explicit human_approve call
    before applying any self-modification, on top of its own automated
    SafetyVerifier pass (agents/specialized/recursive_self_improvement_engine.py)
    -- but until now nothing ever told a human a proposal was waiting, so that
    gate had no real notification channel. Once a proposal clears automated
    verification (status=approved), text the user for a real yes/no and, on
    approval, call human_approve on their behalf. Fire-and-forget: this must
    not block the REST response that triggered the verify call.
    """
    if agent_key != "self_improvement":
        return
    if result.get("type") != "verification_result":
        return
    if not result.get("verification_passed") or result.get("status") != "approved":
        return

    proposal_id = result.get("proposal_id")
    if not proposal_id:
        return

    async def _gate() -> None:
        approved = await telegram_notifier.request_approval(
            f"Nancy's self-improvement engine has a proposal that passed automated "
            f"safety verification and is awaiting your sign-off.\n\nProposal ID: {proposal_id}\n\n"
            f"This will NOT be applied unless you approve it here."
        )
        if not approved:
            logger.info("Self-improvement proposal %s not approved via Telegram", proposal_id)
            return
        approval_result = await agent_service.run(
            "self_improvement",
            {"type": "human_approve", "proposal_id": proposal_id, "approved_by": "telegram"},
            timeout=10.0,
        )
        if approval_result.get("success"):
            await telegram_notifier.send(
                f"Approved proposal {proposal_id}. It's marked human-approved but still "
                f"requires a separate 'apply' call -- it won't auto-apply from here."
            )
        else:
            await telegram_notifier.send(
                f"Tried to record your approval for {proposal_id} but it failed: "
                f"{approval_result.get('error', 'unknown error')}"
            )

    asyncio.create_task(_gate())


def _history_to_text() -> str:
    if history_manager is None:
        return ""
    history_lines = []
    for msg in history_manager.history:
        history_lines.append(f"{msg.get('role','?')}: {msg.get('content','')}")
    return "\n".join(history_lines)


def _live_system_context() -> str:
    """A compact, real snapshot of backend state, injected into every chat
    prompt so meta-questions ('how many agents are running?') get grounded
    answers instead of the LLM guessing from the system prompt alone -- which
    is why 'how many agents are running' previously got 'none': nothing in
    the prompt ever told the model any agents existed at all."""
    if not agent_service.is_ready():
        return "Live system status: the specialized agent service is still initialising."
    stats = agent_service.get_service_stats()
    domains = ", ".join(a.get("domain", a.get("key", "?")) for a in agent_service.list_agents())
    return (
        f"Live system status: {stats['agents_online']} specialized agents online, "
        f"{stats['agents_offline']} offline, {stats['total_tasks']} tasks completed so far "
        f"({stats['success_rate'] * 100:.1f}% success rate). "
        f"Available agent domains: {domains}."
    )


# ---------------------------------------------------------------------------
# File access tools (Claude tool-use only -- see AnthropicLLM.generate_with_tools)
#
# Per explicit user choice this session: no folder sandbox (any path Nancy's
# process can reach is fair game), but every write/delete/move is gated
# behind a real Telegram yes/no before it executes. Reads are immediate.
# ---------------------------------------------------------------------------
FILE_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Read the text content of a file on the user's computer, given an absolute or ~-relative path.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files and subdirectories inside a directory on the user's computer.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Create or overwrite a text file on the user's computer. "
            "Requires the user's explicit yes/no approval (sent to their phone) before it takes effect."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "delete_file",
        "description": (
            "Delete a file or directory (recursively) on the user's computer. "
            "Requires the user's explicit yes/no approval (sent to their phone) before it takes effect."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "move_file",
        "description": (
            "Move or rename a file/directory on the user's computer. "
            "Requires the user's explicit yes/no approval (sent to their phone) before it takes effect."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"src": {"type": "string"}, "dst": {"type": "string"}},
            "required": ["src", "dst"],
        },
    },
]

_FILE_WRITE_TOOLS = {"write_file", "delete_file", "move_file"}

# ---------------------------------------------------------------------------
# Subagent creation (Claude tool-use only, same as file access -- see
# subagent_factory.py for why this is a materially higher risk tier than
# read/write/delete on individual files: a new agent is arbitrary Python that
# gets imported and its methods called, not a bounded I/O operation).
# ---------------------------------------------------------------------------
CREATE_SUBAGENT_TOOL: Dict[str, Any] = {
    "name": "create_subagent",
    "description": (
        "Create a brand new specialized agent for Nancy's own roster. Generate a COMPLETE, "
        "working Python module defining a class that subclasses SpecializedAgent "
        "(from agents.specialized.base_specialized_agent import SpecializedAgent). Contract: "
        "__init__(self, settings) must call "
        "super().__init__(settings, '<Agent Display Name>', '<domain-slug>'); you MUST implement "
        "'async def process_task(self, task_data: dict) -> dict' handling at least "
        "task_data.get('type') == 'query' using task_data.get('query', ''), returning a dict with "
        "at least {'success': bool, ...}. Keep the agent self-contained (computation, text "
        "generation, data transformation) -- do not use subprocess, eval, exec, sockets, ctypes, "
        "or other unrestricted system access; that code will be statically rejected. This also "
        "requires the user's explicit approval before anything is saved, and only takes effect "
        "after the backend is restarted -- it does not go live immediately."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "lowercase_snake_case identifier, e.g. 'weather_forecaster'"},
            "class_name": {"type": "string", "description": "PascalCase class name, e.g. 'WeatherForecasterAgent'"},
            "domain": {"type": "string", "description": "human-readable domain slug, e.g. 'weather-forecasting'"},
            "description": {"type": "string", "description": "one-sentence description of what this agent does"},
            "code": {"type": "string", "description": "the complete Python module source code"},
        },
        "required": ["key", "class_name", "domain", "description", "code"],
    },
}


async def _execute_file_tool(name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    if name == "create_subagent":
        return await _execute_create_subagent_tool(tool_input)

    if name in _FILE_WRITE_TOOLS:
        description = {
            "write_file": f"Write to file: {tool_input.get('path')}",
            "delete_file": f"Delete: {tool_input.get('path')}",
            "move_file": f"Move {tool_input.get('src')} -> {tool_input.get('dst')}",
        }[name]
        approved = await telegram_notifier.request_approval(
            f"Nancy wants to: {description}", timeout=120.0
        )
        if not approved:
            return {"success": False, "error": "User did not approve this file operation."}

    if name == "read_file":
        return file_access.read_file(tool_input["path"])
    if name == "list_directory":
        return file_access.list_directory(tool_input["path"])
    if name == "write_file":
        return file_access.write_file(tool_input["path"], tool_input["content"])
    if name == "delete_file":
        return file_access.delete_file(tool_input["path"])
    if name == "move_file":
        return file_access.move_file(tool_input["src"], tool_input["dst"])
    return {"success": False, "error": f"Unknown tool {name}"}


async def _execute_create_subagent_tool(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    key = str(tool_input.get("key", ""))
    class_name = str(tool_input.get("class_name", ""))
    domain = str(tool_input.get("domain", ""))
    description = str(tool_input.get("description", ""))
    code = str(tool_input.get("code", ""))

    validation = subagent_factory.validate_agent_code(key, class_name, code)
    if not validation["ok"]:
        return {"success": False, "error": validation["error"]}

    preview = code[:1200] + ("...(truncated)" if len(code) > 1200 else "")
    approved = await telegram_notifier.request_approval(
        f"Nancy wants to create a new agent:\n\n"
        f"Key: {key}\nClass: {class_name}\nDomain: {domain}\nDescription: {description}\n\n"
        f"Code preview:\n{preview}\n\n"
        f"Passed static safety checks (valid syntax, correct base class, no "
        f"subprocess/eval/exec/sockets). Will NOT be active until you approve here AND "
        f"the backend is restarted.",
        timeout=300.0,
    )
    if not approved:
        return {"success": False, "error": "User did not approve creating this agent."}

    result = subagent_factory.write_agent_file(key, code)
    if result.get("success"):
        await telegram_notifier.send(
            f"Created agent '{key}' at {result['path']}. Restart the backend to bring it online."
        )
    return result


async def _generate_response_via_hierarchy(user_text: str) -> tuple[str, dict]:
    """Route a chat message to a real specialized agent when the text clearly
    matches one of the 29 registered domains; otherwise fall back to the
    general-purpose LLM.

    The previous implementation imported `orchestration.integration.run_nancy_hierarchy`,
    whose relative imports fail at runtime (`from ..llm import ...` outside package
    context) — every call silently hit the except branch below and fell back to a
    bare LLM call, so the "hierarchy" never actually ran. This now uses
    `agent_service`, the genuinely working 29-agent runtime (already exercised via
    the `/agents/run` and `/agents/auto` endpoints), with the same keyword-routing
    table `auto_run` uses — but only delegates on an actual keyword match, so plain
    conversational text isn't forced onto the "research" agent as `auto_run`'s own
    fallback does.
    """
    history_text = _history_to_text()

    if agent_service.is_ready():
        try:
            from agents.agent_service import _auto_route
            routed_key = _auto_route(user_text)
        except Exception:
            routed_key = None

        if routed_key:
            try:
                result = await agent_service.run(
                    routed_key,
                    {"type": "query", "query": user_text, "context": history_text},
                    timeout=30.0,
                )
                response_text = result.get("response") or result.get("result")
                if response_text and result.get("success", True) is not False:
                    return str(response_text), {
                        "routed_to": routed_key,
                        "agents_used": result.get("agents_used", [routed_key]),
                    }
                logger.warning(
                    "Agent '%s' returned no usable response (%s); falling back to LLM",
                    routed_key, result.get("error", "no error given"),
                )
            except Exception as e:
                logger.warning("Specialized agent '%s' failed, falling back to LLM: %s", routed_key, e)

    prompt = f"{BASE_SYSTEM_PROMPT}\n\n{_live_system_context()}\n\n{history_text}\nuser: {user_text}\nassistant:"

    # File access (read/list/write/delete/move real files on this computer,
    # per this session's explicit scope: no folder sandbox, writes/deletes
    # gated on a real Telegram approval) only works through Claude's native
    # tool-use -- the other backends in the fallback chain are plain text
    # completion with no tool-calling loop. Try that path first when
    # Anthropic is configured; anything that fails (including "no credits")
    # falls through to the ordinary no-tools chain below.
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            claude = AnthropicLLM()
            resp = await claude.generate_with_tools(
                prompt, FILE_TOOLS + [CREATE_SUBAGENT_TOOL], _execute_file_tool, max_tokens=1024
            )
            return resp, {"tool_use": True}
        except Exception as e:
            logger.warning("Claude tool-use path failed, falling back to plain chain: %s", e)

    try:
        resp = await llm_backend.generate(prompt, max_tokens=512, temperature=0.7)
    except Exception as llm_e:
        resp = f"I'm having trouble processing that right now. ({llm_e})"
    return resp, {}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class AgentRunRequest(BaseModel):
    agent_key: str
    task_type: str
    payload: Dict[str, Any] = {}
    timeout: float = 60.0

class AgentAutoRequest(BaseModel):
    text: str
    timeout: float = 60.0

class ChatRequest(BaseModel):
    text: str
    history: list = []
    task_hint: str | None = None  # e.g., "coding", "fast_response", "general", "multimodal"

class SynthesizeRequest(BaseModel):
    text: str


# ---------------------------------------------------------------------------
# REST routes — Core
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return HTMLResponse("<h1>Nancy/Billion Backend v2 — online</h1>")

@app.get("/test")
async def test():
    return {"message": "test ok", "agents_ready": agent_service.is_ready()}


# ---------------------------------------------------------------------------
# Startup & Greeting endpoints
# ---------------------------------------------------------------------------

@app.get("/startup")
async def startup_sequence():
    """Get Nancy's startup sequence"""
    sequence = startup_coordinator.start_up()
    return {
        "success": True,
        **sequence
    }


@app.get("/greeting")
async def get_greeting():
    """Get current greeting from Nancy"""
    greeting = startup_coordinator.greeting
    return {
        "success": True,
        "persona": startup_coordinator.persona,
        "boot_message": greeting.get_boot_message(),
        "ready_message": greeting.get_ready_message(),
        "context_aware_greeting": greeting.get_context_aware_greeting()
    }


@app.post("/persona/{persona_name}")
async def set_persona(persona_name: str):
    """Change Nancy's persona"""
    valid_personas = ["nancy", "billion", "jarvis"]

    if persona_name.lower() not in valid_personas:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid persona. Choose from: {', '.join(valid_personas)}"
        )

    startup_coordinator.set_persona(persona_name)

    greeting = startup_coordinator.greeting
    logger.info(f"Persona changed to: {persona_name}")

    return {
        "success": True,
        "persona": startup_coordinator.persona,
        "greeting": greeting.get_ready_message()
    }


async def _build_real_personal_context() -> "PersonalContext":
    """Populate PersonalContext from Nancy's actual data sources instead of
    the hardcoded demo data in intelligent_greeting.py's own __main__ block
    (that demo is exactly the "Docker build"/"Roxan deployment" example
    text -- illustrative of the tone, not real data). No calendar/meetings
    integration exists, so meetings_today is intentionally always empty
    rather than fabricated. Every other field is best-effort: any source
    that errors or has nothing to report is just omitted, not faked.
    """
    market_alerts: list = []
    for pair in ("EUR/USD", "GBP/USD"):
        try:
            snapshot = await forex_aggregator.get_price(pair)
            if snapshot:
                direction = "up" if snapshot.change_24h > 0 else "down" if snapshot.change_24h < 0 else "flat"
                market_alerts.append(
                    f"{pair} is trading at {snapshot.price:.4f}, {direction} {abs(snapshot.change_24h):.2f}% on the day"
                )
        except Exception as e:
            logger.debug("Greeting: market data unavailable for %s: %s", pair, e)

    project_updates: list = []
    try:
        for p in memory_manager.get_project_context()[:2]:
            name = p.get("name") or p.get("project") or "a project"
            project_updates.append(f"{name} is active in memory")
    except Exception as e:
        logger.debug("Greeting: project context unavailable: %s", e)

    active_trades: list = []
    try:
        open_trades = [t for t in trading_manager.trades if t.status == "open"]
        active_trades = [f"{t.pair} {t.direction} @ {t.entry_price}" for t in open_trades]
    except Exception as e:
        logger.debug("Greeting: trade data unavailable: %s", e)

    tasks_due: list = []
    try:
        si_result = await agent_service.run("self_improvement", {"type": "status"}, timeout=5.0)
        pending = si_result.get("pending_proposals", 0)
        if pending:
            tasks_due.append(f"{pending} self-improvement proposal{'s' if pending != 1 else ''} awaiting your approval")
    except Exception as e:
        logger.debug("Greeting: self-improvement status unavailable: %s", e)

    return PersonalContext(
        meetings_today=[],  # no calendar integration -- honestly empty, not fabricated
        build_status=None,  # no CI/build system integration exists
        market_alerts=market_alerts,
        project_updates=project_updates,
        active_trades=active_trades,
        tasks_due=tasks_due,
    )


@app.post("/greeting/personalized")
async def get_personalized_greeting(payload: Dict = None):
    """
    Get Nancy's intelligent personalized greeting, built from real data:
    live forex rates, memory/projects, open trades, and pending
    self-improvement proposals. No meetings/build-status fields are
    fabricated -- those sources (calendar, CI) aren't connected, so they're
    honestly omitted rather than invented.

    Optional request body fields override/extend the real-data context
    (e.g. to add a meeting once a calendar integration exists).
    """
    context = await _build_real_personal_context()

    overrides = payload or {}
    if overrides.get("meetings_today"):
        context.meetings_today = overrides["meetings_today"]
    if overrides.get("build_status"):
        context.build_status = overrides["build_status"]
    context.market_alerts = overrides.get("market_alerts") or context.market_alerts
    context.project_updates = overrides.get("project_updates") or context.project_updates
    context.active_trades = overrides.get("active_trades") or context.active_trades
    context.tasks_due = overrides.get("tasks_due") or context.tasks_due

    coordinator = IntelligentStartupCoordinator(persona=startup_coordinator.persona)
    startup_data = await coordinator.startup_with_context(context)

    logger.info(f"Generated personalized greeting for {len(context.meetings_today)} "
               f"meetings, {len(context.market_alerts)} market alerts, "
               f"{len(context.project_updates)} project updates")

    return {
        "success": True,
        **startup_data
    }


@app.post("/context/analyze")
async def analyze_context(payload: ChatRequest):
    """Analyze user input and return context/intent information (DEBUG endpoint)."""
    brain_decision = nancy_brain.process_input(payload.text)
    return {
        "input": payload.text,
        "intent": brain_decision['intent'],
        "confidence": brain_decision['confidence'],
        "should_show_map": brain_decision['should_use_map'],
        "routing_hints": brain_decision['routing_hints'],
        "active_topics": nancy_brain.context.active_topics,
    }


# ---------------------------------------------------------------------------
# Memory API endpoints
# ---------------------------------------------------------------------------

@app.get("/memory/summary")
async def memory_summary():
    """Get summary of Nancy's memory state"""
    summary = memory_manager.get_memory_summary()
    return {
        "success": True,
        "memory": summary
    }


@app.post("/memory/query")
async def memory_query(payload: ChatRequest):
    """Search Nancy's memories for relevant information"""
    if not payload.text:
        raise HTTPException(status_code=400, detail="Query text required")

    memories = memory_manager.get_relevant_memories(payload.text, top_k=10)

    return {
        "success": True,
        "query": payload.text,
        "memories": memories,
        "count": len(memories)
    }


@app.get("/memory/projects")
async def get_projects():
    """Get all projects Nancy remembers"""
    projects = memory_manager.get_project_context()
    return {
        "success": True,
        "projects": projects,
        "count": len(projects)
    }


@app.get("/memory/trades")
async def get_trades():
    """Get trade history from Nancy's memory"""
    trades = memory_manager.get_trade_history(limit=50)
    return {
        "success": True,
        "trades": trades,
        "count": len(trades)
    }


# ---------------------------------------------------------------------------
# Trading Intelligence API endpoints
# ---------------------------------------------------------------------------

@app.post("/trading/analyze", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def analyze_pair(payload: ChatRequest):
    """Analyze a forex pair with technical analysis"""
    if not payload.text:
        raise HTTPException(status_code=400, detail="Pair name required")

    # Extract pair from text (e.g., "EUR/USD" or "What about EUR/USD")
    pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD"]
    pair = None
    for p in pairs:
        if p.upper() in payload.text.upper():
            pair = p
            break

    if not pair:
        raise HTTPException(status_code=400, detail="Forex pair not found in request")

    # Get market data
    snapshot = await forex_aggregator.get_price(pair)
    historical = await forex_aggregator.get_historical(pair)

    if not snapshot:
        raise HTTPException(status_code=400, detail=f"Could not get data for {pair}")

    # Perform analysis
    analysis = analysis_engine.analyze(pair, snapshot, historical)

    # Get recommendation
    rec = strategy_advisor.get_recommendation(analysis)

    return {
        "success": True,
        "pair": pair,
        "price": snapshot.price,
        "analysis": analysis.to_dict(),
        "recommendation": rec
    }


@app.get("/trading/recommendation/{pair}")
async def get_trading_recommendation(pair: str):
    """Get trading recommendation for a pair"""
    snapshot = await forex_aggregator.get_price(pair)
    if not snapshot:
        raise HTTPException(status_code=400, detail=f"Could not get data for {pair}")

    historical = await forex_aggregator.get_historical(pair)
    analysis = analysis_engine.analyze(pair, snapshot, historical)
    recommendation = strategy_advisor.get_recommendation(analysis)

    return {
        "success": True,
        "pair": pair,
        "recommendation": recommendation
    }


@app.get("/trading/risk-assessment")
async def assess_trading_risk():
    """Assess overall trading risk"""
    trades = trading_manager.trades
    risk_assessment = risk_monitor.assess_risk([
        {
            "risk_amount": t.profit_loss or 0,
            "result": "win" if (t.profit_loss or 0) > 0 else "loss"
        }
        for t in trades if t.status == "closed"
    ])

    return {
        "success": True,
        "risk_assessment": risk_assessment
    }


@app.post("/trading/record-trade", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def record_trade(payload: Dict):
    """Record a new trade"""
    pair = payload.get("pair")
    direction = payload.get("direction")  # BUY or SELL
    entry_price = payload.get("entry_price")
    quantity = payload.get("quantity", 1.0)
    notes = payload.get("notes", "")

    if not all([pair, direction, entry_price]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    trade = trading_manager.record_trade(pair, direction, entry_price, quantity, notes)

    # Store in memory
    memory_manager.graph.add_memory(
        f"Opened {direction} trade on {pair} @ {entry_price}",
        MemoryType.TRADE,
        {"pair": pair, "direction": direction, "entry": entry_price},
        importance=0.8
    )

    return {
        "success": True,
        "trade": {
            "pair": trade.pair,
            "direction": trade.direction,
            "entry_price": trade.entry_price,
            "quantity": trade.quantity,
            "status": trade.status
        }
    }


@app.get("/trading/performance")
async def get_trading_performance():
    """Get trading performance metrics"""
    metrics = trading_manager.get_performance_metrics()

    return {
        "success": True,
        "metrics": metrics,
        "recommendation": trading_manager._get_trading_recommendation(metrics)
    }


@app.get("/trading/history")
async def get_trading_history(pair: str = None, limit: int = 50):
    """Get trading history"""
    trades = trading_manager.get_trade_history(pair=pair, limit=limit)

    return {
        "success": True,
        "trades": [
            {
                "pair": t.pair,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "profit_loss": t.profit_loss,
                "status": t.status,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time
            }
            for t in trades
        ],
        "count": len(trades)
    }


@app.get("/trading/report")
async def get_trading_report():
    """Get comprehensive trading report"""
    report = trading_manager.generate_trading_report()

    return {
        "success": True,
        "report": report
    }


@app.post("/chat", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def chat_endpoint(payload: ChatRequest):
    """Primary chat endpoint with intelligent context-aware routing.

    Uses NancyContextualBrain to:
    - Understand user intent (NOT confuse weather with map!)
    - Select appropriate LLM based on task
    - Route to correct handler
    - Maintain conversation context

    Supports task_hint to route to specialized LLMs:
    - "coding" → Claude (Anthropic)
    - "fast_response" → Groq (speed optimized)
    - "multimodal" → Gemini
    - None / "general" → Uses full fallback chain (Ollama → Anthropic → Groq → OpenAI → etc.)
    """
    text = payload.text
    if not text:
        raise HTTPException(status_code=400, detail="Missing text")

    # Process input through Nancy's brain for intelligent routing
    brain_decision = nancy_brain.process_input(text)

    logger.info(f"User intent: {brain_decision['intent']} (confidence: {brain_decision['confidence']:.2f})")
    logger.info(f"Routing hints: {brain_decision['routing_hints']}")

    # Determine if we should show map (NOT for weather, research, etc!)
    should_show_map = brain_decision['should_use_map'] and brain_decision['confidence'] > 0.7

    prompt_lines = []
    for msg in payload.history:
        if isinstance(msg, dict):
            prompt_lines.append(f"{msg.get('role','user')}: {msg.get('content','')}")
    prompt_lines.append(f"user: {text}")
    prompt_lines.append("assistant:")
    prompt = "\n".join(prompt_lines)

    try:
        # Extract memories from conversation
        memory_manager.extract_memories_from_conversation()

        # Select LLM based on task hint or detected intent
        task_hint = payload.task_hint
        if not task_hint and brain_decision['intent'] == IntentType.TRADING.value:
            task_hint = "trading"
            logger.debug("Auto-detected trading task")
        elif not task_hint and brain_decision['intent'] == IntentType.CODING.value:
            task_hint = "coding"
            logger.debug("Auto-detected coding task")

        # Augment prompt with relevant memories
        augmented_prompt = memory_manager.augment_prompt_with_memory(prompt)

        selected_llm = select_llm_for_task(task_hint)
        logger.info(f"Chat endpoint using LLM: {selected_llm.__class__.__name__} (intent: {brain_decision['intent']}, task_hint: {task_hint})")

        # Coding/self-improvement tasks get Claude with adaptive-thinking effort
        # cranked up — select_llm_for_task() already routes "coding" hints to
        # AnthropicLLM; this adds the effort param that class actually knows how
        # to use (other backends don't accept it, hence the isinstance guard).
        from llm import AnthropicLLM
        if isinstance(selected_llm, AnthropicLLM) and task_hint in ("coding", "self_improvement", "devops"):
            response = await selected_llm.generate(augmented_prompt, max_tokens=2048, temperature=0.7, effort="high")
        else:
            response = await selected_llm.generate(augmented_prompt, max_tokens=512, temperature=0.7)

        # Record response in context
        nancy_brain.add_response(response)

        # Learn from this exchange
        memory_manager.learn_from_response(text, response)

    except Exception as e:
        logger.exception("LLM generation failed: %s", e)
        response = "My apologies, I encountered an error while processing your request."

    return {
        "reply": response.strip(),
        "action": "locate" if should_show_map else "none",  # Only show map for actual map requests!
        "category": None,
        "topic": None,
        "symbol": None,
        "panel": "map" if should_show_map else None,  # Don't show map for weather!
        "target": None,
        "media": "articles",
        "autoOpenTop": False,
        "intent": brain_decision['intent'],
        "confidence": brain_decision['confidence'],
    }


# ---------------------------------------------------------------------------
# REST routes — Specialized Agents
# ---------------------------------------------------------------------------

@app.get("/agents/list")
async def list_agents():
    """Return all 29 specialized agents with live status."""
    agents = agent_service.list_agents()
    stats  = agent_service.get_service_stats()
    return {
        "success": True,
        "agents":  agents,
        "stats":   stats,
        "total":   len(agents),
    }


@app.get("/agents/stats")
async def agent_stats():
    return {"success": True, **agent_service.get_service_stats()}


@app.get("/agents/{agent_key}/status")
async def agent_status(agent_key: str):
    """Full status for a single agent."""
    status = agent_service.get_agent_status(agent_key)
    return {"success": True, "agent_key": agent_key, "status": status}


@app.get("/system/health")
async def system_health():
    """Real psutil-backed system health (CPU/memory/disk/network/temperature).

    SystemMonitor already existed (system_monitor.py) but was never wired to any
    route — the frontend's Overview/System panels showed Math.random()-jittered
    fake CPU/memory numbers instead. cpu_percent(interval=1) blocks for ~1s, so
    it's run in a thread to avoid blocking the event loop.
    """
    loop = asyncio.get_event_loop()
    health = await loop.run_in_executor(None, system_monitor.get_comprehensive_health)
    return {"success": True, **health}


@app.get("/clap/status")
async def clap_status():
    """Whether the clap-detection model (satellite repo ../../clap-detection-main)
    is loaded and ready. That repo ships no pretrained weights, so this is False
    on a fresh checkout until CLAP_MODEL_PATH is pointed at a real .pth file —
    see clap_detection.py for the honest error this reports until then.
    """
    loop = asyncio.get_event_loop()
    status = await loop.run_in_executor(None, lambda: clap_detector.status)
    return {"success": True, **status}


@app.get("/tts/status")
async def tts_status():
    """Whether TTS is using the real neural voice (NeuTTS-nano) and which
    reference clip it cloned from ("user" vs "synthetic-placeholder") — see
    neu_tts.py. Falls back to a generic status if TTS_BACKEND=pyttsx3.
    """
    if not isinstance(tts_backend, NeuTTSBackend):
        return {"success": True, "available": True, "voice_source": "pyttsx3", "error": None}
    loop = asyncio.get_event_loop()
    # Access the `status` property inside the executor -- it's a property, so
    # even `getattr`/`hasattr` on it would trigger the (possibly slow, first-load)
    # getter synchronously on the event loop thread if called outside one.
    status = await loop.run_in_executor(None, lambda: tts_backend.status)
    return {"success": True, **status}


@app.get("/telegram/status")
async def telegram_status():
    """Whether Telegram is configured and the reply-polling loop is running —
    see telegram_bot.py. TelegramNotifier's status is a plain attribute (not
    a property doing I/O), so no executor offload is needed here."""
    return {"success": True, **telegram_notifier.status}


@app.post("/tts/synthesize")
async def tts_synthesize(req: SynthesizeRequest):
    """Synthesize arbitrary text to speech. Used for locally-generated spoken
    lines (nav confirmations, greetings, etc.) that never go through the chat
    WebSocket's own tts_audio push.
    """
    try:
        wav_bytes = await tts_backend.synthesize(req.text)
    except Exception as e:
        logger.exception("TTS synthesis failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
    return Response(content=wav_bytes, media_type="audio/wav")


@app.post("/agents/run", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def run_agent(req: AgentRunRequest):
    """
    Run a specific agent with a typed task payload.

    Example:
        POST /agents/run
        {
          "agent_key": "quantum_reasoning",
          "task_type": "qrng",
          "payload": {"n_bits": 256}
        }
    """
    if not agent_service.is_ready():
        raise HTTPException(status_code=503, detail="AgentService not yet initialised")

    task_data = {"type": req.task_type, **req.payload}
    started = _time.monotonic()
    result = await agent_service.run(req.agent_key, task_data, timeout=req.timeout)
    await _notify_if_long_running(f"agent '{req.agent_key}' ({req.task_type})", started, result)
    _maybe_gate_self_improvement(req.agent_key, result)
    return result


@app.post("/agents/auto", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def auto_route_agent(req: AgentAutoRequest):
    """
    Auto-route a natural-language query to the best specialist agent.

    Example:
        POST /agents/auto
        {"text": "generate a 256-bit quantum random number"}
    """
    if not agent_service.is_ready():
        raise HTTPException(status_code=503, detail="AgentService not yet initialised")

    started = _time.monotonic()
    result = await agent_service.auto_run(req.text, timeout=req.timeout)
    await _notify_if_long_running(f"auto-routed task: {req.text[:80]}", started, result)
    _maybe_gate_self_improvement(result.get("agent_key", ""), result)
    return result


# Legacy HTTP agent runner (Fury-based)
@app.post("/agent/run")
async def run_fury_agent(payload: dict):
    """Run a Fury registry agent by key (legacy endpoint)."""
    agent_key  = payload.get("agent_key")
    input_text = payload.get("input_text")
    if not agent_key or input_text is None:
        return {"error": "Missing required fields: agent_key, input_text"}
    try:
        out = await fury_run_agent(
            agent_key=agent_key,
            input_text=str(input_text),
            max_tokens=int(payload.get("max_tokens", 512)),
            temperature=float(payload.get("temperature", 0.7)),
        )
        return {"agent_key": agent_key, "output": out}
    except Exception as e:
        return {"agent_key": agent_key, "error": str(e)}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket(os.getenv("WS_PATH", "/ws"))
async def websocket_endpoint(websocket: WebSocket):
    # WebSocket auth: HTTPException-based Depends() doesn't apply to WS routes,
    # so check the same shared-secret manually (no-op unless BACKEND_AUTH_TOKEN
    # is set). Pass ?token=... on the connection URL.
    if _BACKEND_AUTH_TOKEN and websocket.query_params.get("token") != _BACKEND_AUTH_TOKEN:
        await websocket.close(code=4401)
        return
    client_ip = websocket.client.host if websocket.client else "unknown"
    if not _rate_limiter.check(client_ip):
        await websocket.close(code=4429)
        return
    await manager.connect(websocket)
    try:
        while True:
            data    = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")

            # ---- Audio chunk (STT) ----
            if msg_type == "audio_chunk":
                audio_b64 = message.get("data")
                if audio_b64:
                    try:
                        if np is not None:
                            decoded  = decode_webm_opus_b64_to_pcm(
                                audio_b64,
                                target_sample_rate=int(os.getenv("STT_SAMPLE_RATE", "16000")),
                            )
                            audio_np = pcm_int16_to_float32(decoded.pcm_int16)
                        else:
                            audio_bytes = base64.b64decode(audio_b64)
                            import array as _arr
                            raw = _arr.array("h", audio_bytes)
                            audio_np = [s / 32768.0 for s in raw]
                    except Exception:
                        audio_bytes = base64.b64decode(audio_b64)
                        audio_np = [s / 32768.0 for s in audio_bytes]

                    transcript = await stt_backend.transcribe_chunk(audio_np)
                    if transcript:
                        await manager.send(
                            json.dumps({"type": "transcript", "data": transcript}),
                            websocket,
                        )

            # ---- Audio chunk (clap detection) ----
            elif msg_type == "clap_chunk":
                audio_b64 = message.get("data")
                if audio_b64:
                    loop = asyncio.get_event_loop()
                    # status (and the torch/model load it triggers on first call) runs in
                    # a thread so a cold load can't freeze every other WS client's event loop.
                    clap_status = await loop.run_in_executor(None, lambda: clap_detector.status)
                    if not clap_status["available"]:
                        await manager.send(
                            json.dumps({"type": "clap_error", "error": clap_status["error"]}),
                            websocket,
                        )
                    else:
                        try:
                            decoded = decode_webm_opus_b64_to_pcm(
                                audio_b64,
                                target_sample_rate=int(os.getenv("CLAP_SAMPLE_RATE", "44100")),
                            )
                            audio_np = pcm_int16_to_float32(decoded.pcm_int16)
                            result = await loop.run_in_executor(None, clap_detector.predict, audio_np)
                            threshold = float(os.getenv("CLAP_DETECT_THRESHOLD", "0.6"))
                            await manager.send(
                                json.dumps({
                                    "type": "clap_result",
                                    "is_clap": result.is_clap and result.confidence > threshold,
                                    "confidence": result.confidence,
                                }),
                                websocket,
                            )
                        except Exception as e:
                            logger.exception("Clap detection error: %s", e)
                            await manager.send(
                                json.dumps({"type": "clap_error", "error": str(e)}),
                                websocket,
                            )

            # ---- Final transcript / user text ----
            elif msg_type in ("final_transcript", "user_text"):
                text = message.get("data", "")
                logger.info("Received %s: %s", msg_type, text[:80])

                if history_manager:
                    await history_manager.add({"role": "user", "content": text})

                response, debug_payload = await _generate_response_via_hierarchy(text)

                if history_manager:
                    await history_manager.add({"role": "assistant", "content": response})

                await manager.send(
                    json.dumps({
                        "type":  "agent_response",
                        "data":  response,
                        "debug": debug_payload,
                    }),
                    websocket,
                )

                # TTS
                try:
                    audio_wav = await tts_backend.synthesize(response)
                    if audio_wav:
                        await manager.send(
                            json.dumps({
                                "type": "tts_audio",
                                "data": base64.b64encode(audio_wav).decode(),
                            }),
                            websocket,
                        )
                except Exception as e:
                    logger.error("TTS error: %s", e)

            # ---- Specialized Python agent task (new) ----
            elif msg_type == "run_specialized_task":
                """
                Run one of the 29 Python specialized agents directly.
                Message format:
                {
                    "type":       "run_specialized_task",
                    "agent_key":  "quantum_reasoning",
                    "task_type":  "qrng",
                    "payload":    {"n_bits": 128},
                    "request_id": "abc123"   (optional, echoed back)
                }
                """
                agent_key  = message.get("agent_key", "")
                task_type  = message.get("task_type", "query")
                payload    = message.get("payload", {})
                request_id = message.get("request_id")

                if not agent_key:
                    await manager.send(
                        json.dumps({"type": "agent_error", "error": "Missing agent_key", "request_id": request_id}),
                        websocket,
                    )
                    continue

                task_data = {"type": task_type, **payload}

                try:
                    result = await agent_service.run(agent_key, task_data, timeout=60.0)
                    await manager.send(
                        json.dumps({
                            "type":       "agent_result",
                            "agent_key":  agent_key,
                            "request_id": request_id,
                            "result":     result,
                        }),
                        websocket,
                    )
                except Exception as e:
                    logger.exception("WS specialized task error: %s", e)
                    await manager.send(
                        json.dumps({
                            "type":       "agent_error",
                            "agent_key":  agent_key,
                            "request_id": request_id,
                            "error":      str(e),
                        }),
                        websocket,
                    )

            # ---- Auto-route NL to best agent ----
            elif msg_type == "auto_route_task":
                """
                {
                    "type": "auto_route_task",
                    "text": "generate a quantum random number",
                    "request_id": "xyz"
                }
                """
                text       = message.get("text", "")
                request_id = message.get("request_id")
                try:
                    result = await agent_service.auto_run(text, timeout=60.0)
                    await manager.send(
                        json.dumps({
                            "type":       "agent_result",
                            "request_id": request_id,
                            "result":     result,
                        }),
                        websocket,
                    )
                except Exception as e:
                    await manager.send(
                        json.dumps({"type": "agent_error", "error": str(e), "request_id": request_id}),
                        websocket,
                    )

            # ---- Legacy Fury agent runner ----
            elif msg_type in ("run_agent", "run_specialized_agent"):
                agent_key  = message.get("agent_key")
                input_text = message.get("input_text", "")
                if not agent_key:
                    await manager.send(
                        json.dumps({"type": "agent_error", "data": "Missing agent_key"}),
                        websocket,
                    )
                    continue
                try:
                    out = await fury_run_agent(
                        agent_key=str(agent_key),
                        input_text=str(input_text),
                        max_tokens=int(message.get("max_tokens", 512)),
                        temperature=float(message.get("temperature", 0.7)),
                    )
                    await manager.send(
                        json.dumps({"type": "agent_response", "data": out}),
                        websocket,
                    )
                except Exception as e:
                    await manager.send(
                        json.dumps({"type": "agent_error", "data": str(e)}),
                        websocket,
                    )

            elif msg_type == "ping":
                await manager.send(json.dumps({"type": "pong"}), websocket)

            else:
                logger.warning("Unknown WS message type: %s", msg_type)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.exception("WebSocket error: %s", e)
        manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Startup / Shutdown
# ---------------------------------------------------------------------------

async def _telegram_chat_handler(text: str) -> str:
    """Routes a Telegram message through the same chat pipeline the voice/web
    UI uses, so 'chat with Billion from Telegram' means the same Billion --
    same context history, same agent routing, same LLM fallback chain."""
    response, _debug = await _generate_response_via_hierarchy(text)
    if history_manager:
        await history_manager.add({"role": "user", "content": f"[telegram] {text}"})
        await history_manager.add({"role": "assistant", "content": response})
    return response


@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()
    logger.info("Nancy/Billion backend starting up…")
    # Initialise all 29 specialized agents in background so startup is fast
    asyncio.create_task(_init_agents())
    telegram_notifier.set_chat_handler(_telegram_chat_handler)
    telegram_notifier.start_polling()


async def _init_agents():
    try:
        await agent_service.initialize(settings=None)
        stats = agent_service.get_service_stats()
        logger.info(
            "AgentService ready: %d online, %d offline.",
            stats["agents_online"], stats["agents_offline"],
        )
    except Exception as exc:
        logger.exception("AgentService init failed: %s", exc)


@app.on_event("shutdown")
async def shutdown_event():
    await agent_service.shutdown()
    await telegram_notifier.stop_polling()
    logger.info("Nancy/Billion backend shut down.")


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=False,
    )
