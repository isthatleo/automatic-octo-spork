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
import re
import hmac
import hashlib
import threading
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
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
import terminal_tool
import skill_loader
from mcp_client import mcp_manager, plugin_store
from moa import run_moa
from inbound_webhooks_store import inbound_webhook_store
from canvas_store import canvas_store
from blueprint_catalog import CATALOG as BLUEPRINT_CATALOG, get_blueprint, blueprint_catalog_entry, fill_blueprint, BlueprintFillError
from skill_bundles import skill_bundle_store
import run_script_tool
from web_tool import fetch_url, web_search, extract_urls, WEB_TOOLS
from providers.bootstrap import load_all_providers
from channels.bootstrap import load_all_channels
import security_lint
import arm_switch
from llm_task import structured_llm_call, UTILITY_TOOLS
from workspace_uri import resolve_oc_path
from backup_tool import create_backup, list_backups, BACKUP_TOOLS
from disk_cleanup import ensure_bootstrap_script
from channels.home_assistant import HOME_ASSISTANT_TOOLS
from providers.spotify_tool import SPOTIFY_TOOLS, handle_spotify_tool
from memory import wiki_store, commitments
import evidence_ledger
import lifecycle_hooks
import lsp_client
from diff_render import post_diff_to_canvas
import doc_extraction
import config_migration
import workflow_engine
from debug_share import share_debug_report
import node_host
import approval_policy
import egress_proxy
import coverage_proxy
import usage_analytics
import achievements_store

DIFF_TOOLS = [
    {
        "name": "show_diff",
        "description": "Render a real unified diff between two versions of text/code and post it to the shared canvas with syntax highlighting.",
        "input_schema": {
            "type": "object",
            "properties": {
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
                "title": {"type": "string"},
            },
            "required": ["old_text", "new_text", "title"],
        },
    },
]

NODE_TOOLS = [
    {
        "name": "node_execute_command",
        "description": (
            "Run a real shell command on a paired second machine (a 'node') instead of this "
            "computer. Requires the node to already be registered. Gated by a real allow-once/"
            "allow-always/deny policy -- first use of a new command pattern on a node requires the "
            "user's explicit yes/no approval on their phone."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "command": {"type": "string"},
                "cwd": {"type": "string"},
            },
            "required": ["node_id", "command"],
        },
    },
]

ensure_bootstrap_script()

load_all_providers()
load_all_channels()
import computer_use_tool
from computer_use_tool import COMPUTER_USE_TOOLS, ACTION_TOOLS as COMPUTER_ACTION_TOOLS
from tts import tts_backend
from neu_tts import NeuTTSBackend, USER_REF_WAV, USER_REF_TXT
from tools import get_tools
from wake_word import get_wake_word_detector
from audio_decode import decode_webm_opus_b64_to_pcm, pcm_int16_to_float32
from clap_detection import clap_detector
from telegram_bot import telegram_notifier
import telegram_pairing
from agents.agent_service import agent_service
from event_bus import event_bus
from missions_store import mission_store, MissionError
from context_manager import NancyContextualBrain, IntentType
from memory import MemoryManager, MemoryType
from cron_store import cron_store
from skills_store import skills_store
from webhooks_store import webhook_store, VALID_EVENTS
import economic_calendar
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

# CORS - explicit origins only. The previous config included "*" alongside
# named origins, which (a) makes the named origins meaningless and (b) is
# invalid per the CORS spec when combined with allow_credentials=True (browsers
# reject it). Configure NANCY_ALLOWED_ORIGINS as a comma-separated list for
# non-default deployments (e.g. LAN access) instead of adding "*" back.
_allowed_origins = [
    o.strip() for o in os.getenv(
        "NANCY_ALLOWED_ORIGINS",
        # 3005 is the actual `next dev -p 3005` port this project runs on;
        # 3000 kept for anyone running the frontend on Next's own default.
        "http://localhost:3005,http://127.0.0.1:3005,http://localhost:3000,http://127.0.0.1:3000",
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
_PROCESS_START_TIME = _time.time()  # real wall-clock start, for achievements_store's uptime check


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
        raise HTTPException(status_code=429, detail="Rate limit exceeded - slow down")

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
if not trading_manager.watched_pairs and not trading_manager.trades:
    # One-time seed of what the user actually told Nancy they trade --
    # after this, /trading/watched-pairs (or telling Nancy directly) is the
    # real way to change it; this only fires on a genuinely fresh install
    # (no watched pairs AND no trade history saved yet).
    trading_manager.set_watched_pairs(["XAU/USD", "GBP/USD", "XAG/USD"])

# Log Nancy's startup
logger.info("=" * 70)
logger.info("[done] NANCY/BILLION AI OPERATING SYSTEM STARTING")
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

Always address the user as "Sir" (always capitalized, even mid-sentence) -- naturally, the way a butler-style assistant (JARVIS) would, not stiffly or in every single sentence. Never use their name or any other title.

Calibrate the length and depth of every response to what was actually asked -- this matters doubly here since your replies are spoken aloud, and a long answer means a long wait before the user hears anything useful:
- A quick factual question ("what's the price of X", "what time is it", "is Y online") gets a direct answer in one or two sentences -- no preamble, no unrequested context, no restating the question.
- Casual conversation (greetings, small talk, a quick check-in) gets a short, natural, conversational reply -- not a report.
- A request for a definition or "what is X" gets a brief, precise explanation -- a paragraph at most, not an essay, unless asked to go deeper.
- Only give a longer, structured, multi-part answer when the user's request actually calls for it: they asked for a deep dive, a thorough explanation, a comparison, a plan, or explicitly asked for detail/an essay/"tell me everything about". If genuinely unsure whether they want brief or thorough, default to brief and offer to expand -- don't pre-emptively over-explain.
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
        # One in-flight chat "turn" per connection. A new user_text/final_transcript
        # cancels whatever turn is still running instead of queuing behind it --
        # this is real barge-in, and it's what makes a fresh message actually
        # supersede a slow reply instead of both eventually finishing and racing
        # each other for TTS playback.
        self._turn_tasks: Dict[WebSocket, "asyncio.Task"] = {}
        self._turn_counters: Dict[WebSocket, int] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket connected. Total: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        task = self._turn_tasks.pop(websocket, None)
        if task and not task.done():
            task.cancel()
        self._turn_counters.pop(websocket, None)
        logger.info("WebSocket disconnected. Total: %d", len(self.active_connections))

    async def send(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    def start_turn(self, websocket: WebSocket, coro_factory, turn_id=None) -> Any:
        """Cancel any in-flight turn for this connection and start a new one.
        `coro_factory(turn_id)` must return the coroutine to run. Returns the
        turn_id used. Fire-and-forget by design -- the caller's receive loop
        must stay free to read the next message immediately, not block on the
        LLM/TTS pipeline.

        `turn_id` should normally come from the client (it already knows
        which turn it's waiting on) so the id survives reconnects and doesn't
        depend on message-ordering assumptions; falls back to an internal
        counter if the client didn't send one."""
        prev = self._turn_tasks.get(websocket)
        if prev and not prev.done():
            prev.cancel()
        if turn_id is None:
            turn_id = self._turn_counters.get(websocket, 0) + 1
            self._turn_counters[websocket] = turn_id
        task = asyncio.create_task(coro_factory(turn_id))
        self._turn_tasks[websocket] = task
        return turn_id

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


async def _broadcast_domain_event(event_type: str, envelope: Dict[str, Any]) -> None:
    """Real-time projection of a real domain event to every connected
    browser tab -- see event_bus.py. This is the ONLY place a domain event
    turns into a WebSocket frame; publishers (AgentService, MissionStore
    callers below) never touch WebSockets directly."""
    await manager.broadcast(json.dumps(envelope))

event_bus.subscribe(_broadcast_domain_event)


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


async def _fire_webhooks(event: str, payload: Dict[str, Any]) -> None:
    """Real outbound delivery -- POSTs the event payload to every enabled
    webhook subscribed to it. Fire-and-forget: failures are recorded on the
    subscription (last_status) but never raised, since a broken third-party
    endpoint must not break the real event that triggered this."""
    hooks = webhook_store.for_event(event)
    if not hooks:
        return
    body = {"event": event, "fired_at": _time.time(), **payload}
    async with httpx.AsyncClient(timeout=10.0) as client:
        for hook in hooks:
            try:
                resp = await client.post(hook.url, json=body)
                webhook_store.mark_fired(hook.id, "ok" if resp.is_success else f"http_{resp.status_code}")
            except Exception as exc:
                webhook_store.mark_fired(hook.id, f"error: {exc}")


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
    parts = [
        "Live system status:",
        f"agents={len(agent_service._agents)}",
        f"skills={len(list(skills_store.list()))}",
        f"memory={len(getattr(memory_manager.graph, 'nodes', {}))}",
    ]
    try:
        summary = memory_manager.get_memory_summary()
        if isinstance(summary, dict):
            parts.append("memory_summary=" + ",".join(
                f"{k}={summary.get(k, 0)}" for k in ("total_memories", "projects", "trades", "recent_conversations")
            ))
    except Exception:
        pass
    try:
        stats = agent_service.get_service_stats()
        parts.append(f"tasks_done={stats.get('total_tasks')}")
        parts.append(f"success_rate={stats.get('success_rate')}")
    except Exception:
        pass
    return " ".join(parts)


def _live_context_bridge_context() -> str:
    context = get_live_context_snapshot()
    if not context:
        return ""
    parts = ["Live UI context:"]
    for key in ("active_panel", "panel", "active_suggestions", "channel", "source"):
        if key in context:
            parts.append(f"{key}={context[key]}")
    if context.get("environmental"):
        parts.append(f"environmental={context['environmental']}")
    return " | ".join(parts)


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
            "Create or overwrite a file on the user's computer -- source code just as much as "
            "plain text. ALWAYS give `path` a real extension matching the actual content: .py for "
            "Python, .js/.ts for JavaScript/TypeScript, .html, .css, .json, .sh, .md, .java, .cpp, "
            "etc. Only use .txt for genuine plain-language notes -- never as a generic default for "
            "code, or a Python script asked to run will fail to even execute. If the user didn't "
            "ask for a specific folder, just give a bare filename (e.g. 'calculator.py') and it "
            "will be saved to their Desktop automatically, so they can find and run it immediately. "
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

# Real-world safety net for write_file: a real bug this session was Claude
# happily writing runnable Python source out to a bare "calculator.txt" --
# the tool description above now tells it not to, but LLMs miss instructions,
# so this is a second, code-level guarantee that a file's extension actually
# matches its content before it ever touches disk. Ordered so the earliest
# confident match wins; deliberately conservative (only fires on missing or
# clearly-generic ".txt"/no extension) so it never fights an extension the
# caller picked on purpose.
_EXT_SNIFF_RULES: List[tuple] = [
    (re.compile(r'^#!.*\bpython'), ".py"),
    (re.compile(r'^#!.*\b(bash|sh|zsh)\b'), ".sh"),
    (re.compile(r'^#!.*\bnode\b'), ".js"),
    (re.compile(r'<!DOCTYPE html|<html[ >]', re.I), ".html"),
    (re.compile(r'^\s*(import\s+\w|from\s+\w+\s+import\b)', re.M), ".py"),
    (re.compile(r'^\s*def\s+\w+\s*\(.*\)\s*:', re.M), ".py"),
    (re.compile(r'if\s+__name__\s*==\s*[\'"]__main__[\'"]\s*:'), ".py"),
    (re.compile(r'^\s*(public|private)\s+(static\s+)?(class|void)\b', re.M), ".java"),
    (re.compile(r'^\s*#include\s*<'), ".cpp"),
    (re.compile(r'\bconsole\.log\(|\brequire\(|=>\s*\{|\bconst\s+\w+\s*=|\blet\s+\w+\s*='), ".js"),
    (re.compile(r'^\s*(SELECT|INSERT INTO|CREATE TABLE|UPDATE)\b', re.I), ".sql"),
]


def _sniff_extension(content: str) -> Optional[str]:
    head = content[:2000]
    for pattern, ext in _EXT_SNIFF_RULES:
        if pattern.search(head):
            return ext
    stripped = content.strip()
    if stripped[:1] in "{[":
        try:
            json.loads(stripped)
            return ".json"
        except (ValueError, TypeError):
            pass
    return None


# Highest-confidence signal of all: the user's own words. If they said
# "python"/"bash"/"a json config"/etc., that names the file type they
# actually want, full stop -- more reliable than sniffing generated content
# (which can be ambiguous, e.g. a short snippet with no imports or keywords
# yet) and worth trusting over whatever extension Claude happened to pick.
# Ordered so more specific names (javascript/typescript) are safe to check
# before/after "java" without collision -- \b word boundaries mean "java"
# alone never matches inside "javascript" anyway.
_LANGUAGE_NAME_HINTS: List[tuple] = [
    (re.compile(r'\btypescript\b', re.I), ".ts"),
    (re.compile(r'\bjavascript\b', re.I), ".js"),
    (re.compile(r'\bpython\b', re.I), ".py"),
    (re.compile(r'\bhtml\b', re.I), ".html"),
    (re.compile(r'\bcss\b', re.I), ".css"),
    (re.compile(r'\b(bash|shell)\s*script\b|\bbash\b', re.I), ".sh"),
    (re.compile(r'\bjson\b', re.I), ".json"),
    (re.compile(r'\byaml\b|\byml\b', re.I), ".yaml"),
    (re.compile(r'\bjava\b', re.I), ".java"),
    (re.compile(r'c\+\+', re.I), ".cpp"),
    (re.compile(r'c#', re.I), ".cs"),
    (re.compile(r'\bgo(lang)?\b', re.I), ".go"),
    (re.compile(r'\brust\b', re.I), ".rs"),
    (re.compile(r'\bsql\b', re.I), ".sql"),
    (re.compile(r'\bmarkdown\b', re.I), ".md"),
    (re.compile(r'\bruby\b', re.I), ".rb"),
    (re.compile(r'\bphp\b', re.I), ".php"),
    (re.compile(r'\bcsv\b', re.I), ".csv"),
]


def _explicit_language_hint(user_text: str) -> Optional[str]:
    for pattern, ext in _LANGUAGE_NAME_HINTS:
        if pattern.search(user_text):
            return ext
    return None


def _resolve_write_path(raw_path: str, content: str, user_hint: str = "") -> Path:
    """Bare filename (no folder given) -> save to the real Desktop, not
    wherever the backend process happens to be running from. The file type
    the user actually asked for (user_hint) wins outright over whatever
    extension Claude picked; failing that, missing/generic ".txt" on content
    that's clearly real source gets corrected by sniffing the content itself.
    Together these mean "create a calculator in python" can never again land
    as an unrunnable calculator.txt, no matter which of the two signals
    catches it."""
    p = Path(resolve_oc_path(raw_path)).expanduser()
    if not p.is_absolute() and p.parent == Path("."):
        p = _DESKTOP_DIR / p.name

    current_ext = p.suffix.lower()
    requested = _explicit_language_hint(user_hint) if user_hint else None
    if requested and current_ext != requested:
        return p.with_suffix(requested)

    if current_ext in ("", ".txt"):
        sniffed = _sniff_extension(content)
        if sniffed:
            p = p.with_suffix(sniffed)
    return p

# Only messages that plausibly need a file-system action or a new agent take
# the (slow, multi-round) Claude tool-use path -- see the latency note where
# this is used in _generate_response_via_hierarchy.
_WANTS_TOOLS_RE = re.compile(
    r"\b(file|folder|directory|read .*(file|it)|write .*(file|to)|save (it|this|that|a file)|"
    r"delete|remove .*(file|folder)|move .*(file|folder)|rename|"
    r"create (a |an |another )?(sub)?agent|make (a |an |another )?(sub)?agent|"
    r"new (sub)?agent|build (a |an |another )?(sub)?agent|spin up.*agent|"
    r"run (a |the |this )?command|execute|shell|terminal|"
    r"git (status|log|diff|commit|push|pull|branch|checkout|clone)|"
    r"(check|list|show) (my )?(repo|repository|processes|packages)|"
    r"install .*(package|dependency|library)|"
    r"(fetch|read|open|check|look at|browse|pull up) (this |that |the )?(url|link|page|website|site)|"
    r"https?://|"
    r"(take|grab) (a |)?screenshot|screen ?shot|"
    r"click (the|on)|move (the |)?mouse|type (this|that|the following)|press (the |)?\w+ key|"
    r"control (my|the) (screen|computer|mouse|keyboard)|"
    r"(pin|post|save|add) (this|that|it) to (the |your )?canvas|canvas)\b",
    re.IGNORECASE,
)

# Explicit opt-in only -- Mixture-of-Agents costs real latency (several
# parallel model calls plus a synthesis call) that would fight the Phase 1
# "under 3-4 seconds" responsiveness goal if triggered silently on ordinary
# messages, so it only fires on a deliberate ask for cross-model validation.
_WANTS_MOA_RE = re.compile(
    r"\b(second opinion|cross[- ]check (this|that|it)?.*(model|ai)|"
    r"ask (multiple|several|a few) (ai|model)s|"
    r"mixture of agents|\bmoa\b|"
    r"compare (answers|responses) from (multiple|several|different) (ai|model)s|"
    r"get (multiple|several) (ai )?opinions)\b",
    re.IGNORECASE,
)

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

CANVAS_TOOL: Dict[str, Any] = {
    "name": "post_to_canvas",
    "description": (
        "Pin something to the shared visual canvas for the user to see -- a note, a link, a code "
        "snippet, or a finding worth keeping visible beyond this chat turn. Broadcasts live to every "
        "connected tab. Read-only for the user (they see it appear); no approval needed to post."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["note", "link", "code", "image"]},
            "title": {"type": "string"},
            "content": {"type": "string", "description": "note text, URL, code text, or base64 image data"},
            "language": {"type": "string", "description": "for type=='code' only, e.g. 'python'"},
        },
        "required": ["type", "title", "content"],
    },
}


async def _execute_file_tool(name: str, tool_input: Dict[str, Any], user_hint: str = "") -> Dict[str, Any]:
    if mcp_manager.is_plugin_tool(name):
        return await mcp_manager.call_tool(name, tool_input)

    if name == "post_to_canvas":
        try:
            item = canvas_store.create(
                tool_input.get("type", "note"), tool_input.get("title", ""),
                tool_input.get("content", ""), tool_input.get("language"),
            )
        except ValueError as e:
            return {"success": False, "error": str(e)}
        await event_bus.publish("CANVAS_ITEM_ADDED", {"item": item.to_public_dict()})
        return {"success": True, "item_id": item.id}

    if name == "fetch_url":
        return await fetch_url(tool_input.get("url", ""))

    if name == "web_search":
        return await web_search(tool_input.get("query", ""), max_results=tool_input.get("max_results", 5))

    if name == "llm_structured_task":
        return await structured_llm_call(tool_input.get("prompt", ""), tool_input.get("json_schema", {}))

    if name == "create_backup":
        if not arm_switch.is_armed():
            approved = await telegram_notifier.request_approval(
                "Nancy wants to: create a backup zip of your data/skills/.env", timeout=120.0
            )
            if not approved:
                return {"success": False, "error": "User did not approve this backup."}
        return create_backup()

    if name == "ha_call_service":
        from channels.registry import get_channel
        ha = get_channel("home_assistant")
        if ha is None:
            return {"success": False, "error": "Home Assistant is not configured (HOME_ASSISTANT_URL/HOME_ASSISTANT_TOKEN)."}
        return await ha.call_service(
            tool_input.get("domain", ""), tool_input.get("service", ""), tool_input.get("service_data", {})
        )

    if name == "spotify_control":
        return await handle_spotify_tool(tool_input)

    if name == "node_execute_command":
        return await node_host.dispatch_command(
            tool_input.get("node_id", ""), tool_input.get("command", ""), cwd=tool_input.get("cwd"),
        )

    if name == "show_diff":
        return await post_diff_to_canvas(tool_input.get("old_text", ""), tool_input.get("new_text", ""), tool_input.get("title", "Diff"))

    if name == "extract_document_text":
        return doc_extraction.extract_document(tool_input.get("path", ""))

    if name in ("take_screenshot", "get_screen_size"):
        loop = asyncio.get_event_loop()
        fn = computer_use_tool.take_screenshot if name == "take_screenshot" else computer_use_tool.get_screen_size
        return await loop.run_in_executor(None, fn)

    if name in COMPUTER_ACTION_TOOLS:
        description = {
            "click_screen": f"click the screen at ({tool_input.get('x')}, {tool_input.get('y')})",
            "move_mouse": f"move the mouse to ({tool_input.get('x')}, {tool_input.get('y')})",
            "type_text": f"type: {tool_input.get('text', '')!r}",
            "press_key": f"press the '{tool_input.get('key')}' key",
            "scroll_screen": f"scroll by {tool_input.get('amount')}",
        }[name]
        approved = await telegram_notifier.request_approval(
            f"Nancy wants to control your screen: {description}", timeout=120.0
        )
        if not approved:
            return {"success": False, "error": "User did not approve this screen control action."}
        loop = asyncio.get_event_loop()
        fn = getattr(computer_use_tool, name)
        return await loop.run_in_executor(None, lambda: fn(**tool_input))

    if name == "create_subagent":
        return await _execute_create_subagent_tool(tool_input)

    if name == "execute_command":
        command = str(tool_input.get("command", ""))
        if not terminal_tool._is_safe_command(command) and not arm_switch.is_armed():
            approved = await telegram_notifier.request_approval(
                f"Nancy wants to run a command:\n\n{command}", timeout=120.0
            )
            if not approved:
                return {"success": False, "error": "User did not approve this command."}
        return await terminal_tool.execute_command(command, cwd=tool_input.get("cwd"), use_egress_proxy=tool_input.get("use_egress_proxy", False))

    resolved_write_path: Optional[Path] = None
    if name == "write_file":
        resolved_write_path = _resolve_write_path(tool_input["path"], tool_input["content"], user_hint)

    if name in _FILE_WRITE_TOOLS and not arm_switch.is_armed():
        description = {
            "write_file": f"Write to file: {resolved_write_path}",
            "delete_file": f"Delete: {tool_input.get('path')}",
            "move_file": f"Move {tool_input.get('src')} -> {tool_input.get('dst')}",
        }[name]
        if name == "write_file":
            lint_findings = security_lint.lint_content(tool_input.get("content", ""))
            description += security_lint.format_findings(lint_findings)
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
        await lifecycle_hooks.fire_hook("pre_write", {"path": str(resolved_write_path)})
        old_content_result = file_access.read_file(str(resolved_write_path))
        old_content = old_content_result.get("content") if old_content_result.get("success") else None
        result = file_access.write_file(str(resolved_write_path), tool_input["content"])
        evidence_ledger.record_evidence("write_file", str(resolved_write_path), result.get("success", False))
        if result.get("success"):
            try:
                diag_result = await asyncio.wait_for(
                    lsp_client.diagnostics_before_after_write(str(resolved_write_path), old_content, tool_input["content"]),
                    timeout=15.0,
                )
                if diag_result.get("success") and not diag_result.get("unsupported") and diag_result.get("new_diagnostics"):
                    result["new_diagnostics"] = diag_result["new_diagnostics"]
            except Exception as e:
                logger.info("lsp_client diagnostics check skipped: %s", e)
        return result
    if name == "delete_file":
        result = file_access.delete_file(tool_input["path"])
        evidence_ledger.record_evidence("delete_file", tool_input["path"], result.get("success", False))
        return result
    if name == "move_file":
        result = file_access.move_file(tool_input["src"], tool_input["dst"])
        evidence_ledger.record_evidence("move_file", f"{tool_input['src']} -> {tool_input['dst']}", result.get("success", False))
        return result
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


_SIR_RE = re.compile(r"\bsir\b", re.IGNORECASE)


def _enforce_sir(text: str) -> str:
    """The system prompt asks every backend to address the user as "Sir"
    (capitalized, even mid-sentence), but LLMs reliably "correct" that back
    to lowercase mid-sentence per normal English convention regardless of
    instruction -- confirmed empirically, not just a theoretical concern.
    Enforce it deterministically instead of hoping the model complies."""
    return _SIR_RE.sub("Sir", text)


def _build_chat_prompt(user_text: str, history_text: str) -> str:
    """Shared prompt assembly for both the blocking hierarchy path and the
    streaming path below -- kept in one place so they can't silently drift."""
    skills_block = skill_loader.build_skill_prompt_block(user_text)
    links_block = ""
    detected_urls = extract_urls(user_text)
    if detected_urls:
        links_block = "Links detected in the user's message (already SSRF-checked, safe to fetch_url if relevant): " + ", ".join(detected_urls)
    return (
        f"{BASE_SYSTEM_PROMPT}\n\n{_live_system_context()}\n\n{_live_context_bridge_context()}\n\n"
        f"{skills_block}\n\n{links_block}\n\n{history_text}\nuser: {user_text}\nassistant:"
    )


async def _generate_response_via_hierarchy(user_text: str) -> tuple[str, dict]:
    """Route a chat message to a real specialized agent when the text clearly
    matches one of the 29 registered domains; otherwise fall back to the
    general-purpose LLM.

    The previous implementation imported `orchestration.integration.run_nancy_hierarchy`,
    whose relative imports fail at runtime (`from ..llm import ...` outside package
    context) - every call silently hit the except branch below and fell back to a
    bare LLM call, so the "hierarchy" never actually ran. This now uses
    `agent_service`, the genuinely working 29-agent runtime (already exercised via
    the `/agents/run` and `/agents/auto` endpoints), with the same keyword-routing
    table `auto_run` uses - but only delegates on an actual keyword match, so plain
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

    prompt = _build_chat_prompt(user_text, history_text)

    # File access + subagent-creation only work through Claude's multi-round
    # tool-use loop (generate_with_tools) -- the other backends in the
    # fallback chain are plain text completion with no tool-calling at all.
    # That loop costs real latency: up to 5 sequential Claude round-trips
    # even when no tool ends up being called, which is why this used to run
    # for EVERY message (including plain chat like "how are you") whenever
    # an Anthropic key was configured -- a real contributor to 60s+ replies.
    # Only pay that cost when the message plausibly needs a tool.
    if os.getenv("ANTHROPIC_API_KEY") and _WANTS_TOOLS_RE.search(user_text):
        try:
            claude = AnthropicLLM()

            async def _file_tool_executor(name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
                # Binds this turn's real user_text in as a write_file extension
                # hint -- see _explicit_language_hint -- without changing the
                # tool_executor(name, input) contract generate_with_tools calls.
                return await _execute_file_tool(name, tool_input, user_hint=user_text)

            resp = await asyncio.wait_for(
                claude.generate_with_tools(
                    prompt,
                    FILE_TOOLS + terminal_tool.TERMINAL_TOOLS + [CREATE_SUBAGENT_TOOL, CANVAS_TOOL] + mcp_manager.list_plugin_tools() + WEB_TOOLS + COMPUTER_USE_TOOLS + UTILITY_TOOLS + BACKUP_TOOLS + HOME_ASSISTANT_TOOLS + SPOTIFY_TOOLS + NODE_TOOLS + DIFF_TOOLS + doc_extraction.DOC_EXTRACTION_TOOLS,
                    _file_tool_executor,
                    max_tokens=1024,
                ),
                timeout=45.0,
            )
            return _enforce_sir(resp), {"tool_use": True}
        except Exception as e:
            logger.warning("Claude tool-use path failed, falling back to plain chain: %s", e)

    try:
        resp = await asyncio.wait_for(
            llm_backend.generate(prompt, max_tokens=512, temperature=0.7),
            timeout=30.0,
        )
        resp = _enforce_sir(resp)
    except Exception as llm_e:
        resp = f"I'm having trouble processing that right now, Sir. ({llm_e})"
    return resp, {}


# ---------------------------------------------------------------------------
# Streaming chat turn -- real token streaming (Claude) + per-sentence TTS, so
# Nancy starts speaking sentence 1 while sentence 2+ is still being generated
# instead of waiting for the entire reply and then the entire audio clip.
# Agent-routed and tool-use replies aren't incremental at the source, but they
# still flow through the same per-sentence TTS chunking below so the first
# chunk of audio is available as soon as the first sentence is, not the whole
# response.
# ---------------------------------------------------------------------------
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _extract_ready_sentences(buffer: str) -> tuple[list[str], str]:
    """Split off sentences that are definitely complete (end in . ! or ? and
    are followed by whitespace, or -- for the last piece -- just end in one of
    those, meaning only the trailing whitespace hasn't streamed in yet).
    Returns (ready_sentences, remainder_still_pending)."""
    if not buffer:
        return [], buffer
    parts = _SENTENCE_SPLIT_RE.split(buffer)
    complete = [p for p in parts[:-1] if p.strip()]
    tail = parts[-1]
    if tail and tail.rstrip()[-1:] in (".", "!", "?"):
        complete.append(tail)
        tail = ""
    return complete, tail


async def _generate_response_stream(user_text: str):
    """Async generator yielding {"kind": "delta", "text": ...} chunks as they
    become available, followed by exactly one {"kind": "meta", "debug": ...}.
    Only the plain-chat path (no agent match, no tool-use need) actually
    streams token-by-token, via AnthropicLLM.generate_stream() -- agent
    routing and Claude's tool-use loop aren't incremental at the source, so
    those paths fall back to _generate_response_via_hierarchy and yield its
    complete result as a single delta. Callers still get per-sentence TTS
    chunking downstream either way."""
    history_text = _history_to_text()

    if _WANTS_MOA_RE.search(user_text):
        result = await run_moa(llm_backend, user_text)
        if result.get("success"):
            refs = [r["backend"] for r in result.get("references", [])]
            prefix = f"(Cross-checked against {', '.join(refs)}.) " if result.get("aggregated") else ""
            yield {"kind": "delta", "text": prefix + result["response"]}
            yield {"kind": "meta", "debug": {"moa": True, "references": refs, "aggregated": result.get("aggregated")}}
        else:
            yield {"kind": "delta", "text": f"I couldn't get a cross-checked answer just now, Sir: {result.get('error')}"}
            yield {"kind": "meta", "debug": {"moa": True, "error": result.get("error")}}
        return

    if agent_service.is_ready():
        try:
            from agents.agent_service import _auto_route
            routed_key = _auto_route(user_text)
        except Exception:
            routed_key = None
        if routed_key:
            text, debug = await _generate_response_via_hierarchy(user_text)
            yield {"kind": "delta", "text": text}
            yield {"kind": "meta", "debug": debug}
            return

    if os.getenv("ANTHROPIC_API_KEY") and _WANTS_TOOLS_RE.search(user_text):
        text, debug = await _generate_response_via_hierarchy(user_text)
        yield {"kind": "delta", "text": text}
        yield {"kind": "meta", "debug": debug}
        return

    if os.getenv("ANTHROPIC_API_KEY"):
        prompt = _build_chat_prompt(user_text, history_text)
        try:
            claude = AnthropicLLM()
            got_any = False
            async for delta in claude.generate_stream(prompt, max_tokens=512, temperature=0.7):
                got_any = True
                yield {"kind": "delta", "text": delta}
            if got_any:
                yield {"kind": "meta", "debug": {"streamed": True}}
                return
        except Exception as e:
            logger.warning("Streaming Claude call failed, falling back to non-streaming chain: %s", e)

    text, debug = await _generate_response_via_hierarchy(user_text)
    yield {"kind": "delta", "text": text}
    yield {"kind": "meta", "debug": debug}


async def _synthesize_and_send_chunk(websocket: WebSocket, turn_id: int, seq: int, text: str) -> None:
    text = text.strip()
    if not text:
        return
    try:
        audio_wav = await tts_backend.synthesize(text)
    except Exception as e:
        logger.error("Streaming TTS chunk error (turn %d, seq %d): %s", turn_id, seq, e)
        return
    if not audio_wav:
        return
    try:
        await manager.send(
            json.dumps({
                "type": "tts_audio_chunk",
                "turn_id": turn_id,
                "seq": seq,
                "data": base64.b64encode(audio_wav).decode(),
            }),
            websocket,
        )
    except Exception:
        pass  # connection likely gone; the outer turn will be cancelled/cleaned up


async def _run_chat_turn(websocket: WebSocket, turn_id: int, user_text: str) -> None:
    """The actual per-message work, run as its own cancellable asyncio.Task
    (see ConnectionManager.start_turn) so a new message can supersede a slow
    one in progress instead of queuing behind it."""
    if history_manager:
        await history_manager.add({"role": "user", "content": user_text})

    full_text = ""
    sentence_buffer = ""
    debug_payload: Dict[str, Any] = {}
    seq = 0

    try:
        async for item in _generate_response_stream(user_text):
            if item["kind"] == "delta":
                delta = item["text"]
                full_text += delta
                sentence_buffer += delta
                ready, sentence_buffer = _extract_ready_sentences(sentence_buffer)
                for sentence in ready:
                    seq += 1
                    await _synthesize_and_send_chunk(websocket, turn_id, seq, sentence)
            elif item["kind"] == "meta":
                debug_payload = item.get("debug", {})

        full_text = _enforce_sir(full_text.strip()) or "I'm not sure how to respond to that, Sir."

        if history_manager:
            await history_manager.add({"role": "assistant", "content": full_text})

        # Real commitment extraction (memory/commitments.py) -- fire-and-
        # forget so it never adds latency to the reply already sent above;
        # might_contain_commitment() is a cheap regex check that keeps this
        # a no-op (no LLM call at all) for ordinary turns.
        if commitments.might_contain_commitment(user_text):
            asyncio.create_task(commitments.extract_commitments(user_text, full_text))

        await manager.send(
            json.dumps({
                "type": "agent_response",
                "data": full_text,
                "debug": debug_payload,
                "turn_id": turn_id,
            }),
            websocket,
        )

        if sentence_buffer.strip():
            seq += 1
            await _synthesize_and_send_chunk(websocket, turn_id, seq, sentence_buffer)

        await manager.send(json.dumps({"type": "tts_done", "turn_id": turn_id}), websocket)

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception("Chat turn error (turn %d): %s", turn_id, e)
        try:
            await manager.send(
                json.dumps({"type": "agent_error", "error": str(e), "turn_id": turn_id}),
                websocket,
            )
        except Exception:
            pass


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

class CronJobCreateRequest(BaseModel):
    name: str
    description: str = ""
    hour: int = 0
    minute: int = 0
    action_type: str  # "telegram_message" | "agent_task" | "run_skill" | "terminal_command" | "run_script"
    action_payload: Dict[str, Any] = {}
    # Real cron expression (e.g. "*/15 * * * *") -- takes priority over
    # hour/minute when set. hour/minute stay required-by-default (0/0) for
    # backward compatibility with any existing caller still only sending those.
    cron_expression: Optional[str] = None

class WebhookCreateRequest(BaseModel):
    url: str
    event: str

class InboundWebhookCreateRequest(BaseModel):
    name: str
    action_type: str  # "telegram_message" | "agent_task" | "run_skill" | "terminal_command" | "run_script"
    action_payload: Dict[str, Any] = {}

class CanvasItemCreateRequest(BaseModel):
    type: str  # "note" | "link" | "code" | "image"
    title: str
    content: str
    language: Optional[str] = None

class SkillCreateRequest(BaseModel):
    name: str
    description: str = ""
    category: str = "general"
    agent_keys: list[str] = []

class SkillUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    agent_keys: list[str] | None = None

class PluginServerCreateRequest(BaseModel):
    name: str
    command: str
    args: list[str] = []
    env: Dict[str, str] = {}

class KeyUpsertRequest(BaseModel):
    name: str
    value: str

class SaveFileRequest(BaseModel):
    filename: str
    content: str

class MissionCreateRequest(BaseModel):
    title: str
    description: str = ""
    owner: str = ""
    priority: str = "medium"
    risk: str = "low"
    estimated_cost: float | None = None
    due_date: str | None = None
    tags: list[str] = []
    dependencies: list[str] = []
    subtasks: list[Dict[str, Any]] = []
    assigned_agent: str | None = None
    assigned_agents: list[str] = []

class MissionUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    owner: str | None = None
    priority: str | None = None
    risk: str | None = None
    estimated_cost: float | None = None
    due_date: str | None = None
    tags: list[str] | None = None
    dependencies: list[str] | None = None
    subtasks: list[Dict[str, Any]] | None = None
    order: float | None = None

class MissionAssignRequest(BaseModel):
    agent_key: str | None = None
    # Explicit multi-agent assignment -- when non-empty, takes priority over
    # agent_key (mission_store.assign_multi clears the single-agent field so
    # there's one unambiguous source of truth for _dispatch_mission).
    agent_keys: list[str] = []

class MissionTransitionRequest(BaseModel):
    stage: str


# ---------------------------------------------------------------------------
# REST routes - Core
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return HTMLResponse("<h1>Nancy/Billion Backend v2 - online</h1>")

@app.get("/test")
async def test():
    return {"message": "test ok", "agents_ready": agent_service.is_ready()}


# ---------------------------------------------------------------------------
# Startup & Greeting endpoints
# ---------------------------------------------------------------------------

@app.get("/skills")
async def list_skills():
    return {"success": True, "skills": [asdict(s) for s in skills_store.list()]}


@app.get("/memory/search")
async def memory_search_endpoint(q: str = "", top_k: int = 10):
    try:
        hits = memory_manager.search_memories(q or "", top_k=top_k)
    except Exception:
        hits = []
    return {"success": True, "query": q, "results": hits}


@app.get("/greeting")
async def get_greeting():
    """Current static per-persona greeting strings (see startup.py's
    NancyGreeting) -- distinct from /greeting/personalized, which builds a
    real-data-backed greeting via the LLM. Restored: this and /persona/{name}
    below were commented out, but the Profiles panel's persona switcher
    (admin-panels.tsx) calls /persona/{name} unconditionally and was 404ing
    on every click while the UI claimed to be "real, functional"."""
    greeting = startup_coordinator.greeting
    return {
        "success": True,
        "persona": startup_coordinator.persona,
        "boot_message": greeting.get_boot_message(),
        "ready_message": greeting.get_ready_message(),
        "context_aware_greeting": greeting.get_context_aware_greeting(),
    }


@app.post("/persona/{persona_name}")
async def set_persona(persona_name: str):
    valid_personas = ["nancy", "billion", "jarvis"]
    if persona_name.lower() not in valid_personas:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid persona. Choose from: {', '.join(valid_personas)}",
        )
    startup_coordinator.set_persona(persona_name)
    greeting = startup_coordinator.greeting
    logger.info(f"Persona changed to: {persona_name}")
    return {
        "success": True,
        "persona": startup_coordinator.persona,
        "greeting": greeting.get_ready_message(),
    }


async def _build_real_personal_context() -> "PersonalContext":
    # Populate PersonalContext from Nancy actual data sources instead of
    # the hardcoded demo data in intelligent_greeting.py's own __main__ block
    # (that demo is exactly the "Docker build"/"Roxan deployment" example
    # text -- illustrative of the tone, not real data). No calendar/meetings
    # integration exists, so meetings_today is intentionally always empty
    # rather than fabricated. Every other field is best-effort: any source
    # that errors has nothing to report is just omitted, not faked.
    # Real pairs the user actually trades/watches -- trading_manager.watched_pairs
    # (explicit) unioned with whatever pairs appear in real trade history, never
    # a hardcoded pair list. Confirmed live: this used to always report EUR/USD
    # and GBP/USD regardless of what the user actually trades.
    market_alerts: list = []
    for pair in trading_manager.get_relevant_pairs():
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

    # Real agent-fleet status -- always available once the agent service is
    # ready, so the greeting has substance even when there's nothing else
    # (no trades, no projects, no pending approvals) to report.
    system_status: Optional[str] = None
    try:
        if agent_service.is_ready():
            stats = agent_service.get_service_stats()
            online = stats["agents_online"]
            tasks = stats["total_tasks"]
            if tasks > 0:
                system_status = (
                    f"all {online} specialized agents are online, with {tasks} task"
                    f"{'s' if tasks != 1 else ''} completed at a {stats['success_rate'] * 100:.0f}% success rate"
                )
            else:
                system_status = f"all {online} specialized agents are online and standing by"
    except Exception as e:
        logger.debug("Greeting: system status unavailable: %s", e)

    return PersonalContext(
        meetings_today=[],  # no calendar integration -- honestly empty, not fabricated
        build_status=None,  # no CI/build system integration exists
        market_alerts=market_alerts,
        project_updates=project_updates,
        active_trades=active_trades,
        tasks_due=tasks_due,
        system_status=system_status,
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
# Context bridge - shared UI/brain state
# ---------------------------------------------------------------------------

class _ContextBridge:
    def __init__(self) -> None:
        self.payload: Dict[str, Any] = {}
        self.updated_at: Optional[str] = None
        self.channel_hints: List[str] = []

    def update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.payload.update(payload)
        self.updated_at = datetime.now().isoformat()
        return {
            "success": True,
            "updated_at": self.updated_at,
            "payload": self.payload,
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "success": True,
            "payload": self.payload,
            "updated_at": self.updated_at,
            "channel_hints": self.channel_hints,
        }

_context_bridge = _ContextBridge()


@app.post("/context")
async def context_update(payload: Dict[str, Any]):
    """Accept dashboard/UI context events as a single canonical source."""
    result = _context_bridge.update(payload)
    return result


@app.get("/context")
async def context_snapshot():
    """Return latest context for UI/channel sync."""
    return _context_bridge.snapshot()


def get_live_context_snapshot() -> Dict[str, Any]:
    snapshot = _context_bridge.snapshot()
    payload = snapshot.get("payload", {}) or {}
    return payload


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


@app.get("/trading/watched-pairs")
async def get_watched_pairs():
    """Pairs Nancy actually reports on in the greeting/market alerts --
    explicit watch list plus whatever real trade history contains. See
    trading_manager.get_relevant_pairs()."""
    return {
        "success": True,
        "watched_pairs": trading_manager.watched_pairs,
        "relevant_pairs": trading_manager.get_relevant_pairs(),
    }


class WatchedPairsRequest(BaseModel):
    pairs: List[str]


@app.post("/trading/watched-pairs", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def set_watched_pairs(req: WatchedPairsRequest):
    """Replace the explicit watch list, e.g. after telling Nancy "I mostly
    trade XAUUSD, GBPUSD and XAGUSD" -- accepts "XAUUSD" or "XAU/USD" form."""
    trading_manager.set_watched_pairs(req.pairs)
    return {"success": True, "watched_pairs": trading_manager.watched_pairs}


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
    - "coding" -> Claude (Anthropic)
    - "fast_response" -> Groq (speed optimized)
    - "multimodal" -> Gemini
    - None / "general" -> Uses full fallback chain (Ollama -> Anthropic -> Groq -> OpenAI -> etc.)
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
        # cranked up - select_llm_for_task() already routes "coding" hints to
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
        "reply": _enforce_sir(response.strip()),
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
# REST routes - Specialized Agents
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
    route - the frontend's Overview/System panels showed Math.random()-jittered
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
    on a fresh checkout until CLAP_MODEL_PATH is pointed at a real .pth file -
    see clap_detection.py for the honest error this reports until then.
    """
    loop = asyncio.get_event_loop()
    status = await loop.run_in_executor(None, lambda: clap_detector.status)
    return {"success": True, **status}


@app.get("/llm/status")
async def llm_status():
    """Real LLM fallback chain, STT and TTS engine info -- used by the AI
    Core panel's "Model Stack" card, which previously showed entirely
    fictional entries (a made-up "671B gpt-class" model, fake version
    numbers) instead of what's actually running."""
    backends = []
    for b in getattr(llm_backend, "backends", []):
        entry = {"name": b.__class__.__name__}
        model = getattr(b, "model", None)
        if model:
            entry["model"] = model
        backends.append(entry)

    stt_info = {"backend": stt_backend.__class__.__name__}
    if hasattr(stt_backend, "model_size"):
        stt_info["model"] = stt_backend.model_size
        stt_info["device"] = getattr(stt_backend, "device", None)

    tts_info = {"backend": tts_backend.__class__.__name__}

    return {
        "success": True,
        "primary_model": backends[0].get("model") or backends[0].get("name") if backends else None,
        "backends": backends,
        "stt": stt_info,
        "tts": tts_info,
        "agents_ready": agent_service.is_ready(),
    }


@app.get("/cron/status")
async def cron_status():
    """Info about the one built-in scheduled job -- the daily Telegram
    briefing (see _daily_briefing_loop below). User-created jobs live in
    the separate /cron/jobs CRUD below (cron_store.py), fired by
    _cron_execution_loop -- kept as a distinct endpoint so nothing that
    already reads this shape breaks."""
    now = datetime.now()
    target = now.replace(hour=DAILY_BRIEFING_HOUR, minute=DAILY_BRIEFING_MINUTE, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return {
        "success": True,
        "jobs": [
            {
                "name": "Daily briefing",
                "schedule": f"{DAILY_BRIEFING_HOUR:02d}:{DAILY_BRIEFING_MINUTE:02d} daily",
                "next_run": target.isoformat(),
                "enabled": telegram_notifier.status["available"],
                "description": "Pushes a real-data personalized briefing to Telegram every morning.",
            }
        ],
    }


@app.get("/cron/jobs")
async def list_cron_jobs():
    """User-created scheduled jobs -- real, persisted (data/cron_jobs.json),
    and actually executed every minute by _cron_execution_loop, not just
    stored for display."""
    return {"success": True, "jobs": [j.to_public_dict() for j in cron_store.list()]}


@app.post("/cron/jobs")
async def create_cron_job(req: CronJobCreateRequest):
    if req.cron_expression:
        try:
            from croniter import croniter
            croniter(req.cron_expression)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid cron_expression: {e}")
    elif not (0 <= req.hour <= 23 and 0 <= req.minute <= 59):
        raise HTTPException(status_code=400, detail="hour must be 0-23 and minute 0-59 (or set cron_expression)")
    if req.action_type not in ("telegram_message", "agent_task", "run_skill", "terminal_command", "run_script", "channel_message", "memory_consolidate", "commitment_checkin"):
        raise HTTPException(status_code=400, detail="action_type must be telegram_message, agent_task, run_skill, terminal_command, run_script, or channel_message")
    if req.action_type == "telegram_message" and not req.action_payload.get("text"):
        raise HTTPException(status_code=400, detail="telegram_message jobs need action_payload.text")
    if req.action_type == "agent_task" and not req.action_payload.get("agent_key"):
        raise HTTPException(status_code=400, detail="agent_task jobs need action_payload.agent_key")
    if req.action_type == "run_skill" and not (req.action_payload.get("skill_name") or req.action_payload.get("bundle_name")):
        raise HTTPException(status_code=400, detail="run_skill jobs need action_payload.skill_name or action_payload.bundle_name")
    if req.action_type == "terminal_command" and not req.action_payload.get("command"):
        raise HTTPException(status_code=400, detail="terminal_command jobs need action_payload.command")
    if req.action_type == "run_script" and not req.action_payload.get("script"):
        raise HTTPException(status_code=400, detail="run_script jobs need action_payload.script")
    if req.action_type == "channel_message" and not (req.action_payload.get("channel") and req.action_payload.get("message")):
        raise HTTPException(status_code=400, detail="channel_message jobs need action_payload.channel and action_payload.message")
    job = cron_store.create(
        req.name, req.description, req.hour, req.minute, req.action_type, req.action_payload,
        cron_expression=req.cron_expression,
    )
    return {"success": True, "job": job.to_public_dict()}


@app.patch("/cron/jobs/{job_id}")
async def toggle_cron_job(job_id: str, enabled: bool):
    job = cron_store.set_enabled(job_id, enabled)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"success": True, "job": job.to_public_dict()}


@app.delete("/cron/jobs/{job_id}")
async def delete_cron_job(job_id: str):
    if not cron_store.delete(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    return {"success": True}


@app.get("/cron/blueprints")
async def list_cron_blueprints():
    """Pre-built automation templates (blueprint_catalog.py) -- fill in a
    few real slots (time, topic, recurrence) instead of hand-writing a cron
    expression and a prompt from scratch."""
    return {"success": True, "blueprints": [blueprint_catalog_entry(b) for b in BLUEPRINT_CATALOG]}


class BlueprintFillRequest(BaseModel):
    values: Dict[str, Any] = {}

@app.post("/cron/blueprints/{key}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def create_job_from_blueprint(key: str, req: BlueprintFillRequest):
    blueprint = get_blueprint(key)
    if blueprint is None:
        raise HTTPException(status_code=404, detail="blueprint not found")
    try:
        spec = fill_blueprint(blueprint, req.values)
    except BlueprintFillError as e:
        raise HTTPException(status_code=400, detail=str(e))
    job = cron_store.create(
        spec["name"], spec["description"], 0, 0, spec["action_type"], spec["action_payload"],
        cron_expression=spec["cron_expression"],
    )
    return {"success": True, "job": job.to_public_dict()}


@app.get("/webhooks/inbound", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def list_inbound_webhooks():
    """Real, persisted inbound webhook endpoints -- each one's real trigger
    count/last-result comes from data/inbound_webhooks.json, and each one
    genuinely runs its configured action when its /webhooks/inbound/{id}
    URL actually receives a POST, not just recorded for display."""
    return {"success": True, "webhooks": [h.to_public_dict() for h in inbound_webhook_store.list()]}


@app.post("/webhooks/inbound", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def create_inbound_webhook(req: InboundWebhookCreateRequest):
    if req.action_type not in ("telegram_message", "agent_task", "run_skill", "terminal_command", "run_script", "channel_message", "memory_consolidate", "commitment_checkin"):
        raise HTTPException(status_code=400, detail="action_type must be telegram_message, agent_task, run_skill, terminal_command, run_script, or channel_message")
    if req.action_type == "telegram_message" and not req.action_payload.get("text"):
        raise HTTPException(status_code=400, detail="telegram_message hooks need action_payload.text")
    if req.action_type == "agent_task" and not req.action_payload.get("agent_key"):
        raise HTTPException(status_code=400, detail="agent_task hooks need action_payload.agent_key")
    if req.action_type == "run_skill" and not (req.action_payload.get("skill_name") or req.action_payload.get("bundle_name")):
        raise HTTPException(status_code=400, detail="run_skill hooks need action_payload.skill_name or action_payload.bundle_name")
    if req.action_type == "terminal_command" and not req.action_payload.get("command"):
        raise HTTPException(status_code=400, detail="terminal_command hooks need action_payload.command")
    if req.action_type == "run_script" and not req.action_payload.get("script"):
        raise HTTPException(status_code=400, detail="run_script hooks need action_payload.script")
    if req.action_type == "channel_message" and not (req.action_payload.get("channel") and req.action_payload.get("message")):
        raise HTTPException(status_code=400, detail="channel_message hooks need action_payload.channel and action_payload.message")
    hook = inbound_webhook_store.create(req.name, req.action_type, req.action_payload)
    # The raw secret is only ever revealed here, at creation -- every other
    # read (list, this same hook fetched again later) only exposes
    # has_secret, matching how API keys/tokens are handled everywhere else
    # in this app (see /config/keys never echoing a stored value back).
    return {"success": True, "webhook": {**hook.to_public_dict(), "secret": hook.secret}}


@app.patch("/webhooks/inbound/{hook_id}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def toggle_inbound_webhook(hook_id: str, enabled: bool):
    hook = inbound_webhook_store.set_enabled(hook_id, enabled)
    if not hook:
        raise HTTPException(status_code=404, detail="webhook not found")
    return {"success": True, "webhook": hook.to_public_dict()}


@app.delete("/webhooks/inbound/{hook_id}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def delete_inbound_webhook(hook_id: str):
    if not inbound_webhook_store.delete(hook_id):
        raise HTTPException(status_code=404, detail="webhook not found")
    return {"success": True}


@app.post("/webhooks/inbound/{hook_id}")
async def receive_inbound_webhook(hook_id: str, request: Request):
    """The real receiving end -- an external service (GitHub, a CI
    pipeline, any HTTP client) POSTs here and it genuinely triggers the
    hook's configured action. Deliberately NOT behind require_auth: external
    callers won't have Nancy's own API key, so authentication here is the
    hook's own HMAC secret instead (same model as GitHub/Stripe webhooks).
    """
    hook = inbound_webhook_store.get(hook_id)
    if hook is None:
        raise HTTPException(status_code=404, detail="webhook not found")
    if not hook.enabled:
        raise HTTPException(status_code=403, detail="webhook is disabled")

    raw_body = await request.body()
    if hook.secret:
        signature = request.headers.get("X-Nancy-Signature", "")
        expected = "sha256=" + hmac.new(hook.secret.encode(), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=401, detail="invalid or missing X-Nancy-Signature")

    try:
        body_json = json.loads(raw_body) if raw_body else {}
    except Exception:
        body_json = {}

    trigger_name = f'inbound webhook "{hook.name}"'
    try:
        if hook.action_type == "telegram_message":
            await telegram_notifier.send(hook.action_payload.get("text", ""))
            summary = "sent telegram message"
        elif hook.action_type == "agent_task":
            agent_key = hook.action_payload.get("agent_key")
            task_type = hook.action_payload.get("task_type", "query")
            payload = hook.action_payload.get("payload", {})
            if not agent_service.is_ready() or not agent_key:
                summary = "skipped: agent service not ready"
            else:
                result = await agent_service.run(agent_key, {"type": task_type, **payload}, timeout=60.0)
                summary = json.dumps(result)[:300]
        elif hook.action_type == "run_skill":
            payload = dict(hook.action_payload)
            # The external caller's real payload becomes extra context for
            # the skill -- e.g. a GitHub PR-opened event's real details --
            # but the external caller never controls WHICH skill/command
            # runs, only that this specific pre-configured hook fired.
            extra = (payload.get("context", "") + f"\n\nWebhook payload: {json.dumps(body_json)[:1000]}").strip()
            payload["context"] = extra
            summary = await _run_cron_skill(payload, trigger_name)
        elif hook.action_type == "terminal_command":
            summary = await _run_cron_terminal_command(hook.action_payload, trigger_name)
        elif hook.action_type == "run_script":
            summary = await _run_cron_script(hook.action_payload, trigger_name)
        elif hook.action_type == "channel_message":
            summary = await _run_cron_channel_message(hook.action_payload, trigger_name)
        elif hook.action_type == "memory_consolidate":
            summary = await _run_cron_memory_consolidate(hook.action_payload, trigger_name)
        elif hook.action_type == "commitment_checkin":
            summary = await _run_cron_commitment_checkin(hook.action_payload, trigger_name)
        else:
            summary = f"Unknown action_type: {hook.action_type}"
    except Exception as e:
        logger.exception("Inbound webhook %s failed: %s", hook.name, e)
        summary = f"error: {e}"

    inbound_webhook_store.mark_triggered(hook_id, summary)
    return {"success": True, "result": summary}


@app.get("/canvas")
async def list_canvas_items():
    """Real, persisted shared canvas items (data/canvas.json) -- pinned
    first, newest first otherwise. Live updates broadcast to every
    connected tab via CANVAS_ITEM_ADDED/REMOVED/UPDATED (see event_bus)."""
    return {"success": True, "items": [i.to_public_dict() for i in canvas_store.list()]}


@app.post("/canvas", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def create_canvas_item(req: CanvasItemCreateRequest):
    try:
        item = canvas_store.create(req.type, req.title, req.content, req.language)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await event_bus.publish("CANVAS_ITEM_ADDED", {"item": item.to_public_dict()})
    return {"success": True, "item": item.to_public_dict()}


@app.patch("/canvas/{item_id}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def toggle_canvas_item_pinned(item_id: str, pinned: bool):
    item = canvas_store.set_pinned(item_id, pinned)
    if item is None:
        raise HTTPException(status_code=404, detail="canvas item not found")
    await event_bus.publish("CANVAS_ITEM_UPDATED", {"item": item.to_public_dict()})
    return {"success": True, "item": item.to_public_dict()}


@app.delete("/canvas/{item_id}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def delete_canvas_item(item_id: str):
    if not canvas_store.delete(item_id):
        raise HTTPException(status_code=404, detail="canvas item not found")
    await event_bus.publish("CANVAS_ITEM_REMOVED", {"item_id": item_id})
    return {"success": True}


@app.get("/economic-calendar/events")
async def list_economic_calendar_events():
    """Real NFP/CPI/FOMC releases in the tracked window (see
    economic_calendar.py) -- upcoming ones have actual: null; released ones
    have actual/previous filled in from the last successful FRED poll
    (estimate is always null -- FRED has no consensus/forecast data).
    Empty (not an error) if FRED_API_KEY isn't configured yet."""
    events = economic_calendar.get_cached_events()
    return {
        "success": True,
        "events": events,
        "tracked_releases": {k: v["label"] for k, v in economic_calendar.TRACKED_RELEASES.items()},
        "configured": bool(economic_calendar.FRED_API_KEY),
    }


@app.get("/webhooks")
async def list_webhooks():
    """Real, persisted outbound webhook subscriptions (data/webhooks.json) --
    each one actually gets a real HTTP POST when its subscribed event fires
    (see _fire_webhooks, called from _cron_execution_loop and /agents/run)."""
    return {"success": True, "webhooks": [asdict(h) for h in webhook_store.list()], "valid_events": sorted(VALID_EVENTS)}


@app.post("/webhooks")
async def create_webhook(req: WebhookCreateRequest):
    if req.event not in VALID_EVENTS:
        raise HTTPException(status_code=400, detail=f"event must be one of {sorted(VALID_EVENTS)}")
    if not (req.url.startswith("http://") or req.url.startswith("https://")):
        raise HTTPException(status_code=400, detail="url must start with http:// or https://")
    hook = webhook_store.create(req.url, req.event)
    return {"success": True, "webhook": asdict(hook)}


@app.patch("/webhooks/{hook_id}")
async def toggle_webhook(hook_id: str, enabled: bool):
    hook = webhook_store.set_enabled(hook_id, enabled)
    if not hook:
        raise HTTPException(status_code=404, detail="webhook not found")
    return {"success": True, "webhook": asdict(hook)}


@app.delete("/webhooks/{hook_id}")
async def delete_webhook(hook_id: str):
    if not webhook_store.delete(hook_id):
        raise HTTPException(status_code=404, detail="webhook not found")
    return {"success": True}


@app.post("/webhooks/{hook_id}/test")
async def test_webhook(hook_id: str):
    """Fires one real test delivery to this specific webhook right now,
    regardless of whether its real event has actually happened, so the user
    can confirm their endpoint is reachable before waiting for a real event."""
    hooks = {h.id: h for h in webhook_store.list()}
    hook = hooks.get(hook_id)
    if not hook:
        raise HTTPException(status_code=404, detail="webhook not found")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(hook.url, json={"event": hook.event, "fired_at": _time.time(), "test": True})
            status = "ok" if resp.is_success else f"http_{resp.status_code}"
        except Exception as exc:
            status = f"error: {exc}"
    webhook_store.mark_fired(hook_id, status)
    return {"success": not status.startswith("error") and not status.startswith("http_4") and not status.startswith("http_5"), "status": status}


@app.get("/skills/custom")
async def list_custom_skills():
    """User-created skill records -- real, persisted (data/skills.json).
    Separate from /agents/list's specializations, which are read-only
    (compiled into each agent's Python class); these are assignable tags
    a user actually creates and attaches to real agents."""
    return {"success": True, "skills": [asdict(s) for s in skills_store.list()]}


@app.post("/skills/custom")
async def create_custom_skill(req: SkillCreateRequest):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    skill = skills_store.create(req.name.strip(), req.description, req.category, req.agent_keys)
    return {"success": True, "skill": asdict(skill)}


@app.patch("/skills/custom/{skill_id}")
async def update_custom_skill(skill_id: str, req: SkillUpdateRequest):
    skill = skills_store.update(skill_id, **req.model_dump(exclude_unset=True))
    if not skill:
        raise HTTPException(status_code=404, detail="skill not found")
    return {"success": True, "skill": asdict(skill)}


@app.delete("/skills/custom/{skill_id}")
async def delete_custom_skill(skill_id: str):
    if not skills_store.delete(skill_id):
        raise HTTPException(status_code=404, detail="skill not found")
    return {"success": True}


@app.get("/skills/library")
async def list_skill_library():
    """The real, invokable procedure skills (skill_loader.py's SKILL.md
    files) with real usage stats -- how many times each one has actually
    been matched into a live prompt, not just whether it exists on disk.
    Distinct from /skills (skills_store.py's user-facing labels)."""
    return {
        "success": True,
        "skills": skill_loader.list_skills_with_stats(),
        "archived": skill_loader.list_archived_skills(),
    }


@app.post("/skills/library/{name}/archive", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def archive_skill_route(name: str):
    """Manual curation, not an automatic timer -- moves the skill's real
    folder to skills/_archived/ so it stops being matched, without deleting
    it (restore_skill brings it straight back)."""
    if not skill_loader.archive_skill(name):
        raise HTTPException(status_code=404, detail="skill not found")
    return {"success": True}


@app.post("/skills/library/{name}/restore", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def restore_skill_route(name: str):
    if not skill_loader.restore_skill(name):
        raise HTTPException(status_code=404, detail="archived skill not found")
    return {"success": True}


class SkillBundleCreateRequest(BaseModel):
    name: str
    skill_names: List[str]
    description: str = ""

@app.get("/skills/bundles")
async def list_skill_bundles():
    """Real, persisted named groups of skills (skill_bundles.py) -- running
    one via a cron/webhook run_skill action (action_payload.bundle_name)
    injects every named skill's real instructions together as one combined
    procedure, instead of skill_loader's normal keyword-matched top-2."""
    return {"success": True, "bundles": [b.to_public_dict() for b in skill_bundle_store.list()]}


@app.post("/skills/bundles", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def create_skill_bundle(req: SkillBundleCreateRequest):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    unknown = [n for n in req.skill_names if skill_loader.get_skill(n) is None]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown skill(s): {', '.join(unknown)}")
    bundle = skill_bundle_store.create(req.name.strip(), req.skill_names, req.description)
    return {"success": True, "bundle": bundle.to_public_dict()}


@app.delete("/skills/bundles/{bundle_id}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def delete_skill_bundle(bundle_id: str):
    if not skill_bundle_store.delete(bundle_id):
        raise HTTPException(status_code=404, detail="bundle not found")
    return {"success": True}


@app.get("/plugins")
async def list_plugins():
    """Real, persisted MCP plugin server configs (data/mcp_servers.json)
    plus their live connection status -- connected/error/tool count, not
    just what's on disk."""
    return {"success": True, "servers": mcp_manager.list_status()}


@app.post("/plugins", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def create_plugin(req: PluginServerCreateRequest):
    """Registers a new MCP server and connects it immediately. Gated by the
    same Telegram-approval pattern as execute_command/terminal_command --
    `command` + `args` here IS an arbitrary local subprocess launch, the
    same real capability, just configured once instead of per-call."""
    if not req.name.strip() or not req.command.strip():
        raise HTTPException(status_code=400, detail="name and command are required")
    approved = await telegram_notifier.request_approval(
        f"Nancy wants to connect a new MCP plugin server \"{req.name}\":\n\n{req.command} {' '.join(req.args)}",
        timeout=120.0,
    )
    if not approved:
        raise HTTPException(status_code=403, detail="User did not approve this plugin server.")
    cfg = plugin_store.create(req.name.strip(), req.command.strip(), req.args, req.env)
    live = await mcp_manager.connect(cfg.id)
    return {
        "success": True,
        "server": {**cfg.to_public_dict(), "connected": live.connected, "error": live.error, "tools": [t.name for t in live.tools]},
    }


@app.patch("/plugins/{server_id}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def toggle_plugin(server_id: str, enabled: bool):
    cfg = plugin_store.set_enabled(server_id, enabled)
    if cfg is None:
        raise HTTPException(status_code=404, detail="plugin server not found")
    if enabled:
        await mcp_manager.connect(server_id)
    else:
        await mcp_manager.disconnect(server_id)
    return {"success": True, "server": cfg.to_public_dict()}


@app.delete("/plugins/{server_id}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def delete_plugin(server_id: str):
    await mcp_manager.disconnect(server_id)
    if not plugin_store.delete(server_id):
        raise HTTPException(status_code=404, detail="plugin server not found")
    return {"success": True}


@app.get("/config/public")
async def config_public():
    """Non-secret backend configuration -- real values, never API keys or tokens."""
    return {
        "success": True,
        "config": {
            "host": os.getenv("HOST", "0.0.0.0"),
            "port": int(os.getenv("PORT", 8000)),
            "ws_path": os.getenv("WS_PATH", "/ws"),
            "stt_backend": os.getenv("STT_BACKEND", "faster_whisper"),
            "whisper_model": os.getenv("WHISPER_MODEL", "tiny.en"),
            "anthropic_model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
            "groq_model": os.getenv("GROQ_MODEL", ""),
            "gemini_model": os.getenv("GEMINI_MODEL", ""),
            "opencode_model": os.getenv("OPENCODE_MODEL", ""),
            "daily_briefing": f"{DAILY_BRIEFING_HOUR:02d}:{DAILY_BRIEFING_MINUTE:02d}",
            "auth_required": bool(_BACKEND_AUTH_TOKEN),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
        },
    }


# Only these names can be written via /config/keys -- an explicit allowlist
# so this endpoint can never be used to overwrite arbitrary env vars (HOST,
# PORT, auth tokens, etc.) through the Keys page.
_WRITABLE_KEY_NAMES = {
    "ANTHROPIC_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY",
    "OPENROUTER_API_KEY", "OPENCODE_API_KEY",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
}


@app.post("/config/keys")
async def upsert_key(req: KeyUpsertRequest):
    """Writes a real provider key to backend/.env on disk via dotenv's
    set_key (create-or-update, preserves every other line in the file).
    Never echoes the value back or logs it. Honest about the one real
    limitation: the LLM/Telegram backend chain reads these at process
    startup (see load_dotenv() at the top of this file), so a written key
    takes effect on the next backend restart, not immediately -- this is
    a real constraint of the current architecture, not something to hide
    behind a fake "applied" response."""
    from dotenv import set_key

    name = req.name.strip().upper()
    if name not in _WRITABLE_KEY_NAMES:
        raise HTTPException(status_code=400, detail=f"'{name}' is not a writable key. Allowed: {sorted(_WRITABLE_KEY_NAMES)}")
    if not req.value.strip():
        raise HTTPException(status_code=400, detail="value cannot be empty")

    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        env_path.touch()
    set_key(str(env_path), name, req.value.strip())
    os.environ[name] = req.value.strip()

    return {
        "success": True,
        "name": name,
        "message": "Saved to .env. Restart the backend for the new key to take effect in the live LLM/Telegram chain.",
    }


@app.get("/tts/status")
async def tts_status():
    """Whether TTS is using the real neural voice (NeuTTS-nano) and which
    reference clip it cloned from ("user" vs "synthetic-placeholder") - see
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


@app.post("/voice/reference", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def upload_voice_reference(file: UploadFile = File(...)):
    """Real voice-clone upload -- drop in a clip and NeuTTS clones it on the
    very next synthesis, no restart (see neu_tts.py's refresh_reference).
    Auto-transcribed via faster-whisper (beam_size=5, the same one-time
    higher-accuracy pass _transcribe_user_reference always used), so no
    hand-typed transcript is needed."""
    if not isinstance(tts_backend, NeuTTSBackend):
        raise HTTPException(status_code=400, detail="Voice cloning requires the NeuTTS backend (TTS_BACKEND=neutts)")
    if not (file.filename or "").lower().endswith(".wav"):
        raise HTTPException(status_code=400, detail="Only .wav clips are supported")
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Clip too large (25MB max)")
    USER_REF_WAV.parent.mkdir(parents=True, exist_ok=True)
    USER_REF_WAV.write_bytes(data)
    USER_REF_TXT.unlink(missing_ok=True)  # force re-transcription of the new clip, never reuse the old transcript
    status = await tts_backend.refresh_reference()
    return {"success": True, **status}


@app.delete("/voice/reference", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def delete_voice_reference():
    """Reverts to the synthetic Pyttsx3 placeholder voice."""
    if not isinstance(tts_backend, NeuTTSBackend):
        raise HTTPException(status_code=400, detail="Voice cloning requires the NeuTTS backend (TTS_BACKEND=neutts)")
    USER_REF_WAV.unlink(missing_ok=True)
    USER_REF_TXT.unlink(missing_ok=True)
    status = await tts_backend.refresh_reference()
    return {"success": True, **status}


@app.get("/telegram/status")
async def telegram_status():
    """Whether Telegram is configured and the reply-polling loop is running -
    see telegram_bot.py. TelegramNotifier's status is a plain attribute (not
    a property doing I/O), so no executor offload is needed here."""
    return {"success": True, **telegram_notifier.status}


@app.post("/telegram/pair/start")
async def telegram_pair_start():
    """Real pairing flow (see telegram_pairing.py) -- generates a one-time
    code; message it to the bot and /telegram/pair/status will pick up the
    resulting chat_id and write it to .env for real."""
    return telegram_pairing.start_pairing()


@app.get("/telegram/pair/status")
async def telegram_pair_status():
    result = await telegram_pairing.check_pairing()
    return result


class MoaRequest(BaseModel):
    prompt: str
    reference_count: int = 3

@app.post("/llm/moa", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def llm_moa(req: MoaRequest):
    """Real Mixture-of-Agents: calls up to `reference_count` distinct
    configured LLM backends on the same prompt in parallel, then has the
    top-priority backend critically synthesize their answers."""
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")
    result = await run_moa(llm_backend, req.prompt.strip(), reference_count=req.reference_count)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "MoA failed"))
    return {"success": True, **result}


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
    await _fire_webhooks("agent_task_completed", {"agent_key": req.agent_key, "task_type": req.task_type, "result": result})
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


_DESKTOP_DIR = Path(os.path.expanduser("~")) / "Desktop"
_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

def _safe_desktop_path(filename: str) -> Path:
    """Resolve a user-supplied filename to a real, collision-free path under
    the real Desktop folder - strips directory components and Windows-illegal
    characters so this can't be used to write outside Desktop or clobber an
    existing file the user didn't ask to overwrite."""
    name = os.path.basename(filename).strip() or "output.txt"
    name = _UNSAFE_FILENAME_CHARS.sub("_", name)[:200]
    _DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
    path = _DESKTOP_DIR / name
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    n = 2
    while path.exists():
        path = _DESKTOP_DIR / f"{stem} ({n}){suffix}"
        n += 1
    return path


@app.post("/files/save-desktop", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def save_to_desktop(req: SaveFileRequest):
    """Write real content to a real file on the user's actual Desktop -
    used by the Kanban board (and anywhere else) when a task's output is
    meant to be a deliverable file rather than just an on-screen result."""
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="content is empty - nothing to save")
    path = _safe_desktop_path(req.filename)
    try:
        path.write_text(req.content, encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write file: {exc}")
    return {"success": True, "path": str(path), "filename": path.name}


# ---------------------------------------------------------------------------
# Arm/disarm safety switch -- a time-boxed alternative to a one-off Telegram
# approval for a batch of risky actions (real shell commands, file
# writes/deletes/moves) -- see arm_switch.py.
# ---------------------------------------------------------------------------
class ArmRequest(BaseModel):
    duration_s: float = arm_switch.DEFAULT_ARM_SECONDS
    reason: Optional[str] = None


@app.post("/safety/arm", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def arm_safety_switch(req: ArmRequest):
    return arm_switch.arm(req.duration_s, req.reason)


@app.post("/safety/disarm", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def disarm_safety_switch():
    return arm_switch.disarm()


@app.get("/safety/status", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def safety_switch_status():
    return arm_switch.status()


# ---------------------------------------------------------------------------
# Backups -- see backup_tool.py.
# ---------------------------------------------------------------------------
@app.get("/backups", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def list_backups_route():
    return {"success": True, "backups": list_backups()}


@app.post("/backups", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def create_backup_route():
    if not arm_switch.is_armed():
        approved = await telegram_notifier.request_approval(
            "Nancy wants to: create a backup zip of your data/skills/.env", timeout=120.0
        )
        if not approved:
            raise HTTPException(status_code=403, detail="User did not approve this backup.")
    return create_backup()


# ---------------------------------------------------------------------------
# Memory Wiki -- see memory/wiki_store.py.
# ---------------------------------------------------------------------------
class WikiPageCreateRequest(BaseModel):
    title: str
    claim: str
    evidence: List[str] = []
    provenance: str = "conversation"
    contradiction_of: Optional[str] = None
    body: str = ""


@app.get("/memory/wiki", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def list_wiki_pages():
    return {"success": True, "pages": [p.to_dict() for p in wiki_store.list_pages()]}


@app.post("/memory/wiki", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def create_wiki_page(req: WikiPageCreateRequest):
    if not req.title.strip() or not req.claim.strip():
        raise HTTPException(status_code=400, detail="title and claim are required")
    page = wiki_store.create_page(req.title, req.claim, req.evidence, req.provenance, req.contradiction_of, req.body)
    return {"success": True, "page": page.to_dict()}


@app.get("/memory/wiki/contradictions", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def list_wiki_contradictions():
    return {"success": True, "contradictions": wiki_store.find_contradictions()}


@app.get("/memory/wiki/{slug}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def get_wiki_page(slug: str):
    page = wiki_store.get_page(slug)
    if page is None:
        raise HTTPException(status_code=404, detail="wiki page not found")
    return {"success": True, "page": page.to_dict()}


# ---------------------------------------------------------------------------
# Journey timeline -- see memory/journey.py.
# ---------------------------------------------------------------------------
@app.get("/memory/journey", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def get_journey_timeline(limit: int = 100):
    from memory import journey
    return {
        "success": True,
        "timeline": journey.build_timeline(memory_manager.graph, limit=limit),
        "stats": journey.summary_stats(memory_manager.graph),
    }


# ---------------------------------------------------------------------------
# Commitments -- see memory/commitments.py.
# ---------------------------------------------------------------------------
@app.get("/memory/commitments", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def list_commitments_route(include_resolved: bool = False):
    return {"success": True, "commitments": [c.to_dict() for c in commitments.list_commitments(include_resolved)]}


@app.post("/memory/commitments/{commitment_id}/resolve", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def resolve_commitment_route(commitment_id: str):
    ok = commitments.resolve_commitment(commitment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="commitment not found")
    return {"success": True}


# ---------------------------------------------------------------------------
# Dream diary -- see memory/dreaming.py.
# ---------------------------------------------------------------------------
@app.get("/memory/dream-diary", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def get_dream_diary_route(limit: int = 20):
    from memory import dreaming
    return {"success": True, "entries": dreaming.get_dream_diary(limit=limit)}


# ---------------------------------------------------------------------------
# Verification evidence ledger -- see evidence_ledger.py.
# ---------------------------------------------------------------------------
@app.get("/evidence", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def list_evidence(limit: int = 50, kind: Optional[str] = None):
    return {"success": True, "evidence": evidence_ledger.query_evidence(limit=limit, kind=kind)}


# ---------------------------------------------------------------------------
# Lifecycle hooks -- see lifecycle_hooks.py.
# ---------------------------------------------------------------------------
@app.get("/hooks", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def list_hooks_route():
    return {"success": True, **lifecycle_hooks.list_hooks()}


@app.post("/hooks/{event}/test", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def test_hook_route(event: str):
    return await lifecycle_hooks.test_hook(event)


# ---------------------------------------------------------------------------
# Debug report sharing -- see debug_share.py.
# ---------------------------------------------------------------------------
@app.post("/debug/share", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def share_debug_report_route(local_only: bool = False):
    return await share_debug_report(local_only=local_only)


# ---------------------------------------------------------------------------
# Paired nodes -- see node_host.py / approval_policy.py / node_agent_stub.py.
# ---------------------------------------------------------------------------
class NodeRegisterRequest(BaseModel):
    node_id: str
    base_url: str
    shared_secret: str


class NodePolicyRequest(BaseModel):
    command: str
    decision: str


@app.get("/nodes", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def list_nodes_route():
    return {"success": True, "nodes": node_host.list_nodes()}


@app.post("/nodes", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def register_node_route(req: NodeRegisterRequest):
    node_host.register_node(req.node_id, req.base_url, req.shared_secret)
    return {"success": True}


@app.delete("/nodes/{node_id}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def remove_node_route(node_id: str):
    ok = node_host.remove_node(node_id)
    if not ok:
        raise HTTPException(status_code=404, detail="node not found")
    return {"success": True}


@app.get("/nodes/{node_id}/health", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def node_health_route(node_id: str):
    return await node_host.check_node_health(node_id)


@app.get("/nodes/{node_id}/policies", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def list_node_policies_route(node_id: str):
    return {"success": True, "policies": approval_policy.list_policies(node_id)}


@app.post("/nodes/{node_id}/policies", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def set_node_policy_route(node_id: str, req: NodePolicyRequest):
    node_host.set_node_policy(node_id, req.command, req.decision)
    return {"success": True}


# ---------------------------------------------------------------------------
# Egress proxy + coverage report -- see egress_proxy.py / coverage_proxy.py.
# ---------------------------------------------------------------------------
@app.post("/egress-proxy/start", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def start_egress_proxy_route():
    return await egress_proxy.start_egress_proxy()


@app.post("/egress-proxy/stop", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def stop_egress_proxy_route():
    return await egress_proxy.stop_egress_proxy()


@app.get("/egress-proxy/status", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def egress_proxy_status_route():
    return {"success": True, **egress_proxy.proxy_status()}


@app.post("/egress-proxy/install-ca", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def install_egress_ca_route():
    approved = await telegram_notifier.request_approval(
        "Nancy wants to install a local root CA certificate into your Windows Trusted Root store "
        "(needed for the egress-proxy's TLS interception). This is a system-trust change.",
        timeout=120.0,
    )
    if not approved:
        raise HTTPException(status_code=403, detail="User did not approve installing the CA certificate.")
    return egress_proxy.install_ca_certificate()


@app.post("/egress-proxy/coverage/enable", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def enable_coverage_route():
    return coverage_proxy.enable_coverage_tracking()


@app.get("/egress-proxy/coverage/report", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def coverage_report_route():
    return coverage_proxy.generate_coverage_report()


# ---------------------------------------------------------------------------
# LLM usage analytics -- see usage_analytics.py.
# ---------------------------------------------------------------------------
@app.get("/usage/llm", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def llm_usage_route():
    return {"success": True, **usage_analytics.get_usage_summary()}


# ---------------------------------------------------------------------------
# Achievements -- see achievements_store.py. Badges computed live from real
# already-persisted activity, not a separate incrementing counter system.
# ---------------------------------------------------------------------------
def _gather_activity_stats() -> Dict[str, Any]:
    from memory import dreaming

    agent_stats = agent_service.get_service_stats() if agent_service.is_ready() else {}
    evidence = evidence_ledger.query_evidence(limit=10_000)
    terminal_commands = sum(1 for e in evidence if e["kind"] == "terminal_command")
    file_writes = sum(1 for e in evidence if e["kind"] == "write_file")

    skill_usage = skill_loader._USAGE
    distinct_skills_used = sum(1 for u in skill_usage.values() if u.get("match_count", 0) > 0)

    return {
        "total_tasks": agent_stats.get("total_tasks", 0),
        "failed_tasks": agent_stats.get("failed_tasks", 0),
        "terminal_commands": terminal_commands,
        "file_writes": file_writes,
        "distinct_skills_used": distinct_skills_used,
        "total_skills": len(skill_loader.list_skills()),
        "total_memories": len(getattr(memory_manager.graph, "nodes", {})),
        "wiki_pages": len(wiki_store.list_pages()),
        "dream_cycles": len(dreaming.get_dream_diary(limit=10_000)),
        "uptime_hours": (_time.time() - _PROCESS_START_TIME) / 3600.0,
    }


@app.post("/documents/extract", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def extract_document_route(path: str):
    return doc_extraction.extract_document(path)


class MemoryImportPlanRequest(BaseModel):
    json_path: str


class SkillImportPlanRequest(BaseModel):
    source_dir: str


class SkillImportApplyRequest(BaseModel):
    source_dir: str
    skill_names: Optional[List[str]] = None


@app.post("/config-migration/memory/plan", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def plan_memory_import_route(req: MemoryImportPlanRequest):
    return config_migration.plan_memory_import(req.json_path)


@app.post("/config-migration/memory/apply", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def apply_memory_import_route(req: MemoryImportPlanRequest):
    approved = await telegram_notifier.request_approval(f"Nancy wants to import memories from {req.json_path}", timeout=120.0)
    if not approved:
        raise HTTPException(status_code=403, detail="User did not approve this memory import.")
    return await config_migration.apply_memory_import(req.json_path, memory_manager.graph)


@app.post("/config-migration/skills/plan", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def plan_skill_import_route(req: SkillImportPlanRequest):
    return config_migration.plan_skill_import(req.source_dir)


@app.post("/config-migration/skills/apply", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def apply_skill_import_route(req: SkillImportApplyRequest):
    approved = await telegram_notifier.request_approval(f"Nancy wants to import skills from {req.source_dir}", timeout=120.0)
    if not approved:
        raise HTTPException(status_code=403, detail="User did not approve this skill import.")
    return config_migration.apply_skill_import(req.source_dir, req.skill_names)


class WorkflowRunRequest(BaseModel):
    key: str
    title: str
    steps: List[Dict[str, Any]]


@app.post("/workflows/run", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def run_workflow_route(req: WorkflowRunRequest):
    template = workflow_engine.WorkflowTemplate(
        key=req.key, title=req.title,
        steps=[workflow_engine.WorkflowStep(name=s["name"], type=s["type"], payload=s.get("payload", {})) for s in req.steps],
    )
    return await workflow_engine.run_workflow(template)


@app.post("/workflows/runs/{run_id}/resume", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def resume_workflow_route(run_id: str):
    return await workflow_engine.resume_run(run_id)


@app.get("/workflows/runs", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def list_workflow_runs_route():
    return {"success": True, "runs": workflow_engine.list_runs()}


@app.get("/workflows/runs/{run_id}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def get_workflow_run_route(run_id: str):
    run = workflow_engine.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {"success": True, "run": run}


@app.get("/achievements", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def list_achievements_route():
    activity = _gather_activity_stats()
    unlocked = achievements_store.compute_unlocked(activity)
    unlocked_keys = {a["key"] for a in unlocked}
    all_ach = achievements_store.all_achievements()
    return {
        "success": True,
        "unlocked": unlocked,
        "locked": [a for a in all_ach if a["key"] not in unlocked_keys],
        "activity": activity,
    }


# ---------------------------------------------------------------------------
# REST routes - Missions (AI Workflow Orchestrator)
#
# A mission is a real, persisted entity (data/missions.json - see
# missions_store.py) that moves through the real pipeline: planning ->
# reasoning -> dependency_resolution -> agent_assignment -> execution ->
# validation -> human_approval -> deployment -> completed. Every stage
# transition publishes a real event over event_bus, which the WebSocket
# subscriber above (_broadcast_domain_event) pushes to every connected
# browser tab live - the frontend's board is a projection of this state,
# not an independent localStorage-backed app.
# ---------------------------------------------------------------------------

def _summarize_agent_result(result: Dict[str, Any]) -> str:
    """Same rules as the frontend's summarizeResult() (lib/nancy/agent-client.ts)
    -- kept in sync deliberately so a mission dispatched server-side reads the
    same way a manually-run agent result does."""
    if not result.get("success"):
        return str(result.get("error") or "Task failed - no further detail returned")
    for key in ("response", "result", "synthesis", "summary", "message"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Completed - see full details"


_MISSION_SYNTHESIS_PROMPT = """A mission was split across specialist agents chosen by the user. Combine their real results into one clear, coherent answer.

Mission: {goal}

Agent results:
{results}

Write a concise synthesis (a few sentences to a short paragraph). Do not repeat the raw JSON -- summarize what was actually found/done, and note if any agent failed.
"""


async def _run_mission_agents_parallel(goal: str, agent_keys: List[str]) -> Dict[str, Any]:
    """Runs every explicitly-assigned agent on the same mission goal in real
    parallel (asyncio.gather, not sequential), then -- if more than one ran --
    synthesizes their genuine outputs with one LLM call. Mirrors
    DispatcherAgent's own run-then-synthesize shape (agents_used/synthesis/
    sub_results) so _summarize_agent_result and the frontend's result view
    read it identically either way, but skips DispatcherAgent's own LLM
    routing step since the user already picked the agents explicitly."""
    async def _run_one(agent_key: str) -> Dict[str, Any]:
        result = await agent_service.run(agent_key, {"type": "query", "query": goal}, timeout=60.0)
        return {"agent_key": agent_key, "result": result}

    sub_results = await asyncio.gather(*[_run_one(k) for k in agent_keys], return_exceptions=True)
    clean_results = []
    for r in sub_results:
        if isinstance(r, Exception):
            clean_results.append({"agent_key": "unknown", "result": {"success": False, "error": str(r)}})
        else:
            clean_results.append(r)

    any_success = any(bool(r["result"].get("success")) for r in clean_results)
    if len(clean_results) == 1:
        synthesis = _summarize_agent_result(clean_results[0]["result"])
    else:
        results_text = "\n\n".join(
            f"[{r['agent_key']}] {json.dumps(r['result'], default=str)[:800]}" for r in clean_results
        )
        try:
            synthesis = await asyncio.wait_for(
                llm_backend.generate(
                    _MISSION_SYNTHESIS_PROMPT.format(goal=goal, results=results_text),
                    max_tokens=500, temperature=0.5,
                ),
                timeout=25.0,
            )
            synthesis = synthesis.strip()
        except Exception as e:
            synthesis = f"(Synthesis unavailable: {e}) See individual agent results."

    return {
        "success": any_success,
        "agents_used": [r["agent_key"] for r in clean_results],
        "synthesis": synthesis,
        "sub_results": clean_results,
    }


async def _dispatch_mission(mission_id: str) -> None:
    """Real server-side execution of a mission that just entered the
    Execution stage with an agent assigned - mirrors the honest
    auto-dispatch behaviour the Kanban board used to do client-side, now
    server-driven so every connected tab (not just the one that dragged the
    card) sees it live via MISSION_STARTED/MISSION_COMPLETED events. Two real
    paths: explicit multi-agent (mission.assigned_agents, run in parallel and
    synthesized) or single-agent (mission.assigned_agent -- includes the
    "dispatcher" key, which does its own internal multi-agent routing)."""
    mission = mission_store.get(mission_id)
    if mission is None or not (mission.assigned_agent or mission.assigned_agents):
        return
    mission_store.set_dispatched(mission_id)
    started_snapshot = mission_store.get(mission_id)
    await event_bus.publish("MISSION_STARTED", {"mission": started_snapshot.to_public_dict()})

    query = mission.description or mission.title
    if mission.assigned_agents:
        result = await _run_mission_agents_parallel(query, mission.assigned_agents)
    else:
        # 100s, not agent_service.run's normal 60s default -- the "dispatcher"
        # agent key does its own internal route+run+synthesize sequence
        # (up to ~90s worst case: 20s routing + 45s sub-agent + 25s synthesis),
        # which the generic 60s default was silently truncating.
        result = await agent_service.run(mission.assigned_agent, {"type": "query", "query": query}, timeout=100.0)
    success = bool(result.get("success"))
    text = _summarize_agent_result(result)
    mission_store.record_result(mission_id, success=success, text=text)

    next_stage = "validation" if success else "agent_assignment"
    try:
        updated = mission_store.transition(mission_id, next_stage)
    except MissionError:
        updated = mission_store.get(mission_id)
    await event_bus.publish(
        "MISSION_COMPLETED" if success else "MISSION_UPDATED",
        {"mission": updated.to_public_dict(), "result": result},
    )


@app.get("/missions")
async def list_missions():
    return {"success": True, "missions": [m.to_public_dict() for m in mission_store.list()]}


@app.post("/missions", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def create_mission(req: MissionCreateRequest):
    try:
        mission = mission_store.create(
            req.title, description=req.description, owner=req.owner, priority=req.priority,
            risk=req.risk, estimated_cost=req.estimated_cost, due_date=req.due_date,
            tags=req.tags, dependencies=req.dependencies, subtasks=req.subtasks,
            assigned_agent=req.assigned_agent, assigned_agents=req.assigned_agents,
        )
    except MissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await event_bus.publish("MISSION_CREATED", {"mission": mission.to_public_dict()})
    return {"success": True, "mission": mission.to_public_dict()}


@app.patch("/missions/{mission_id}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def update_mission(mission_id: str, req: MissionUpdateRequest):
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    try:
        mission = mission_store.update(mission_id, **fields)
    except MissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if mission is None:
        raise HTTPException(status_code=404, detail="mission not found")
    await event_bus.publish("MISSION_UPDATED", {"mission": mission.to_public_dict()})
    return {"success": True, "mission": mission.to_public_dict()}


@app.post("/missions/{mission_id}/assign", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def assign_mission_route(mission_id: str, req: MissionAssignRequest):
    if req.agent_keys:
        mission = mission_store.assign_multi(mission_id, req.agent_keys)
    else:
        mission = mission_store.assign(mission_id, req.agent_key)
    if mission is None:
        raise HTTPException(status_code=404, detail="mission not found")
    await event_bus.publish("MISSION_ASSIGNED", {"mission": mission.to_public_dict()})
    return {"success": True, "mission": mission.to_public_dict()}


@app.post("/missions/{mission_id}/transition", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def transition_mission_route(mission_id: str, req: MissionTransitionRequest):
    try:
        mission = mission_store.transition(mission_id, req.stage)
    except MissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await event_bus.publish("MISSION_UPDATED", {"mission": mission.to_public_dict()})
    if req.stage == "execution" and (mission.assigned_agent or mission.assigned_agents):
        asyncio.create_task(_dispatch_mission(mission_id))
    return {"success": True, "mission": mission.to_public_dict()}


@app.post("/missions/{mission_id}/cancel", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def cancel_mission_route(mission_id: str):
    mission = mission_store.cancel(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="mission not found")
    await event_bus.publish("MISSION_CANCELLED", {"mission": mission.to_public_dict()})
    return {"success": True, "mission": mission.to_public_dict()}


@app.delete("/missions/{mission_id}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def delete_mission_route(mission_id: str):
    if not mission_store.delete(mission_id):
        raise HTTPException(status_code=404, detail="mission not found")
    await event_bus.publish("MISSION_DELETED", {"mission_id": mission_id})
    return {"success": True}


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
                client_turn_id = message.get("turn_id")
                logger.info("Received %s: %s", msg_type, text[:80])

                # Fire-and-forget: start_turn cancels any still-running previous
                # turn and spawns this one as its own task, so the receive loop
                # stays free to read the next message immediately instead of
                # blocking on the LLM/TTS pipeline for this one. See
                # _run_chat_turn for the actual streaming generation + TTS work.
                manager.start_turn(
                    websocket,
                    lambda turn_id, _text=text: _run_chat_turn(websocket, turn_id, _text),
                    turn_id=client_turn_id,
                )

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
    logger.info("Nancy/Billion backend starting up...")
    # Initialise all 29 specialized agents in background so startup is fast
    asyncio.create_task(_init_agents())
    telegram_notifier.set_chat_handler(_telegram_chat_handler)
    telegram_notifier.start_polling()
    asyncio.create_task(_daily_briefing_loop())
    asyncio.create_task(_cron_execution_loop())
    asyncio.create_task(_economic_calendar_loop())
    asyncio.create_task(_prewarm_tts())
    asyncio.create_task(_prewarm_memory_embeddings())
    asyncio.create_task(mcp_manager.connect_all())


async def _prewarm_tts() -> None:
    """NeuTTS's first-ever synthesis call constructs the GGUF backbone +
    ONNX codec from scratch (cold model load), which can take a long time and
    holds NeuTTSBackend._model_lock for its entire duration -- confirmed live
    to exceed even a 60s timeout on this hardware. Paying that cost here,
    once, at startup means a user's actual first message doesn't have to."""
    try:
        await tts_backend.synthesize("Systems online.")
        logger.info("TTS backend pre-warmed.")
    except Exception as e:
        logger.warning("TTS pre-warm failed (non-fatal, will retry on first real request): %s", e)


async def _prewarm_memory_embeddings() -> None:
    """SentenceTransformerEmbedding's model download+load (memory/graph.py)
    is a real, potentially multi-second blocking call on its first use --
    since MemoryGraph/MemoryManager's interface is synchronous throughout
    the codebase (not worth an async rewrite of every call site for what's
    normally a ~10-50ms embed() once warm), run that one first call here in
    an executor at startup instead of letting a user's first memory-touching
    message pay for it."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, memory_manager.graph.embedding_engine.embed, "Systems online.")
        logger.info("Memory embedding model pre-warmed.")
    except Exception as e:
        logger.warning("Memory embedding pre-warm failed (non-fatal): %s", e)


# Local time, 24h format -- override in .env if 07:30 isn't the right moment.
DAILY_BRIEFING_HOUR = int(os.getenv("DAILY_BRIEFING_HOUR", "7"))
DAILY_BRIEFING_MINUTE = int(os.getenv("DAILY_BRIEFING_MINUTE", "30"))


async def _daily_briefing_loop() -> None:
    """Pushes Nancy's full personalized briefing to Telegram every day at
    DAILY_BRIEFING_HOUR:DAILY_BRIEFING_MINUTE (07:30 local time by default)
    with no user action required -- the same real-data briefing the boot
    greeting builds (see _build_real_personal_context), delivered
    proactively instead of only on demand. No-ops safely (logs and moves on)
    if Telegram isn't configured, same as every other telegram_notifier.send.
    """
    while True:
        now = datetime.now()
        target = now.replace(
            hour=DAILY_BRIEFING_HOUR, minute=DAILY_BRIEFING_MINUTE, second=0, microsecond=0
        )
        if target <= now:
            target += timedelta(days=1)
        wait_s = (target - now).total_seconds()
        logger.info(
            "Daily briefing scheduled for %s (in %.0f min)", target.isoformat(), wait_s / 60
        )
        await asyncio.sleep(wait_s)
        try:
            context = await _build_real_personal_context()
            coordinator = IntelligentStartupCoordinator(persona=startup_coordinator.persona)
            startup_data = await coordinator.startup_with_context(context)
            await telegram_notifier.send(f"Morning briefing, Sir:\n\n{startup_data['greeting']}")
        except Exception as e:
            logger.exception("Daily briefing failed: %s", e)
        # Loop back around -- next iteration recomputes tomorrow's target.


async def _cron_execution_loop() -> None:
    """Checks user-created cron_store jobs every 30s and actually fires
    whichever are due -- this is what makes the Cron Jobs page's "create
    job" button real instead of a form that writes to a list nothing ever
    reads. Four real action types: push a Telegram message, run a real
    agent task, run a real skill's procedure (optionally with tool access),
    or run a real shell command (optionally with tool access) -- optionally
    pushing the result to Telegram too, same as _run_long_agent_task's
    "notify when done" pattern."""
    while True:
        await asyncio.sleep(30)
        try:
            now = datetime.now()
            for job in cron_store.due_jobs(now):
                try:
                    if job.action_type == "telegram_message":
                        text = job.action_payload.get("text", "")
                        await telegram_notifier.send(text)
                        cron_store.mark_run(job.id, "sent telegram message")
                        await _fire_webhooks("cron_job_ran", {"job_id": job.id, "job_name": job.name, "result": "sent telegram message"})
                    elif job.action_type == "agent_task":
                        agent_key = job.action_payload.get("agent_key")
                        task_type = job.action_payload.get("task_type", "query")
                        payload = job.action_payload.get("payload", {})
                        if agent_service.is_ready() and agent_key:
                            result = await agent_service.run(agent_key, {"type": task_type, **payload}, timeout=60.0)
                            summary = json.dumps(result)[:300]
                            cron_store.mark_run(job.id, summary)
                            if telegram_notifier.status["available"]:
                                await telegram_notifier.send(f"Cron job \"{job.name}\" ran:\n\n{summary}")
                            await _fire_webhooks("cron_job_ran", {"job_id": job.id, "job_name": job.name, "result": result})
                        else:
                            cron_store.mark_run(job.id, "skipped: agent service not ready")
                    elif job.action_type == "run_skill":
                        summary = await _run_cron_skill(job.action_payload, f"scheduled job \"{job.name}\"")
                        cron_store.mark_run(job.id, summary)
                        if telegram_notifier.status["available"]:
                            await telegram_notifier.send(f"Cron job \"{job.name}\" ran:\n\n{summary}")
                        await _fire_webhooks("cron_job_ran", {"job_id": job.id, "job_name": job.name, "result": summary})
                    elif job.action_type == "terminal_command":
                        summary = await _run_cron_terminal_command(job.action_payload, f"Scheduled job \"{job.name}\"")
                        cron_store.mark_run(job.id, summary)
                        if telegram_notifier.status["available"]:
                            await telegram_notifier.send(f"Cron job \"{job.name}\" ran:\n\n{summary}")
                        await _fire_webhooks("cron_job_ran", {"job_id": job.id, "job_name": job.name, "result": summary})
                    elif job.action_type == "run_script":
                        summary = await _run_cron_script(job.action_payload, f"scheduled job \"{job.name}\"")
                        cron_store.mark_run(job.id, summary)
                        if telegram_notifier.status["available"] and not summary.startswith("(silent"):
                            await telegram_notifier.send(f"Cron job \"{job.name}\" ran:\n\n{summary}")
                        await _fire_webhooks("cron_job_ran", {"job_id": job.id, "job_name": job.name, "result": summary})
                    elif job.action_type == "channel_message":
                        summary = await _run_cron_channel_message(job.action_payload, f"scheduled job \"{job.name}\"")
                        cron_store.mark_run(job.id, summary)
                        await _fire_webhooks("cron_job_ran", {"job_id": job.id, "job_name": job.name, "result": summary})
                    elif job.action_type == "memory_consolidate":
                        summary = await _run_cron_memory_consolidate(job.action_payload, f"scheduled job \"{job.name}\"")
                        cron_store.mark_run(job.id, summary)
                        await _fire_webhooks("cron_job_ran", {"job_id": job.id, "job_name": job.name, "result": summary})
                    elif job.action_type == "commitment_checkin":
                        summary = await _run_cron_commitment_checkin(job.action_payload, f"scheduled job \"{job.name}\"")
                        cron_store.mark_run(job.id, summary)
                        await _fire_webhooks("cron_job_ran", {"job_id": job.id, "job_name": job.name, "result": summary})
                except Exception as e:
                    logger.exception("Cron job %s failed: %s", job.name, e)
                    cron_store.mark_run(job.id, f"error: {e}")
        except Exception:
            logger.exception("Cron execution loop tick failed")


async def _run_cron_skill(action_payload: Dict[str, Any], trigger_name: str = "job") -> str:
    """Runs a skill's real instructions on demand -- e.g. a nightly "check
    git status and report" cron job, or an inbound webhook, using the
    git-and-github skill. Goes through Claude's real tool-use loop (file/
    terminal tools) so the skill can actually act, not just narrate what it
    would do. Plain (payload, name) params rather than a cron_store.CronJob
    so both the cron loop and inbound webhooks can share this one real
    execution path instead of each having their own copy."""
    extra_context = action_payload.get("context", "")
    bundle_name = action_payload.get("bundle_name", "")

    if bundle_name:
        bundle = skill_bundle_store.get_by_name(bundle_name)
        if bundle is None:
            return f"Unknown skill bundle: {bundle_name!r}"
        skills = [skill_loader.get_skill(n) for n in bundle.skill_names]
        skills = [s for s in skills if s is not None]
        if not skills:
            return f"Skill bundle {bundle_name!r} has no valid skills"
        skills_block = "\n\n".join(f"### Skill: {s.name}\n{s.instructions}" for s in skills)
    else:
        skill_name = action_payload.get("skill_name", "")
        skill = skill_loader.get_skill(skill_name)
        if skill is None:
            return f"Unknown skill: {skill_name!r}"
        skills_block = f"### Skill: {skill.name}\n{skill.instructions}"

    if not os.getenv("ANTHROPIC_API_KEY"):
        return "Cannot run skill: ANTHROPIC_API_KEY not configured (tool-use requires Claude)"

    prompt = (
        f"{BASE_SYSTEM_PROMPT}\n\nA {trigger_name} triggered this skill (or skill bundle) -- follow its "
        f"instructions and actually do the work, don't just describe it. If more than one skill is listed, "
        f"follow all of them together as one combined procedure.\n\n"
        f"{skills_block}\n\n"
        f"Additional context for this run: {extra_context or '(none)'}"
    )
    claude = AnthropicLLM()
    resp = await asyncio.wait_for(
        claude.generate_with_tools(
            prompt, FILE_TOOLS + terminal_tool.TERMINAL_TOOLS + [CREATE_SUBAGENT_TOOL, CANVAS_TOOL] + mcp_manager.list_plugin_tools() + WEB_TOOLS + COMPUTER_USE_TOOLS + UTILITY_TOOLS + BACKUP_TOOLS + HOME_ASSISTANT_TOOLS + SPOTIFY_TOOLS + NODE_TOOLS + DIFF_TOOLS + doc_extraction.DOC_EXTRACTION_TOOLS, _execute_file_tool, max_tokens=1024
        ),
        timeout=120.0,
    )
    return _enforce_sir(resp)[:800]


async def _run_cron_terminal_command(action_payload: Dict[str, Any], trigger_name: str = "job") -> str:
    """Runs a real shell command on demand (cron job or inbound webhook),
    through the exact same safe-command-allowlist-or-approval gate every
    other terminal_tool caller goes through -- a scheduled/triggered job
    doesn't get to skip approval for a destructive command just because a
    human isn't watching in real time."""
    command = action_payload.get("command", "")
    cwd = action_payload.get("cwd")
    if not terminal_tool._is_safe_command(command):
        approved = await telegram_notifier.request_approval(
            f"\"{trigger_name}\" wants to run a command:\n\n{command}", timeout=120.0
        )
        if not approved:
            return "Not approved: command requires explicit approval and none was given in time"
    result = await terminal_tool.execute_command(command, cwd=cwd)
    if result.get("success"):
        return (result.get("stdout") or "(no output)")[:800]
    return f"Command failed: {result.get('error') or result.get('stderr') or 'unknown error'}"


async def _run_cron_channel_message(action_payload: Dict[str, Any], trigger_name: str = "job") -> str:
    """Sends a real message through any registered channels.Channel (see
    channels/registry.py) -- the general-purpose sibling of the
    Telegram-specific telegram_message action, for any new channel that
    registers itself (ntfy, Home Assistant, etc.)."""
    from channels.registry import get_channel
    channel_name = action_payload.get("channel", "")
    message = action_payload.get("message", "")
    channel = get_channel(channel_name)
    if channel is None:
        return f"error: channel {channel_name!r} is not registered/configured"
    sent = await channel.send(message)
    return "sent" if sent else f"error: {channel_name} send failed"


async def _run_cron_memory_consolidate(action_payload: Dict[str, Any], trigger_name: str = "job") -> str:
    """Runs a real memory/dreaming.py light+deep+REM consolidation cycle
    over the live memory_manager.graph -- see memory/dreaming.py."""
    from memory import dreaming
    result = await dreaming.run_full_cycle(memory_manager.graph)
    return result["rem"]["entry"]["narrative"]


async def _run_cron_commitment_checkin(action_payload: Dict[str, Any], trigger_name: str = "job") -> str:
    """Sends a real Telegram reminder for unresolved commitments
    (memory/commitments.py), or stays silent if there's nothing open."""
    reminder = commitments.format_overdue_reminder()
    if reminder is None:
        return "(nothing open -- no reminder sent)"
    await telegram_notifier.send(reminder)
    return reminder


async def _run_cron_script(action_payload: Dict[str, Any], trigger_name: str = "job") -> str:
    """Runs a real sandboxed script (run_script_tool.py) and either delivers
    its stdout verbatim (no_agent=True -- a deterministic watchdog: "print a
    message only if X happened") or hands it to the dispatcher agent as real
    collected data to reason over (default) -- separates deterministic
    data-collection from the LLM call that turns it into a response."""
    script = action_payload.get("script", "")
    no_agent = bool(action_payload.get("no_agent", False))
    result = await run_script_tool.run_script(script, no_agent=no_agent)
    if not result.get("success"):
        return f"error: {result.get('error')}"
    if result.get("silent"):
        return "(silent — script reported nothing new)"

    stdout = result.get("stdout", "")
    if no_agent:
        return stdout or "(script produced no output)"

    if not agent_service.is_ready():
        return "skipped: agent service not ready"
    goal = action_payload.get("prompt") or f"Summarize what this {trigger_name} found and whether it needs attention."
    query = f"The following data was just collected by a real pre-run script:\n\n{stdout}\n\n{goal}"
    agent_result = await agent_service.run("dispatcher", {"type": "query", "query": query}, timeout=90.0)
    return _summarize_agent_result(agent_result)


async def _economic_calendar_loop() -> None:
    """Track NFP/CPI/FOMC releases and fire a real alert the moment a tracked
    release's actual value appears: Telegram push plus WebSocket broadcast.
    Polls FRED every 15 min normally, every 10s inside a live release window
    so a NFP/CPI print gets caught within ~10s of actually posting, not 15
    minutes late. No-ops safely if FRED_API_KEY isn't configured."""
    while True:
        try:
            newly_alerted = await economic_calendar.poll_once()
            for event in newly_alerted:
                text = economic_calendar.compose_alert_text(event)
                await telegram_notifier.send(f"[alert] {text}")
                await manager.broadcast(json.dumps({"type": "economic_alert", "text": text, **event}))
                logger.info("Economic calendar alert fired: %s", text)
        except Exception:
            logger.exception("Economic calendar loop tick failed")
        await asyncio.sleep(economic_calendar.next_poll_interval_s())


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
    await mcp_manager.disconnect_all()
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