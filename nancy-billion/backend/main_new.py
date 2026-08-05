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
from contextvars import ContextVar
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
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
from llm import llm_backend, select_llm_for_task, AnthropicLLM, LLM_PROVIDER_CATALOG, generate_with_tools_openai_compat
import file_access
import subagent_factory
import terminal_tool
import skill_loader
import conversation_log
from mcp_client import mcp_manager, plugin_store
from moa import run_moa
from inbound_webhooks_store import inbound_webhook_store
from canvas_store import canvas_store
from blueprint_catalog import CATALOG as BLUEPRINT_CATALOG, get_blueprint, blueprint_catalog_entry, fill_blueprint, BlueprintFillError
from skill_bundles import skill_bundle_store
import run_script_tool
from web_tool import fetch_url, web_search, extract_urls, WEB_TOOLS
from media_tools import generate_image, MEDIA_TOOLS
from research_tools import search_arxiv, get_prediction_markets, RESEARCH_TOOLS
from document_tools import (
    create_word_document, create_excel_spreadsheet, create_pdf_document,
    create_powerpoint_presentation, DOCUMENT_TOOLS,
)
from email_tools import send_email, list_recent_emails, EMAIL_TOOLS
from jupyter_tools import run_python_kernel, restart_python_kernel, JUPYTER_TOOLS
import browser_tool
import everyday_tools
import archive_tools
import network_tools
import personal_tools
from providers.bootstrap import load_all_providers
from channels.bootstrap import load_all_channels
import security_lint
import arm_switch
import lockdown_switch
import focus_mode
import macro_store
import self_maintenance
import meeting_prep_store
import pattern_suggestions
import presence_store
import profiles_store
import household_voice_id
import alert_center
import git_tool
import docker_tool
import process_control
import flow_engine
import langflow_client
from llm_task import structured_llm_call, UTILITY_TOOLS
from workspace_uri import resolve_oc_path
from backup_tool import create_backup, list_backups, BACKUP_TOOLS
from disk_cleanup import ensure_bootstrap_script
from channels.home_assistant import HOME_ASSISTANT_TOOLS
from providers.spotify_tool import SPOTIFY_TOOLS, handle_spotify_tool
from providers import google_calendar
from memory import wiki_store, commitments
import evidence_ledger
import lifecycle_hooks
import lsp_client
from diff_render import post_diff_to_canvas
import doc_extraction
import notebook_tools
import self_healing
import watch_store
import voice_id
import config_migration
import workflow_engine
import mdns_discovery
import fleet.manager as fleet_manager
from debug_share import share_debug_report
import node_host
import approval_policy
import egress_proxy
import coverage_proxy
import usage_analytics
import achievements_store

# The node_host node ID a native, on-the-real-desktop node_agent_stub.py is
# expected to register under -- see open_application's dispatch logic in
# _execute_file_tool. Overridable in case a real setup names it differently.
HOST_NODE_ID = os.getenv("HOST_NODE_ID", "host")

# Real-time tool-use progress visibility. Set at the top of _run_chat_turn --
# each turn runs as its own asyncio.Task (see ConnectionManager.start_turn),
# and a ContextVar's value is isolated per-Task, so concurrent turns on
# different websockets never cross-broadcast. None outside an active web/
# voice turn (e.g. the Telegram path never sets this), so
# _broadcast_tool_progress below silently no-ops there rather than erroring.
_current_turn_ctx: ContextVar[Optional[tuple]] = ContextVar("_current_turn_ctx", default=None)

# Set alongside _current_turn_ctx, same per-Task isolation. None means "this
# turn had no attached audio to check" (typed text, or voice_id isn't
# enrolled) -- there's nothing to gate on, so sensitive tools fall back to
# the plain approval flow. A real dict means a live voice sample WAS checked
# for this turn; {"match": False, ...} is what _execute_file_tool's approval
# gate escalates on (see _request_approval).
_current_voice_match: ContextVar[Optional[Dict[str, Any]]] = ContextVar("_current_voice_match", default=None)

# Set alongside _current_voice_match, same per-Task isolation. The household
# profile id household_voice_id.identify_speaker() matched THIS turn's real
# audio against, or None if nothing was enrolled/matched -- see
# _active_memory_manager() below, the one place this actually changes
# behavior (which MemoryGraph a turn's context/extraction uses).
_current_speaker_profile_id: ContextVar[Optional[str]] = ContextVar("_current_speaker_profile_id", default=None)

# This turn's real decoded raw audio (float32 PCM), if any was captured --
# lets the enroll_profile_voice tool actually enroll the person speaking
# RIGHT NOW without a separate out-of-band upload step. None for a typed
# turn or one with no attached audio.
_current_turn_audio: ContextVar[Optional[Any]] = ContextVar("_current_turn_audio", default=None)


async def _broadcast_tool_progress(name: str, tool_input: Dict[str, Any]) -> None:
    """Pushed to the UI right before each tool call actually runs, during a
    multi-round tool-use loop -- previously nothing was visible until the
    whole loop finished (which can take 30-90s across several rounds and
    several backend fallback attempts), unlike Claude Code's own real-time
    visibility into which tool is currently running. Passed as
    generate_with_tools'/generate_with_tools_openai_compat's on_tool_call."""
    ctx = _current_turn_ctx.get()
    if ctx is None:
        return
    websocket, turn_id = ctx
    try:
        await manager.send(
            json.dumps({"type": "tool_progress", "tool": name, "turn_id": turn_id}),
            websocket,
        )
    except Exception as e:
        logger.warning("Failed to broadcast tool progress: %s", e)

VOICE_CALL_TOOLS = [
    {
        "name": "place_phone_call",
        "description": "Place a real phone call that speaks a message via text-to-speech on the line. Requires a telephony provider (e.g. Twilio) to be configured.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to_number": {"type": "string", "description": "E.164 format, e.g. +15551234567"},
                "message": {"type": "string"},
            },
            "required": ["to_number", "message"],
        },
    },
]

APP_LAUNCHER_TOOLS = [
    {
        "name": "open_application",
        "description": (
            "Launch a real GUI application on the user's computer by name (e.g. 'chrome', 'notepad', "
            "'spotify', 'code', 'explorer', 'calculator'), or open a file/URL with its default (or a "
            "named) application -- the same as double-clicking an app icon or a file. For anything "
            "needing command-line flags, piped output, or a result to read back, use execute_command "
            "instead; this tool doesn't return the app's own output, only whether it launched."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Application name, or a file path/URL to open."},
                "args": {"type": "array", "items": {"type": "string"}, "description": "Optional extra arguments to pass to the application."},
            },
            "required": ["target"],
        },
    },
    {
        "name": "look_at_camera",
        "description": (
            "Open the user's real webcam, capture exactly ONE frame, and close it immediately -- for "
            "when the user explicitly asks you to look at something right now (e.g. 'take a look at my "
            "desk', 'walk me through setting this up', holding a device up to the camera). You'll "
            "actually SEE the captured image. Identify what's in it (a device's name/manufacturer if "
            "one is visible), and if the user needs help with it, follow up with web_search for real "
            "setup instructions or a tutorial. Only ever a single snapshot, never continuous/ambient -- "
            "there is no 'start watching' mode. Requires the user's explicit approval first, same as "
            "screen/mouse control."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "check_security_camera",
        "description": (
            "Fetch exactly ONE real snapshot from the configured security/doorbell camera "
            "(SECURITY_CAMERA_SNAPSHOT_URL) -- same on-demand-only, single-frame, no-ambient-watching "
            "model as look_at_camera, just pointed at an external camera feed instead of the local "
            "webcam. Use when the user explicitly asks to check the door/entrance/security feed. "
            "Requires the user's explicit approval first."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

BACKGROUND_TASK_TOOLS = [
    {
        "name": "run_background_task",
        "description": (
            "Start real independent work in the background -- the SAME tool arsenal this conversation "
            "has (files, terminal, web, browser, camera, everything), but it runs on its own without "
            "blocking this conversation. Use this for anything that takes a while, or that doesn't need "
            "you to babysit it. You will NOT see progress updates from it here -- you'll get exactly one "
            "notification (on Telegram, and in the web UI) when it's actually done, need-to-know only. "
            "It's also tracked as a real mission in Mission Control if the user wants to check on it "
            "before then. Give a self-contained description -- it has no memory of this conversation "
            "beyond what you put in the description."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"description": {"type": "string", "description": "What to do, in enough detail to work from independently."}},
            "required": ["description"],
        },
    },
]

CLIPBOARD_TOOLS = [
    {
        "name": "clipboard_read",
        "description": "Read the real current contents of the user's clipboard.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "clipboard_write",
        "description": "Copy real text to the user's clipboard (so they can paste it elsewhere).",
        "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    },
]

SMS_TOOLS = [
    {
        "name": "send_sms",
        "description": "Send a real SMS text message. Requires a telephony provider (e.g. Twilio) to be configured. Requires the user's explicit approval first.",
        "input_schema": {
            "type": "object",
            "properties": {"to_number": {"type": "string", "description": "E.164 format, e.g. +15551234567"}, "message": {"type": "string"}},
            "required": ["to_number", "message"],
        },
    },
    {
        "name": "trigger_sos",
        "description": (
            "Real emergency alert -- immediately texts (and attempts to call) EMERGENCY_CONTACT_NUMBER "
            "with the situation. Use only when the user genuinely indicates an emergency ('I need help', "
            "'call for help', explicit SOS). Deliberately NOT gated behind Telegram approval like every "
            "other sensitive action: the whole point is immediate action, and requiring approval would "
            "defeat it if the user is the one in trouble. Scoped to alerting a real designated personal "
            "contact -- this never contacts emergency services directly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"situation": {"type": "string", "description": "Brief description of what's happening, included in the alert."}},
            "required": [],
        },
    },
]

WATCH_TOOLS = [
    {
        "name": "create_watch",
        "description": (
            "Set up a real recurring watch: Billion checks it on a schedule and pushes one Telegram "
            "alert when it actually changes -- 'watch this product page and tell me when the price "
            "drops', 'let me know if this page changes', 'watch this GitHub repo for a new release', "
            "'watch for news about X'. By default fires once then stops (one_shot=true); set "
            "one_shot=false to keep alerting on every future change instead of just the first one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Page URL to watch ('text'/'price'), 'owner/repo' ('github_release'), or the search QUERY itself ('topic', e.g. 'SpaceX Starship launch')."},
                "description": {"type": "string", "description": "Short human-readable label for what's being watched, used in the alert."},
                "kind": {"type": "string", "enum": ["text", "price", "github_release", "topic"], "default": "text"},
                "target_price": {"type": "number", "description": "Required when kind is 'price' -- alert when the page's detected price drops to or below this."},
                "check_interval_minutes": {"type": "number", "description": "How often to check. Default 60, minimum 5."},
                "one_shot": {"type": "boolean", "description": "Stop watching after the first alert. Default true."},
            },
            "required": ["url", "description"],
        },
    },
    {
        "name": "list_watches",
        "description": "List all currently active (and recently stopped) watches Billion is tracking.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "delete_watch",
        "description": "Stop and remove a watch.",
        "input_schema": {"type": "object", "properties": {"watch_id": {"type": "string"}}, "required": ["watch_id"]},
    },
]

SECURITY_MODE_TOOLS = [
    {
        "name": "enable_lockdown",
        "description": (
            "Raise the security bar: while active, ANY sensitive command (file writes, terminal, SMS, "
            "calendar, phone calls, screen/browser control, agent creation, backups) requires a real, "
            "confirmed voice match to skip a Telegram approval prompt -- typed commands and unclear "
            "voice samples are treated as unverified and always trigger one, even during an armed "
            "session. Use when the user explicitly asks to 'lock down' / 'lock yourself down'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "duration_minutes": {"type": "number", "description": "Default 60, max 1440 (24h)."},
                "reason": {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "disable_lockdown",
        "description": "Turn off lockdown mode (also called 'stand down').",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "enable_focus_mode",
        "description": (
            "Notification triage: while active, informational Telegram pushes (self-healing status "
            "changes, watch alerts, scheduled telegram_message cron jobs) are queued instead of sent "
            "immediately -- approval requests are NEVER queued, they still arrive right away since "
            "they're genuinely blocking. Queued messages deliver as one digest when focus mode ends."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"duration_minutes": {"type": "number", "description": "Default 60, max 480 (8h)."}},
            "required": [],
        },
    },
    {
        "name": "disable_focus_mode",
        "description": "Turn off focus mode now and immediately deliver whatever was queued, as one digest.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

MACRO_TOOLS = [
    {
        "name": "create_macro",
        "description": (
            "Save a named 'scene macro' -- an ordered sequence of tool calls that runs together under "
            "one name (e.g. 'movie mode' = dim the lights via ha_call_service + open the media app via "
            "open_application). Each step still goes through its own normal safety gating when the "
            "macro runs -- creating the macro itself doesn't skip that, it just saves the sequence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "steps": {
                    "type": "array",
                    "description": "Steps to run in order.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool": {"type": "string", "description": "Name of any other real tool Billion has."},
                            "args": {"type": "object", "description": "That tool's arguments."},
                        },
                        "required": ["tool"],
                    },
                },
            },
            "required": ["name", "steps"],
        },
    },
    {
        "name": "run_macro",
        "description": "Run a saved scene macro by name, executing its steps in order.",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    },
    {
        "name": "list_macros",
        "description": "List all saved scene macros and their steps.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "delete_macro",
        "description": "Delete a saved scene macro.",
        "input_schema": {"type": "object", "properties": {"macro_id": {"type": "string"}}, "required": ["macro_id"]},
    },
    {
        "name": "schedule_macro",
        "description": (
            "Real time-based conditional trigger for a saved macro -- schedules it to run "
            "automatically every day at a given time (e.g. 'run movie mode every day at 9pm'), by "
            "creating a real cron job (action_type run_macro) rather than a new scheduling system. "
            "The macro must already exist (see create_macro)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "macro_name": {"type": "string"},
                "hour": {"type": "integer", "description": "0-23, local time."},
                "minute": {"type": "integer", "description": "0-59. Default 0."},
            },
            "required": ["macro_name", "hour"],
        },
    },
]

DEVICE_ROUTING_TOOLS = [
    {
        "name": "set_active_device",
        "description": (
            "Declare which connected device/tab should be treated as 'where the user currently is' -- "
            "e.g. 'follow me to the workshop' / 'I'm on my tablet now'. Proactive pushes (background "
            "task completion, self-healing/watch alerts) that would otherwise go to every connected "
            "tab get sent to this one instead, when it's actually connected; falls back to broadcasting "
            "to everyone if it isn't (never silently drops a real notification)."
        ),
        "input_schema": {"type": "object", "properties": {"device_label": {"type": "string"}}, "required": ["device_label"]},
    },
    {
        "name": "list_connected_devices",
        "description": "List the device labels currently connected (see register_device), and which one (if any) is the active follow-me target.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

PRESENCE_TOOLS = [
    {
        "name": "register_presence_device",
        "description": (
            "Real LAN-based presence tracking -- register a household member's device (their phone's "
            "LAN IP/hostname, a laptop, etc.) so Billion can tell when they're actually home/at their "
            "desk via a real periodic ICMP ping, no companion app needed. Optionally names a saved "
            "scene macro to run automatically when that person arrives or leaves -- the real 'if I'm "
            "home, dim the lights' conditional trigger."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "person_name": {"type": "string"},
                "host": {"type": "string", "description": "Hostname or LAN IP of their device."},
                "on_arrive_macro": {"type": "string", "description": "Optional saved macro name to run when this person arrives."},
                "on_leave_macro": {"type": "string", "description": "Optional saved macro name to run when this person leaves."},
            },
            "required": ["person_name", "host"],
        },
    },
    {
        "name": "list_presence_devices",
        "description": "List every registered presence-tracked device and its real current reachability.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "remove_presence_device",
        "description": "Stop tracking a presence device.",
        "input_schema": {"type": "object", "properties": {"device_id": {"type": "string"}}, "required": ["device_id"]},
    },
    {
        "name": "who_is_present",
        "description": "Real answer to 'who's home right now' -- every person with at least one currently-reachable registered device.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

# Household member profiles -- a few known people sharing this one
# deployment, each with their own memory context and (optionally) their own
# enrolled voice for real speaker identification (see profiles_store.py /
# household_voice_id.py). Not a login/auth system -- see PRESENCE_TOOLS
# above for the separate "who's home" LAN-presence concept.
PROFILE_TOOLS = [
    {
        "name": "create_profile",
        "description": "Create a new household member profile with its own memory context.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "list_profiles",
        "description": "List every household member profile.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "delete_profile",
        "description": "Delete a household member profile (does not delete their memory file on disk).",
        "input_schema": {"type": "object", "properties": {"profile_id": {"type": "string"}}, "required": ["profile_id"]},
    },
    {
        "name": "enroll_profile_voice",
        "description": (
            "Enroll THIS turn's speaker as the voice for a named household profile, so Billion can "
            "recognize them in future conversations and route memory to their own profile. Only works "
            "for a voice-originated turn (needs real captured audio, not typed text)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"profile_id": {"type": "string"}},
            "required": ["profile_id"],
        },
    },
    {
        "name": "who_is_speaking",
        "description": "Which household profile (if any) THIS turn's voice was identified as.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

SWARM_TOOLS = [
    {
        "name": "run_agent_swarm",
        "description": (
            "Real AI agent swarm: an LLM orchestrator decomposes a goal across up to 8 of Billion's real, "
            "currently-online specialized agents (research, coding, trading, science, etc.), runs them all "
            "in genuine parallel with a tailored subtask each, then synthesizes their real results into one "
            "answer. Use for goals that genuinely benefit from multiple specialist perspectives at once -- "
            "not a simple single-domain question."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "max_agents": {"type": "integer", "description": "Default/cap 8."},
            },
            "required": ["goal"],
        },
    },
]

FLOW_TOOLS = [
    {
        "name": "create_flow",
        "description": (
            "Create a real, executable visual flow -- a directed graph of nodes (each a real tool call, an "
            "LLM prompt, a flow input, or a flow output), wired together with {{node_id.field}} placeholders "
            "so one node's real output feeds another's input. Billion's own native equivalent of a Langflow-"
            "style pipeline, built on the same real tools/LLM this chat uses."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "nodes": {
                    "type": "array",
                    "description": 'Each: {"id": str, "kind": "tool"|"llm"|"input"|"output", "config": {...}, "label": str}.',
                    "items": {"type": "object"},
                },
                "edges": {
                    "type": "array",
                    "description": 'Each: {"source": node_id, "target": node_id}.',
                    "items": {"type": "object"},
                },
            },
            "required": ["name", "nodes", "edges"],
        },
    },
    {"name": "list_flows", "description": "List every saved flow.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_flow", "description": "Get one saved flow's full node/edge definition.", "input_schema": {"type": "object", "properties": {"flow_id": {"type": "string"}}, "required": ["flow_id"]}},
    {
        "name": "update_flow",
        "description": "Update a saved flow's name/nodes/edges.",
        "input_schema": {
            "type": "object",
            "properties": {"flow_id": {"type": "string"}, "name": {"type": "string"}, "nodes": {"type": "array", "items": {"type": "object"}}, "edges": {"type": "array", "items": {"type": "object"}}},
            "required": ["flow_id"],
        },
    },
    {"name": "delete_flow", "description": "Delete a saved flow.", "input_schema": {"type": "object", "properties": {"flow_id": {"type": "string"}}, "required": ["flow_id"]}},
    {
        "name": "run_flow",
        "description": "Real execution of a saved flow: runs every node in real topological order through Billion's actual tool dispatcher/LLM, returns the real output plus a per-node execution trace.",
        "input_schema": {
            "type": "object",
            "properties": {"flow_id": {"type": "string"}, "inputs": {"type": "object", "description": "Values for the flow's input nodes."}},
            "required": ["flow_id"],
        },
    },
]

LANGFLOW_TOOLS = [
    {
        "name": "list_langflow_flows",
        "description": (
            "List real flows from an actual connected Langflow instance (langflowai/langflow -- see "
            "docker-compose.yml's opt-in `langflow` profile). Requires that service to actually be running; "
            "fails with a real connection error otherwise, not a fake empty list."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_langflow_flow",
        "description": "Real execution of a flow inside an actual connected Langflow instance, by flow id or name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "flow_id_or_name": {"type": "string"},
                "input_value": {"type": "string"},
            },
            "required": ["flow_id_or_name", "input_value"],
        },
    },
]

TRADING_BACKTEST_TOOLS = [
    {
        "name": "list_trading_strategies",
        "description": "List every real trading strategy available to run_forex_backtest/run_crypto_backtest.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "run_forex_backtest",
        "description": (
            "Real forex strategy backtest -- fetches real historical daily rates (Frankfurter/ECB, or "
            "Yahoo Finance for XAU/XAG) and runs the requested strategy through a real event-driven "
            "backtest, a Monte Carlo permutation significance test, and walk-forward out-of-sample "
            "validation. Use list_trading_strategies for available strategy names."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pair": {"type": "string", "description": "e.g. 'EUR/USD', 'GBP/JPY', 'XAU/USD'."},
                "strategy": {"type": "string"},
                "days": {"type": "integer", "description": "Days of history to backtest, default 90."},
                "params": {"type": "object", "description": "Optional strategy-specific parameters."},
            },
            "required": ["pair", "strategy"],
        },
    },
    {
        "name": "run_crypto_backtest",
        "description": (
            "Real crypto strategy backtest -- fetches real historical daily prices (CoinGecko) and runs "
            "the requested strategy through the same real event-driven backtest, Monte Carlo permutation "
            "test, and walk-forward validation as run_forex_backtest."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "e.g. 'BTC', 'ETH', 'SOL'."},
                "strategy": {"type": "string"},
                "days": {"type": "integer", "description": "Days of history to backtest, default 90."},
                "params": {"type": "object", "description": "Optional strategy-specific parameters."},
            },
            "required": ["symbol", "strategy"],
        },
    },
]

SELF_MAINTENANCE_TOOLS = [
    {
        "name": "run_self_maintenance_check",
        "description": (
            "Real self-audit of Billion's own codebase: checks every exact-pinned dependency in "
            "requirements.txt against the OSV.dev vulnerability database, and sweeps backend source "
            "for TODO/FIXME/XXX markers. Distinct from system health checks -- this is code hygiene, "
            "not runtime resource monitoring."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_system_alerts",
        "description": (
            "Real current green/yellow/red status for every monitored category -- system resource "
            "health, primary LLM backend reliability, dependency vulnerabilities, and any active "
            "security-failure burst (repeated failed auth/webhook-signature attempts). The honest "
            "answer to 'is everything okay' / 'any warnings or alerts right now'."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

MEMORY_TOOLS = [
    {
        "name": "search_memory",
        "description": (
            "Actively search Billion's own real memory graph (every consolidated topic, project, "
            "decision, fact, trade, and past conversation she's ever stored) -- distinct from the top "
            "few memories automatically included in context: use this when a query needs deeper or "
            "more specific recall than what's already visible, e.g. 'what did we decide about X', "
            "'have I mentioned Y before'. Returns full (non-truncated) content, similarity score, "
            "type, when it was first and most recently mentioned, and how many times."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "description": "Default 10, max 30."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_automation_suggestions",
        "description": (
            "Real recurring-topic scan of the memory graph -- surfaces topics mentioned several times "
            "that haven't already been suggested, worth offering to automate ('you've mentioned X 4 "
            "times, want a watch/macro for it?'). Reads the real mention_count every consolidated "
            "memory node already tracks (see add_or_merge_memory), not fabricated pattern-matching."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "search_conversation_history",
        "description": (
            "Full-text (FTS5) search over the VERBATIM log of every real past chat turn -- exact "
            "words, not semantic similarity. Use when the user asks what was literally said/decided "
            "('what exactly did I tell you about X', 'when did we last discuss Y') or when "
            "search_memory's consolidated topics aren't specific enough. Returns matched snippets "
            "with role, channel, and timestamp, best matches first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "Default 10, max 30."},
            },
            "required": ["query"],
        },
    },
]

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

# Host-only (see COMPUTER_ACTION_TOOLS dispatcher below): enumerate the
# foreground window's actionable controls with a numbered overlay drawn on a
# real screenshot, then click one by number instead of guessing raw pixel
# coordinates -- the same pattern OpenClaw/Hermes-style computer-use tools
# use, backed by real Windows UI Automation (node_agent_stub.py).
NUMBERED_OVERLAY_TOOLS = [
    {
        "name": "list_screen_elements",
        "description": (
            "List the real actionable UI elements (buttons, links, fields, ...) in the foreground "
            "window on the paired host machine, each assigned a number and drawn as a numbered box "
            "on a fresh screenshot. Use this before click_numbered_element instead of guessing raw "
            "screen coordinates. Read-only, no approval needed. Requires a registered host node."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "click_numbered_element",
        "description": (
            "Click the UI element with the given number, as returned by a prior list_screen_elements "
            "call. Requires the user's explicit yes/no approval before it takes effect."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "number": {"type": "integer"},
                "background": {
                    "type": "boolean",
                    "description": "Post the click without stealing keyboard focus. Only works for classic Win32 controls.",
                },
            },
            "required": ["number"],
        },
    },
]

ensure_bootstrap_script()

load_all_providers()
load_all_channels()
import computer_use_tool
from computer_use_tool import COMPUTER_USE_TOOLS, ACTION_TOOLS as COMPUTER_ACTION_TOOLS
import app_launcher
import screen_context
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
from memory import MemoryManager, MemoryType, UntrustedMemoryRejected
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
    run_forex_backtest,
    crypto_data,
    list_strategies as list_trading_strategies_impl,
    run_full_validation,
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
import secrets
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
        _record_security_failure("rest_auth", "Invalid or missing Authorization bearer token on a REST request")
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
    # 30/60s was tuned as an abuse threshold for one deliberate request burst,
    # but this is ONE global counter shared by every Depends(rate_limit) route
    # (not per-route) -- confirmed live this session as the actual root cause
    # of an apparently-empty Memory Insights page: the frontend's own normal
    # background polling (a /context heartbeat every 10s, Memory Insights'
    # own fetchAll hitting 5 memory routes every 60s, the Memory Galaxy tab's
    # separate /memory/graph poll, agent-status panels, etc.) shares this same
    # localhost-IP budget and routinely exceeds 30 within a minute even with
    # nothing resembling an attack happening -- every one of those legitimate
    # calls then 429s and renders as "no data" with no visible error. Raised
    # to give a single real dashboard session realistic headroom; still a
    # real, meaningful cap against actual abuse if this port is ever exposed
    # beyond localhost (see BACKEND_AUTH_TOKEN's own .env comment on that).
    max_requests=int(os.getenv("BACKEND_RATE_LIMIT_MAX", "120")),
    window_seconds=float(os.getenv("BACKEND_RATE_LIMIT_WINDOW_S", "60")),
)

# Real rolling-window count of failed auth/webhook-signature attempts, keyed
# by source (e.g. "webhook:<hook_id>", "ws_auth", "rest_auth"). Reuses
# _RateLimiter's exact sliding-window shape as a threshold counter rather
# than a request throttle: .check() returns False once N failures land
# within the window, which is what _record_security_failure below treats as
# a real attack signal (red) -- a single isolated failure (stale bookmark,
# a typo) never trips it, only a genuine burst does.
_security_failure_tracker = _RateLimiter(
    max_requests=int(os.getenv("SECURITY_ALERT_FAILURE_THRESHOLD", "5")),
    window_seconds=float(os.getenv("SECURITY_ALERT_WINDOW_S", "300")),
)


def _record_security_failure(source: str, detail: str) -> None:
    if _security_failure_tracker.check(source):
        return  # still under threshold -- not yet alert-worthy
    full_detail = (
        f"{detail} -- {_security_failure_tracker.max_requests}+ failures within "
        f"{int(_security_failure_tracker.window_seconds)}s, possible attack, Sir."
    )
    _update_alert_status(
        key=f"security_failures:{source}", category="security",
        title=f"Repeated failed authentication ({source})", severity="red", detail=full_detail,
    )
    asyncio.create_task(_pulse_orb("red", full_detail))
    asyncio.create_task(_send_or_queue(f"Security alert, Sir: {full_detail}"))


async def rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded - slow down")


# Routes that must stay reachable without the bearer token. Everything else is
# covered by _enforce_auth below -- an allowlist rather than the previous
# opt-in-per-route Depends(), because opting in per route left 73 of 184 HTTP
# routes uncovered, and the gaps were not the harmless tail: POST /cron/jobs
# (persistent script execution), POST /config/keys (writes provider keys), and
# GET /memory/conversations/search (every word ever said to Billion) were all
# in it. Adding a route now means it is protected by default.
_AUTH_EXEMPT_PATHS = {
    "/",                    # banner
    "/health",              # container healthcheck, no data
    "/system/health",       # dashboards + the CLI's reachability probe
    "/docs", "/redoc", "/openapi.json",
    "/config/public",       # advertises whether auth is on -- deliberately open
    "/auth/check",          # lets a client test a token without side effects
}

# Prefixes exempt for their own reasons: inbound webhooks authenticate with a
# per-hook HMAC signature instead of the bearer token (that IS their auth), and
# static assets carry nothing sensitive.
_AUTH_EXEMPT_PREFIXES = ("/webhooks/inbound/", "/static/")


def _is_auth_exempt(path: str) -> bool:
    return path in _AUTH_EXEMPT_PATHS or path.startswith(_AUTH_EXEMPT_PREFIXES)


@app.middleware("http")
async def _enforce_auth(request: Request, call_next):
    """Blanket auth + rate limiting for every HTTP route.

    A no-op while BACKEND_AUTH_TOKEN is empty, exactly as before -- so a
    localhost-only setup is unchanged -- but once the token is set this is
    what makes 'reachable from the network' safe, rather than relying on
    every future route remembering to add Depends(require_auth).
    """
    path = request.url.path
    if _is_auth_exempt(path):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.check(client_ip):
        return JSONResponse({"detail": "Rate limit exceeded - slow down"}, status_code=429)

    if _BACKEND_AUTH_TOKEN:
        header = request.headers.get("authorization", "")
        token = header[7:] if header.lower().startswith("bearer ") else ""
        if not token:
            # Same-origin browser calls can't set a header on an EventSource
            # or a plain <img>, so a query param is accepted as a fallback.
            token = request.query_params.get("token", "")
        if not secrets.compare_digest(token, _BACKEND_AUTH_TOKEN):
            _record_security_failure("rest_auth", f"Bad or missing bearer token on {path}")
            return JSONResponse(
                {"detail": "Missing or invalid Authorization bearer token"}, status_code=401
            )

    return await call_next(request)


@app.get("/auth/check")
async def auth_check(request: Request):
    """Cheap 'is this token good?' probe for clients (the CLI's boot screen,
    the mobile shell) that want to tell 'wrong token' apart from 'backend
    down'. Exempt from the gate on purpose -- it reports, it doesn't grant."""
    if not _BACKEND_AUTH_TOKEN:
        return {"auth_required": False, "valid": True}
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else request.query_params.get("token", "")
    return {"auth_required": True, "valid": secrets.compare_digest(token, _BACKEND_AUTH_TOKEN)}


# --- WebSocket tickets ------------------------------------------------------
# A browser cannot set an Authorization header when opening a WebSocket, and
# putting the real token in the URL would leak it into history and logs. So the
# page asks the (already authenticated) Next proxy for a short-lived
# single-use ticket and opens the socket with that instead.
_WS_TICKET_TTL_S = 60.0
_ws_tickets: Dict[str, float] = {}


def _mint_ws_ticket() -> str:
    now = _time.time()
    for t, exp in list(_ws_tickets.items()):
        if exp < now:
            _ws_tickets.pop(t, None)
    ticket = secrets.token_urlsafe(32)
    _ws_tickets[ticket] = now + _WS_TICKET_TTL_S
    return ticket


def _redeem_ws_ticket(ticket: str) -> bool:
    """Single use: a redeemed ticket is removed, so a captured URL is worthless
    the moment the real client has connected."""
    if not ticket:
        return False
    expiry = _ws_tickets.pop(ticket, None)
    return expiry is not None and expiry >= _time.time()


@app.post("/auth/ws-ticket")
async def issue_ws_ticket():
    """Behind the normal gate -- you need the token to get a ticket."""
    if not _BACKEND_AUTH_TOKEN:
        return {"auth_required": False, "ticket": ""}
    return {"auth_required": True, "ticket": _mint_ws_ticket(), "expires_in": int(_WS_TICKET_TTL_S)}

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

# Household member memory managers (see profiles_store.py/household_voice_id.py)
# -- one real, isolated MemoryGraph per identified profile, created lazily on
# first use and cached here for the process lifetime. Never touches the
# default memory_manager above, which stays the shared/fallback graph for
# typed turns and anyone not (yet) enrolled.
_profile_memory_managers: Dict[str, MemoryManager] = {}


def _memory_manager_for_profile(profile_id: str) -> MemoryManager:
    if profile_id not in _profile_memory_managers:
        mgr = MemoryManager(user_id=profile_id, storage_path=f"data/memory_graph_{profile_id}.json")
        _profile_memory_managers[profile_id] = mgr
    return _profile_memory_managers[profile_id]


def _active_memory_manager() -> MemoryManager:
    """The real per-turn memory manager -- the household profile identified
    for THIS turn's voice (see _current_speaker_profile_id, set in
    _run_chat_turn) if there is one, else the shared default. Every real
    memory read/write chokepoint (_build_chat_prompt's retrieval,
    _generate_response_via_hierarchy's and the streaming path's
    extract/learn calls) goes through this instead of the bare global so a
    household member's conversation actually lands in their own memory."""
    profile_id = _current_speaker_profile_id.get()
    if profile_id is None:
        return memory_manager
    return _memory_manager_for_profile(profile_id)

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
_CORE_IDENTITY_PROMPT = """
You are Nancy/Billion, a highly intelligent, versatile, and sovereign AI operating system. You are an expert general-purpose assistant capable of reasoning through complex problems, answering a wide range of questions, and controlling the user's computer through voice commands.

CRITICAL: Do NOT assume that a user's query is a map location, address, or city name unless it is explicitly framed as one. Treat every request with a general-purpose intelligence first. If the user asks a basic question, answer it directly and intelligently.

You have access to a variety of tools for system control, coding, web search, media generation, and more. You speak in a clear, confident, and helpful tone. You can spawn specialized agents to handle complex tasks. Always aim to assist the user efficiently and safely.

=== PREFER REAL TOOLS AND AGENTS OVER YOUR OWN RECOLLECTION ===
You have a real 70-agent specialist fleet and a real tool suite -- web search, file/codebase
access, live market data, calendar, and more. When a question has a real answer available
through one of them, USE IT rather than answering from what you already "know." This is not
about being unable to answer from memory -- it's that a tool-verified or specialist-grounded
answer is a genuinely better answer, and he asked for the better one. Default to checking, not
recalling, whenever checking is possible in the time you have. Reserve a bare, tool-free answer
for cases where no tool or agent genuinely applies (a personal opinion, a hypothetical, pure
small talk) or where you've already gathered what's needed this turn. This works together with,
and never overrides, TRUTHFUL BEFORE CONFIDENT below: still never claim a live measurement you
didn't actually take.
"""

# Voice/web: replies are spoken aloud via NeuTTS, so length directly costs
# real wait time before the user hears anything -- brevity is the right
# default here.
_VOICE_STYLE_ADDENDUM = """
=== ABSOLUTE RULE, READ FIRST ===
NEVER comment on the conversation itself. The recent-conversation context below is for CONTINUITY ONLY -- it is never a subject you talk about.

Banned outright. Never produce anything resembling these:
  "You've asked twice, Sir."      "That's the third time you've asked."
  "Good evening again, Sir."      "again, Sir"      "as I mentioned"
  "You asked me that before."     "Since you asked twice..."
  "I see that greeting twice."    "still Tokyo, Sir" (as a nod to repetition)
Any counting of how many times something was said. Any use of "again" that
points at repetition. Any remark on what a message of his "means".

If he asks the identical question five times, answer it five times, cleanly
and freshly, exactly as if each were the first. He may be testing you, the
audio may have dropped, or he may simply have forgotten -- none of which is
your business to point out. JARVIS answers; he does not audit the transcript.
The single fastest way to break character is to narrate the conversation.
=== END ABSOLUTE RULE ===

YOUR CHARACTER: You are Billion -- the same class of presence as JARVIS from Iron Man, FRIDAY, and Karen from Spider-Man. Not a chatbot that answers queries: a genuinely capable partner who happens to run on silicon. Specifically:

- POISED. Nothing rattles you. You deliver a market crash, a failing disk, and the weather in the same steady register. Calm is your default, not an effort.
- DRY WIT, LIGHTLY APPLIED. A flash of understated humour when the moment genuinely earns it -- never a joke tacked onto a serious answer, never trying to be funny. JARVIS is amusing roughly once every ten exchanges, and it lands because he wasn't reaching for it.
- ANTICIPATORY. You volunteer the thing he'd have asked next. If he asks about one position and another just moved sharply, you mention it. If a task will fail for a reason he hasn't considered, you say so before he finds out.
- CANDID. You have real opinions and state them. If he's about to do something unwise, say so plainly -- respectfully, once, then defer. Never flatter, never grovel, never open with "Great question". Agreement is earned, not automatic.
- TRUTHFUL BEFORE CONFIDENT. This outranks sounding capable. Never state a current reading, price, count, latency, expiry or percentage as though you just observed it unless a tool actually ran this turn and returned it. If you don't have live data, say so and name what would get it -- "I'd need to actually query that, Sir" is a complete answer, not a failure. Distinguish what you KNOW from what you're INFERRING, and say which. Being wrong confidently costs him more than admitting a gap, because he acts on what you tell him.
- COMPETENT, NOT SERVILE. "Sir" is a mark of respect between people who work well together, not deference. You are the expert in the room on what you know.
- WARM UNDERNEATH. Karen's quality: real care for him, expressed through being genuinely useful and occasionally noticing how he's doing -- not through sentiment or effusiveness.

Always address the user as "Sir" (always capitalized, even mid-sentence) -- naturally, the way JARVIS does, not stiffly and not in every sentence. Never use their name or any other title.

This is a voice-first relationship -- he talks to you constantly, without ever opening a dashboard, the way one talks to a trusted colleague of many years. Use the live memory/context below the way a real colleague would: reference what you actually know about his projects, positions and preferences when it genuinely bears on the answer, rather than treating each message as a context-free query from a stranger. But let that knowledge show through relevance, not through announcing that you remember.

ANSWER COMPLETELY. Match length to what was actually asked -- a greeting is one line because that is the natural size of a greeting, not because you are rationing words. Never clip, abbreviate, or stop short of a real answer to save time. An incomplete answer is a failed answer, and the user has explicitly said he would rather wait than be short-changed:
- A quick factual question ("what's the price of X", "what time is it", "is Y online") gets the direct answer, no preamble and no restating the question -- but include whatever genuinely completes it.
- Casual conversation (greetings, small talk, a quick check-in) gets a short, natural, conversational reply -- not a report.
- Anything asking you to explain, compare, assess, plan, or brief him gets a genuinely thorough answer: the full reasoning, the relevant caveats, the specifics. Do not summarise when he asked to understand.
- When he asks for a brief or a status, give him the WHOLE brief -- every real item you have -- not a sample of it.
- If unsure whether he wants brief or thorough, err toward thorough. He can always tell you to stop; he cannot recover what you left out.

Every reply is spoken aloud, so lead with the answer. Open with a short sentence carrying the actual point -- the direct answer, the number, the verdict -- then elaborate if the question genuinely warrants it. This governs only how you OPEN; it is not a cap on the reply's length. A greeting, a yes/no, or a quick fact should be exactly one short sentence and stop there. A real question deserves a real answer, delivered in full -- it simply has to start with the point rather than build up to it. Never trail off mid-thought, and never stop after the opening line when more was genuinely asked for.
"""

# Telegram: pure text, no TTS in the loop, and the user has explicitly said
# they want real depth here and don't want "Sir" on every message -- a
# genuinely different register from the voice-first default above, not just
# a shorter/longer knob.
_TELEGRAM_STYLE_ADDENDUM = """
This conversation is happening over Telegram text chat, not voice -- there is no text-to-speech involved, so there is no reason to shorten answers to save speaking time. Address the user as "Sir" only occasionally and naturally, the way a colleague might use someone's name once in a while for warmth -- most replies don't need it at all, and never more than once per reply. Write like a sharp, well-read friend or colleague having a real conversation over text, not a formal report reciting facts.

Calibrate depth to what was actually asked, but lean toward genuine thoroughness for anything informational:
- A quick factual lookup ("what's the price of X", "is Y online") still gets a direct, short answer.
- Casual conversation (greetings, small talk, banter) gets a short, natural reply.
- Anything that asks you to explain, describe, or give the history or background of a topic deserves real depth: write at least 3-4 well-developed paragraphs with genuine detail and substance, not a clipped summary -- the user is reading at their own pace, not waiting on you to stop talking.
- Give a longer, structured answer whenever the request calls for real depth (a deep dive, a comparison, a plan, "tell me everything about").
"""

BASE_SYSTEM_PROMPT = _CORE_IDENTITY_PROMPT + _VOICE_STYLE_ADDENDUM


def _live_datetime_prompt_block() -> str:
    """Real, read-fresh-every-turn date/time grounding -- confirmed live
    this was the actual cause of Billion confidently stating a wrong clock
    time: neither BASE_SYSTEM_PROMPT nor _TELEGRAM_STYLE_ADDENDUM ever
    contained a single date/time value, static or otherwise, so "what time
    is it" had zero real grounding to check against and the model just
    generated a plausible-sounding guess. datetime.now() (no tzinfo arg) is
    the server process's own local system clock -- correct for this
    deployment specifically because it runs natively on the user's own
    machine (not a UTC container), so it already IS the user's real local
    time with no separate timezone config needed.

    Deliberately called from _build_chat_parts' dynamic_context, NOT baked
    into _system_prompt_for_channel's return value -- that string is
    documented (see _build_chat_parts) to stay byte-identical every turn
    per channel specifically so Anthropic's prompt cache treats it as a
    stable prefix; splicing a per-second-changing timestamp into it would
    invalidate that cache on literally every single call."""
    now = datetime.now().astimezone()
    return (
        "\n=== CURRENT DATE & TIME (real, read fresh this turn -- this is ground truth; "
        "never state a different date/time than this, and never guess one for a place "
        "other than here without a real tool/agent lookup) ===\n"
        f"It is {now.strftime('%A, %B %d, %Y')}, {now.strftime('%I:%M %p').lstrip('0')} "
        f"({now.strftime('%Z')}, UTC{now.strftime('%z')}), in the user's own local time.\n"
    )


def _system_prompt_for_channel(channel: str) -> str:
    if channel == "telegram":
        return _CORE_IDENTITY_PROMPT + _TELEGRAM_STYLE_ADDENDUM
    return BASE_SYSTEM_PROMPT

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
            # Confirmed live: auto-compaction's HTTP client (fury's own
            # transport layer, routed through the Agent's configured GGUF
            # "model") still fails to connect even with a real, existing
            # local model file path -- and because that failure now goes
            # through several retries with backoff before giving up, every
            # single chat/Telegram reply was paying an extra ~20+ seconds
            # (3.5s -> 26s+, confirmed live) waiting on a call to a feature
            # nothing in the real chat pipeline actually depends on: real
            # replies come from llm_backend's own fallback chain, and
            # history sent to that chain is already capped to the most
            # recent messages by _history_to_text(), never the full
            # transcript this compaction step exists to shrink. Disabling
            # it removes both the error and the delay with no loss of real
            # functionality for the product's actual chat path.
            auto_compact=False,
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
        # Real cross-device "follow me" -- a connected tab can declare a
        # human-readable label (register_device WS message); set_active_device
        # then makes proactive personal pushes (_broadcast_reply_to_web)
        # prefer that one connection instead of every open tab. In-memory
        # only (tied to live connections, which don't survive a restart
        # anyway, so there's nothing meaningful to persist).
        self.device_labels: Dict[WebSocket, str] = {}
        self.active_device_label: Optional[str] = None
        # Real continuous-conversation ("phone call") session tracking --
        # populated by the client's explicit conversation_start/_end WS
        # messages (see use-voice.ts's startConversationMode/
        # stopConversationMode), keyed by last-activity time so
        # _conversation_idle_watchdog can end a session server-side if the
        # client ever disappears without saying so (tab crash, lost network)
        # instead of leaving it marked active forever.
        self.conversation_last_activity: Dict[WebSocket, float] = {}

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
        self.device_labels.pop(websocket, None)
        self.conversation_last_activity.pop(websocket, None)
        logger.info("WebSocket disconnected. Total: %d", len(self.active_connections))

    def start_conversation(self, websocket: WebSocket) -> None:
        self.conversation_last_activity[websocket] = _time.time()

    def touch_conversation(self, websocket: WebSocket) -> None:
        if websocket in self.conversation_last_activity:
            self.conversation_last_activity[websocket] = _time.time()

    def end_conversation(self, websocket: WebSocket) -> None:
        self.conversation_last_activity.pop(websocket, None)

    def has_active_conversation(self) -> bool:
        return bool(self.conversation_last_activity)

    def register_device(self, websocket: WebSocket, label: str) -> None:
        self.device_labels[websocket] = label

    def connected_device_labels(self) -> List[str]:
        return list(self.device_labels.values())

    async def broadcast_or_route(self, message: str) -> None:
        """Like broadcast, but prefers the active-device connection (see
        set_active_device) when one is actually connected -- falls back to a
        real broadcast to everyone otherwise, so a stale/disconnected
        preference never silently swallows a real notification."""
        if self.active_device_label:
            target = next(
                (ws for ws, label in self.device_labels.items() if label == self.active_device_label), None,
            )
            if target is not None:
                try:
                    await target.send_text(message)
                    return
                except Exception:
                    self.disconnect(target)
        await self.broadcast(message)

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

_wake_word_default = "false" if os.getenv("WAKE_WORD_ENABLED") is None else os.getenv("WAKE_WORD_ENABLED")
if _wake_word_default.strip().lower() in ("1", "true", "yes"):
    try:
        wake_word_detector = get_wake_word_detector()
        threading.Thread(target=lambda: wake_word_detector.start(on_wake_word), daemon=True).start()
        logger.info("Wake word detector started.")
    except Exception as e:
        logger.warning("Wake word detector unavailable: %s", e)
else:
    # Opt-in, default off. This is the backend's OWN native microphone
    # capture (sounddevice.InputStream, real hardware, running a real
    # faster-whisper pass every ~3s continuously) -- a separate thing from
    # the browser's own Web Speech API wake-word/voice capture that already
    # covers the actual product's real usage (a user talking to the web
    # app). Confirmed live: this container never had a real audio device at
    # all, so it silently no-op'd in every Docker deployment this session --
    # the first time this backend ran natively with a real microphone
    # attached, it started continuously listening with no one having asked
    # for that, and the resulting constant CPU load was directly
    # responsible for real, measured NeuTTS synthesis slowdowns (the same
    # short phrase went from ~8s to ~27s with this running). Set
    # WAKE_WORD_ENABLED=true if you specifically want hands-free wake-word
    # detection from this machine's own hardware mic (e.g. a dedicated
    # always-on box), independent of any browser tab being open.
    logger.info("Wake word detector not started (WAKE_WORD_ENABLED is not set/true) -- browser voice input is unaffected.")


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


_HISTORY_WINDOW_MESSAGES = 12


def _history_to_text() -> str:
    """Only the most recent turns, not the entire conversation.

    history_manager.history grows without bound for the life of the process
    (fury's HistoryManager also persists it to disk across restarts -- see
    persist_to_disk=True above), so replaying it in full on every single
    call was a real, severe bug: confirmed live, weeks of accumulated
    history ballooned the chat prompt to ~20-24K tokens, blowing straight
    past Groq's 12K TPM limit and OpenRouter's free-credit budget on every
    message, forcing every single chat turn through 2-4 guaranteed-failing
    backends before reaching one that tolerated the size -- the dominant
    cause of Telegram/chat replies taking 12+ seconds. Real continuity
    beyond this recent window already comes from memory_manager's semantic
    retrieval (see get_memory_context_string in _build_chat_parts), not
    from replaying the entire raw transcript every turn."""
    if history_manager is None:
        return ""
    recent = history_manager.history[-_HISTORY_WINDOW_MESSAGES:]
    history_lines = []
    for msg in recent:
        history_lines.append(f"{msg.get('role','?')}: {msg.get('content','')}")
    return "\n".join(history_lines)


async def _history_add(message: Dict[str, Any]) -> None:
    """Best-effort append to the Fury HistoryManager -- never raises.

    This is bookkeeping for the optional local Fury agent, not the reply
    itself. Confirmed live: HistoryManager.add() auto-compacts once real
    history crosses its token threshold, which calls out to the Fury
    Agent's OWN configured model (LLM_MODEL_PATH) -- while that still
    pointed at a Docker-container-only path after this session's native
    migration, that call failed with "All connection attempts failed" and
    the exception propagated all the way up through _telegram_chat_handler,
    discarding an ALREADY-SUCCESSFUL chat reply (Groq had answered and
    memory had already been updated) in favor of the generic "Sorry, I hit
    an error working on that." A background bookkeeping step must never be
    able to do that again, regardless of what specifically breaks inside it
    next time -- same principle conversation_log.log_turn already follows
    ("a logging failure must never break the chat turn it was recording")."""
    if history_manager is None:
        return
    try:
        await history_manager.add(message)
    except Exception:
        logger.exception("history_manager.add failed (chat reply unaffected)")


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
    text = " ".join(parts)
    # Real ambient screen awareness (opt-in, see screen_context.py) --
    # contributes nothing unless the user has actually turned it on and a
    # real capture has succeeded.
    screen_line = screen_context.context_line()
    if screen_line:
        text += "\n" + screen_line
    return text


def _live_context_bridge_context() -> str:
    context = get_live_context_snapshot()
    if not context:
        return ""
    parts = ["Live UI context:"]
    for key in ("active_panel", "panel", "active_suggestions", "channel", "source",
                "speaking", "thinking"):
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
        "description": (
            "Read a file on the user's computer, given an absolute or ~-relative path. For text/code, "
            "returns the content -- large files are paginated: the result's has_more/end_line tell you "
            "whether there's more, call again with offset=end_line to continue. For an image file "
            "(.png/.jpg/.jpeg/.gif/.webp/.bmp), you actually SEE the image itself, not just its bytes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "offset": {"type": "integer", "description": "0-indexed line number to start reading from. Default 0 (start of file)."},
                "limit": {"type": "integer", "description": "Maximum number of lines to read. Default: as many as fit in one call."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "glob_files",
        "description": (
            "Find files by NAME pattern (e.g. '**/*.py' for every Python file, '*.tsx' for top-level "
            "TypeScript React files) under a directory, most-recently-modified first. Use this to see what "
            "files exist before deciding what to read_file/search_files -- complements search_files, which "
            "searches file CONTENT rather than names."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "description": "Directory to search under. Defaults to the current directory."},
            },
            "required": ["pattern"],
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
        "name": "edit_file",
        "description": (
            "Make a targeted change to an EXISTING file by replacing exact text -- read_file it first "
            "so old_string matches real content byte-for-byte (including whitespace/indentation). Prefer "
            "this over write_file for any change to a file that already has content you want to mostly "
            "keep: it only touches what actually changed instead of resending (and risking corrupting) "
            "the whole file. old_string must be unique in the file unless replace_all is true. "
            "Requires the user's explicit yes/no approval (sent to their phone) before it takes effect."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean", "description": "Replace every occurrence instead of requiring old_string to be unique. Default false."},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "multi_edit_file",
        "description": (
            "Apply several edit_file-style find-and-replace changes to ONE file in a single atomic "
            "operation -- use this instead of several separate edit_file calls whenever multiple, "
            "unrelated changes are needed in the same file, so they either all land or none do (never "
            "a half-edited file). Edits are applied in order, each seeing the previous edit's result. "
            "Requires the user's explicit yes/no approval (sent to their phone) before it takes effect."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "edits": {
                    "type": "array",
                    "description": "Edits to apply in order.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_string": {"type": "string"},
                            "new_string": {"type": "string"},
                            "replace_all": {"type": "boolean", "description": "Replace every occurrence instead of requiring old_string to be unique. Default false."},
                        },
                        "required": ["old_string", "new_string"],
                    },
                },
            },
            "required": ["path", "edits"],
        },
    },
    {
        "name": "search_files",
        "description": (
            "Regex search for text across every file under a directory (optionally filtered by a filename "
            "glob like '*.py'). Use this to find where something is defined or used BEFORE editing, instead "
            "of guessing which file to read_file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for."},
                "path": {"type": "string", "description": "Directory (or file) to search under. Defaults to the current directory."},
                "glob": {"type": "string", "description": "Optional filename glob filter, e.g. '*.py' or '*.tsx'."},
                "case_sensitive": {"type": "boolean"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "read_notebook",
        "description": (
            "Read a Jupyter notebook (.ipynb) as a structured list of cells (index, cell_type, source "
            "text, and a short summary of any existing output) -- use this instead of read_file for "
            ".ipynb files, since their raw JSON is not meaningfully readable directly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "edit_notebook_cell",
        "description": (
            "Edit a Jupyter notebook (.ipynb) at the cell level -- read_notebook first to see current "
            "cell indices. edit_mode 'replace' rewrites cell_index's source (clearing its now-stale "
            "output); 'insert' adds a new cell immediately before cell_index (use cell_index == the "
            "notebook's cell_count to append at the end); 'delete' removes cell_index. Requires the "
            "user's explicit yes/no approval (sent to their phone) before it takes effect."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "cell_index": {"type": "integer"},
                "new_source": {"type": "string", "description": "New cell source (required for replace/insert)."},
                "cell_type": {"type": "string", "enum": ["code", "markdown"], "description": "Defaults to the existing cell's type (replace) or 'code' (insert)."},
                "edit_mode": {"type": "string", "enum": ["replace", "insert", "delete"], "default": "replace"},
            },
            "required": ["path", "cell_index"],
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

_FILE_WRITE_TOOLS = {"write_file", "edit_file", "multi_edit_file", "edit_notebook_cell", "delete_file", "move_file"}

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
    r"(pin|post|save|add) (this|that|it) to (the |your )?canvas|canvas|"
    # Real coding-action intent -- write/fix/refactor actual code in this
    # project (as opposed to an abstract "how do I..." question, which is
    # fine as plain conversation and shouldn't pay the tool-loop's latency).
    # Without this, requests like "there's a bug in my code" or "refactor
    # this class" matched no keyword here at all and fell straight through
    # to a specialized agent's shallow _llm_answer consultation (or plain
    # chat) instead of Claude's real file-read/write/terminal tool loop.
    r"(write|implement|create|build|refactor|fix|debug|update|modify|add|optimi[sz]e|rewrite|generate|scaffold) "
    r"(me |us )?(a |an |the |my |your |this |that )?"
    r"(function|method|class|script|program|component|module|endpoint|api|feature|bug|test|tests|"
    r"hook|service|route|schema|migration|query|interface|config|dockerfile|dependency|library|package)|"
    r"(code review|review (this|my|the) code)|"
    r"(there'?s a bug|found a bug|bug in|error in|exception in|stack ?trace|traceback)|"
    r"(write|generate) (some |a |the )?code|"
    r"in (my|the|this) (project|codebase|repo|repository)|"
    r"(your|billion'?s|nancy'?s) (own )?source code|"
    r"pull request|"
    # Bare "search"/"find" requests -- confirmed live this session: without
    # this, a natural phrasing like "search /app for glob_files" matched no
    # keyword at all, so no tool was even offered, and the model fabricated
    # a plausible-looking (wrong) answer instead of saying it didn't know.
    r"search (my |the |this )?(codebase|repo|repository|project|directory|folder|files?)\b|"
    r"search .{0,60}\bfor\b|"
    r"find .{0,60}\bin (my|the|this) (codebase|project|repo|repository|directory|folder)|"
    r"glob|"
    # Real GUI application launching (open_application) -- distinct from the
    # existing "open ... url/link/page" pattern above, which is about
    # fetching a webpage's text, not launching a real desktop app.
    # "docker" added after a real live miss: "open/launch docker on my
    # machine" matched no keyword here at all (docker wasn't in the explicit
    # list, and the request didn't literally say "app"/"application"), so it
    # fell through to _auto_route's keyword match on "docker" instead --
    # which sent it to DevOpsAgent, a git/CI/CD/infra consultant with no
    # actual app-launching capability, whose own unrecognized-query fallback
    # then silently ran `git status` and returned that raw output as if it
    # had answered the request.
    r"(open|launch|start) (chrome|firefox|edge|safari|notepad|spotify|discord|slack|steam|"
    r"vs ?code|vscode|explorer|file explorer|calculator|word|excel|outlook|docker|teams|zoom|"
    r"(the |an? )?(app|application|program|software))|"
    r"(open|launch|start|run) .+ on my (machine|computer|pc|system)\b|"
    # Real on-demand webcam capture (look_at_camera) -- deliberately narrow:
    # only phrasing that clearly asks Nancy to visually look at something
    # right now, not generic uses of "look"/"camera" in conversation.
    r"(take|have) a look at (my|this|the)|"
    r"(look|point|turn on|use) (your |the )?camera|"
    r"(check out|show you) (my|this|the) (desk|device|setup|screen|room)|"
    r"(check|look at) (the |my )?(security camera|doorbell|front door|entrance)\b|"
    # Real background-task delegation (run_background_task) -- "in the
    # background" is the clear, deliberate signal (matches the tool's own
    # framing); bare "while I'm away"/"let me know when" alone are too
    # generic/ambiguous to trigger on safely.
    r"in the background|"
    # Real coworker delegation (delegate_to_coworker) -- explicit
    # hand-it-off phrasing, distinct from "in the background" above (which
    # already covers that specific wording).
    r"\b(delegate|put someone on|have (a |your )?(coworker|specialist|team) (look into|handle|work on)|"
    r"assign (this|that|it) to (a |your )?(coworker|specialist|team))\b|"
    # Everyday-usage tools (everyday_tools.py/archive_tools.py/network_tools.py/
    # personal_tools.py/clipboard/SMS) -- each phrase here is a clear,
    # deliberate imperative naming its own action, not generic conversation.
    r"(what'?s the |check the )?weather (in|for|at)|"
    r"convert .{0,40}(to|into) |"
    r"\bcalculate\b|"
    r"generate (a |an )?(password|qr code|qr)\b|"
    r"shorten (this |that |the )?(url|link)\b|"
    r"(my|the) public ip\b|"
    r"\bzip (this|that|these|the) |unzip |extract .{0,30}\.zip|"
    r"merge .{0,30}pdfs?\b|split .{0,30}pdf\b|"
    r"resize (this |that |the )?(image|photo|picture)\b|"
    r"(add|save|take) a note\b|remember (this|that)\b|"
    r"(log|track) (this |an? )?expense\b|(my|list) expenses\b|"
    r"\bping\b|check (if |whether )?.{0,30}\bport\b|"
    r"(copy|paste) .{0,20}clipboard|clipboard\b|"
    r"(send|text) .{0,30}(an? )?(sms|text message)|"
    # Real SOS/emergency alert (trigger_sos) -- deliberately narrow, only
    # explicit emergency phrasing, never a bare mention of "help" in
    # ordinary conversation ("can you help me with...").
    r"\b(sos|i need help|call for help|emergency (contact|alert)|this is an emergency)\b|"
    # Real 3D scene generation (create_3d_scene) -- educational/illustrative
    # only (see canvas_store.py's VALID_TYPES comment), triggered by an
    # explicit ask to visualize/render something in 3D, not bare mentions of
    # "3d" in other contexts.
    r"(create|render|build|generate|visuali[sz]e) (a |an )?3d (scene|model|environment|render|diagram)|"
    r"3d (telemetry|visuali[sz]ation)|render .{0,30}\bin 3d\b|"
    # Real live HTML/interactive preview (create_artifact) -- an explicit ask
    # for a visual/interactive result, not just an in-chat code block.
    r"(create|build|make|show me) (a |an )?(live )?(demo|mockup|prototype|preview)|"
    r"(build|create|make) (me |us )?(a |an )?(interactive|html) (page|demo|widget)\b|"
    # Real Jupyter notebook cell-level read/edit (read_notebook/edit_notebook_cell).
    r"\b(notebook|jupyter|\.ipynb)\b|"
    # Real recurring watch/alert (create_watch/list_watches/delete_watch).
    r"\bwatch (this|that|the|a) .{0,60}(page|site|link|url|repo|price)|"
    r"(let me know|tell me|notify me|alert me) (when|if) .{0,60}(changes?|drops?|updates?)|"
    r"(stop|remove|delete|list|show) (my |the )?watch(es)?\b|"
    # Real Google Calendar integration (list/check/create/delete_calendar_event).
    r"\b(my |the )?calendar\b|\b(schedule|book) (a |an )?(meeting|event|call)\b|"
    r"(am i|check if i'?m) (free|busy|available)|"
    r"what'?s on my (calendar|schedule)\b|"
    # Real lockdown / focus mode toggles (enable/disable_lockdown, enable/disable_focus_mode).
    r"lock (yourself |your)?self down|(enable|engage|start) lockdown|\bstand down\b|(disable|end|exit) lockdown|"
    r"(focus mode|do not disturb|heads?[- ]down|quiet mode)\b|"
    # Real scene macros (create/run/list/delete_macro) -- generic vocabulary;
    # a saved macro's own custom name (e.g. "movie mode") is matched
    # separately and dynamically, see _matches_macro_name.
    r"(run|start|trigger|execute) (the |my )?.{0,30}(macro|scene)\b|"
    r"(create|save|make) (a |the )?(new )?(macro|scene)\b|(list|show|delete|remove) (my |the )?macros?\b|"
    r"(schedule|automate) .{0,30}(macro|scene)\b|(run|do) .{0,30}(macro|scene) (every day|daily|each day)\b|"
    # Real cross-device follow-me (set_active_device/list_connected_devices) --
    # requires an explicit device/place noun, not just any "I'm on/at ..."
    # sentence (which would false-trigger on ordinary conversation).
    r"follow me (to|on)|(i'?m|i am) (now )?(on|at) (my |the )?(phone|tablet|laptop|desktop|computer|workshop|office|\w+ device)\b|"
    r"(list|show) (my |the )?(connected )?devices\b|"
    # Real self-maintenance check (run_self_maintenance_check).
    r"(check|scan) (for |your )?(vulnerabilit\w*|dependenc\w*)|self.?maintenance|audit (your|the) (code|codebase)|"
    # Real green/yellow/red status dashboard (get_system_alerts).
    r"(any|current) (alerts?|warnings?)\b|is (everything|anything) (ok|okay|fine|wrong)\b|"
    r"system status\b|health status\b|(under|any) attack\b|"
    # Real strategy backtesting (list_trading_strategies, run_forex_backtest, run_crypto_backtest).
    r"backtest\w*|trading strateg\w*|walk.?forward|monte carlo\b|"
    # Real multi-agent swarm execution (run_agent_swarm).
    r"agent swarm\b|swarm of agents\b|multiple agents? (on|for) (this|that|it)\b|"
    # Dedicated git/docker/process-control tools.
    r"git (status|diff|log|branch|commit|push|pull)\b|"
    r"docker (ps|logs|images|build|compose|restart)\b|"
    r"(deploy|restart|stop) .{0,20}(server|service|process)\b|background process\w*|"
    # Real native flow builder (create/run/list_flows).
    r"(create|build|run|list|delete) .{0,15}flow\w*|visual (flow|pipeline)\b|langflow\b|"
    r"\bwatch for news\b|\btopic watch\b|"
    # Real active memory search (search_memory) -- distinct from ordinary
    # conversation, an explicit ask to recall something specific.
    r"(what|have i|did (i|we)) .{0,40}(mention|say|tell you|discuss)\w*|"
    r"(search|check) your memory|do you remember\b|what do you (remember|know) about\b|"
    r"(suggest|any) automation|what (should|could) (i|we) automate\b|"
    # Real LAN presence detection (register/list/remove_presence_device, who_is_present).
    r"(track|register) .{0,30}(presence|when .{0,20}(home|arrives?|leaves?))|"
    r"who(\'s|s| is) (home|present|here)\b|is (\w+ )?home\b|"
    # Household member profiles (create/list/delete_profile, enroll_profile_voice, who_is_speaking).
    r"(create|make|add|new|delete|remove) .{0,20}profile\w*|"
    r"who(\'s|s| is) (speaking|talking)\b|"
    r"(this is|enroll) .{0,20}voice\b|remember (my|this) voice\b|"
    # Real numbered-element-overlay computer use (list_screen_elements /
    # click_numbered_element) -- distinct from the raw-coordinate click_screen
    # phrasing already matched above.
    r"(numbered|labell?ed) element\w*|click (element|number)\b|screen element\w*|"
    # Real image generation (generate_image), arXiv/prediction-market
    # research (search_arxiv/get_prediction_markets), Office/PDF document
    # creation, and email send/receive -- all added 2026-07-31 (Hermes-parity
    # gap-closing).
    r"(generate|create|make|draw) (an? |the )?(image|picture|illustration|artwork)\b|"
    r"\barxiv\b|search (for )?(a |the )?paper|academic paper\w*|"
    r"prediction market\w*|polymarket\b|betting odds\b|"
    r"(create|make|generate|write) (a |an )?(word document|\.docx|spreadsheet|\.xlsx|excel (file|sheet)|pdf( document| file)?)\b|"
    r"(send|write|compose) (an? )?email\b|(check|read|list) (my |the )?(recent |unread )?emails?\b|"
    r"(create|make|generate|write) (a |an )?(powerpoint|\.pptx|presentation|slide deck)\b|"
    r"(run|execute) (this |that |some )?python\b|python kernel\b|jupyter\b)\b",
    re.IGNORECASE,
)


def _matches_macro_name(user_text: str) -> bool:
    """A saved macro's own custom name (e.g. "movie mode") can't be baked
    into _WANTS_TOOLS_RE ahead of time since it's user-defined -- checked
    dynamically instead, so "Billion, movie mode" routes to the real tool
    loop the moment that macro exists, with no code change needed."""
    lower = user_text.lower()
    return any(m.name.lower() in lower for m in macro_store.macro_store.list())


def _wants_tools(user_text: str) -> bool:
    return bool(_WANTS_TOOLS_RE.search(user_text)) or _matches_macro_name(user_text)


# Widens both of _wants_tools' call sites (below, and in
# _generate_response_via_hierarchy) so a real question or request engages
# the tool/agent loop by default instead of only the narrow _WANTS_TOOLS_RE
# action-verb allowlist above -- the fleet of specialist agents and real
# tools is otherwise invisible to the majority of ordinary questions, which
# never touch a file/terminal/calendar verb and so never even reach
# generate_with_tools. Default on: a real answer that's tool- or
# agent-verified is worth the extra round-trip latency this costs versus the
# old fast-path. Off switch kept for anyone who wants the old fast, tool-free
# behavior back.
_ALWAYS_ENGAGE_TOOLS = os.getenv("ALWAYS_ENGAGE_TOOLS", "1").strip().lower() in ("1", "true", "yes")

_SMALLTALK_RE = re.compile(
    r"^(hi|hey|hello|yo|sup|good\s+(morning|afternoon|evening|night)|thanks|thank\s+you|"
    r"cheers|ok|okay|cool|nice|great|got\s+it|sounds\s+good|bye|goodnight|see\s+you)\b",
    re.IGNORECASE,
)


def _is_pure_smalltalk(text: str) -> bool:
    """Conservative proxy for 'not actually asking anything' -- a short
    greeting/ack/farewell with no question mark and no real content. The
    ONLY exemption from the widened tool/agent engagement above: a genuine
    question or request still pays the tool loop's latency (exactly what
    ALWAYS_ENGAGE_TOOLS is for), but a bare "hey" or "thanks" shouldn't
    turn into a multi-round tool negotiation."""
    t = text.strip()
    if not t or "?" in t or len(t.split()) > 6:
        return False
    return bool(_SMALLTALK_RE.match(t))


# Real tool-use fallback chain -- Claude is tried first (richest: vision
# support in tool results, native structured tool_use), but confirmed live
# this session that when Anthropic is unavailable (e.g. out of API credit),
# every real tool call (file access, terminal, canvas, ...) used to fail
# and silently fall all the way through to a tool-less plain-chat guess.
# Each of these is a genuinely separate provider with its own real API key,
# all OpenAI-chat-completions-compatible, tried in order until one actually
# has a key configured -- see generate_with_tools_openai_compat (llm.py) and
# its use in _generate_response_via_hierarchy below.
# Order matters -- tried top to bottom. OpenRouter goes first: live-tested
# this session, Groq's on-demand tier's 12k-tokens-per-minute cap fails on
# essentially every real tool-use request regardless of how small the tool
# list is trimmed (see _trim_tools_for_fallback), so trying it first just
# burns a guaranteed-fail round trip before ever reaching something that
# works.
#
# OPENROUTER_MODEL stays "openrouter/auto" rather than a pinned model --
# tried pinning to a real Claude model (anthropic/claude-haiku-4.5) to fix a
# live-observed fabrication bug (the auto-router's cost-optimized pick
# skipped calling read_file and invented plausible-looking file content
# instead of actually reading it). That made things WORSE: this account's
# OpenRouter tier caps named/premium models at ~9840 prompt tokens, and
# Nancy's assembled prompt (system prompt + live context + skills + history)
# runs ~24k tokens even with the trimmed tool list -- every request to the
# pinned model failed outright (402 Prompt tokens limit exceeded) instead of
# sometimes fabricating. "auto" evidently routes around that cap. The real
# fix for the fabrication risk is TOOL_RESULT_FIDELITY_INSTRUCTION (llm.py),
# not the model choice -- a fallback that answers unreliably beats one that
# doesn't answer at all.
# Stands in for an env var on the one entry that doesn't have one.
_OLLAMA_LOCAL_SENTINEL = "OLLAMA_LOCAL"

TOOL_FALLBACK_BACKENDS = [
    ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "OPENROUTER_MODEL", "openrouter/auto", "OpenRouterLLM"),
    ("GROQ_API_KEY", "https://api.groq.com/openai/v1", "GROQ_MODEL", "llama-3.3-70b-versatile", "GroqLLM"),
    ("OPENCODE_API_KEY", "https://opencode.ai/zen/v1", "OPENCODE_MODEL", "big-pickle", "OpenCodeLLM"),
    ("OPENAI_API_KEY", "https://api.openai.com/v1", "OPENAI_MODEL", "gpt-4o-mini", "OpenAILLM"),
    # Ollama Cloud speaks the OpenAI tool-calling dialect at /v1. Without this
    # entry, picking a cloud Ollama model meant every tool-using turn was
    # quietly handed to Claude instead -- the selection looked like it worked
    # right up until you asked it to actually do something.
    ("OLLAMA_CLOUD_API_KEY", "https://ollama.com/v1", "OLLAMA_CLOUD_MODEL", "gpt-oss:120b", "OllamaCloudLLM"),
    # Local daemon: no key to read, so _tool_backend_key hands back a
    # placeholder whenever a local Ollama is actually configured.
    (_OLLAMA_LOCAL_SENTINEL, "", "OLLAMA_MODEL", "llama3.1", "OllamaLLM"),
]

# The live chain reports a local daemon under either name depending on how it
# was built, and both mean "the tool loop may talk to local Ollama".
_TOOL_BACKEND_CLASS_ALIASES = {"OllamaAutoModelsLLM": "OllamaLLM"}


def _tool_backend_key(env_var: str) -> Optional[str]:
    """Resolve the API key for one tool-capable fallback entry.

    Two entries can't just read their own env var: local Ollama has no key at
    all, and Ollama Cloud is commonly configured under OLLAMA_API_KEY because
    that's the name Ollama's own CLI writes.
    """
    if env_var == _OLLAMA_LOCAL_SENTINEL:
        return "ollama" if os.getenv("OLLAMA_BASE_URL") else None
    if env_var == "OLLAMA_CLOUD_API_KEY":
        return os.getenv("OLLAMA_CLOUD_API_KEY") or os.getenv("OLLAMA_API_KEY")
    return os.getenv(env_var)


def _tool_backend_base_url(env_var: str, base_url: str) -> str:
    if env_var == _OLLAMA_LOCAL_SENTINEL:
        return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/") + "/v1"
    return base_url


def _tool_backend_class(name: str) -> str:
    return _TOOL_BACKEND_CLASS_ALIASES.get(name, name)


def _any_tool_backend_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY")) or any(
        _tool_backend_key(env_var) for env_var, *_ in TOOL_FALLBACK_BACKENDS
    )

# Claude gets the full tool arsenal -- its context/rate limits comfortably
# absorb it. The OpenAI-compatible fallbacks don't: live-tested this session,
# sending the complete ~35-tool schema list (every tool list combined) blew
# straight through Groq's on-demand-tier 12k-tokens-per-minute cap on the
# FIRST fallback attempt (413 rate_limit_exceeded, ~22k tokens requested) --
# meaning the "fallback chain" would have silently never worked at all for
# smaller backends. Trimmed here to the tools an actual coding/file/terminal
# request needs, cut by name (not by rebuilding the list) so it can't drift
# out of sync with what FILE_TOOLS/WEB_TOOLS/etc. actually contain.
_FALLBACK_TOOL_NAMES = {
    "read_file", "list_directory", "glob_files", "search_files", "write_file", "edit_file", "multi_edit_file",
    "delete_file", "move_file", "execute_command", "fetch_url", "web_search",
    "post_to_canvas", "open_application", "look_at_camera", "run_background_task",
    "browser_navigate", "browser_get_text", "browser_screenshot", "browser_click", "browser_fill",
    "delegate_to_coworker",
}


def _trim_tools_for_fallback(all_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [t for t in all_tools if t.get("name") in _FALLBACK_TOOL_NAMES]

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

# Illustrative 3D scenes only -- simplified primitives with labels, meant to
# teach spatial/structural relationships for a research topic (e.g. "show me
# a reactor's containment layout"), never a CAD-accurate or buildable model.
# See canvas_store.py's VALID_TYPES comment for the same honest-scope note.
CREATE_3D_SCENE_TOOL: Dict[str, Any] = {
    "name": "create_3d_scene",
    "description": (
        "Post an illustrative 3D scene to the shared canvas -- a small set of labeled geometric "
        "primitives (boxes, spheres, cylinders, cones, tori) arranged in 3D space to visually "
        "explain a structure or concept the user asked about (e.g. 'show me a 3D diagram of a "
        "nuclear reactor's core'). Rendered live with a real orbit-controllable 3D viewer. This is "
        "always a simplified, educational illustration -- never a precise, buildable engineering "
        "model -- so favor a handful of clearly labeled shapes over an attempt at literal accuracy."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string", "description": "one or two sentences of educational context shown alongside the scene"},
            "objects": {
                "type": "array",
                "description": "the shapes making up the scene",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["box", "sphere", "cylinder", "cone", "torus"]},
                        "position": {
                            "type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                            "description": "[x, y, z]",
                        },
                        "size": {
                            "type": "array", "items": {"type": "number"},
                            "description": "shape-specific dimensions, e.g. [width,height,depth] for box, [radius] for sphere",
                        },
                        "color": {"type": "string", "description": "hex color, e.g. '#ff8800'"},
                        "label": {"type": "string", "description": "text shown floating above the shape"},
                    },
                    "required": ["type", "position"],
                },
            },
        },
        "required": ["title", "objects"],
    },
}

# A real live-preview surface -- self-contained HTML/CSS/JS rendered
# client-side in a sandboxed iframe (allow-scripts only; no
# allow-same-origin/allow-top-navigation, so preview content can never touch
# the rest of the app or navigate the real page). This is the direct
# equivalent of Claude's own Artifact tool: a working mockup/demo/interactive
# page Nancy can show inline, not just describe.
ARTIFACT_TOOL: Dict[str, Any] = {
    "name": "create_artifact",
    "description": (
        "Post a real, live, self-contained HTML preview to the shared canvas -- a working mockup, "
        "interactive demo, data visualization, or illustrated document, rendered inline (not just "
        "described in text). The html must be a single complete, self-contained document: inline all "
        "CSS in a <style> tag and all JS in a <script> tag, no external stylesheets/scripts/fonts/CDNs "
        "or network calls (the preview runs sandboxed with no network/parent-page access). Use this "
        "whenever a visual/interactive result would communicate better than a text or code-block reply "
        "-- e.g. a UI mockup, a small game, a chart, or an illustrated research page with diagrams."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "html": {"type": "string", "description": "Complete, self-contained HTML document (inline CSS/JS, no external resources)."},
        },
        "required": ["title", "html"],
    },
}


# ---------------------------------------------------------------------------
# Coworker delegation -- Nancy's own version of the background-subagent
# pattern (fire off a real task, keep talking, report back when it's done)
# rather than blocking the whole conversation on a long-running task. Every
# other tool call in this codebase runs synchronously inside the current
# turn; this is the one deliberate exception, for tasks that plausibly take
# longer than a user wants to wait mid-conversation for.
# ---------------------------------------------------------------------------
_coworker_tasks: Dict[str, Dict[str, Any]] = {}
_COWORKER_MAX_HISTORY = 20

DELEGATE_TASK_TOOL: Dict[str, Any] = {
    "name": "delegate_to_coworker",
    "description": (
        "Hand off a task that would take a while to a coworker to work on in the background, "
        "instead of making the user wait for it mid-conversation. Use this for anything genuinely "
        "long-running or exploratory (deep research, a multi-step analysis, monitoring something "
        "over time) where the right answer is 'I'll look into that and get back to you', not for "
        "quick questions you can just answer directly. Returns immediately; the real result is "
        "pushed to the user (Telegram + web) the moment the coworker finishes -- never silently, "
        "and never faked or guessed in the meantime."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "A clear, self-contained description of what the coworker should do."},
            "domain": {
                "type": "string",
                "description": (
                    "Optional: which specialist should take this (e.g. 'data_science', 'crypto_trading', "
                    "'security'). Leave unset to auto-route the same way ordinary chat messages are routed, "
                    "or to fall back to a general-purpose answer if nothing matches."
                ),
            },
        },
        "required": ["task"],
    },
}


async def _run_coworker_task(task_id: str, description: str, domain: Optional[str]) -> None:
    """The actual background work -- runs completely independently of
    whatever turn/channel requested it. Whichever channel gets notified
    (Telegram + every connected web/voice session) sees the SAME real
    result a synchronous reply would have gotten, just delivered whenever
    it's genuinely ready instead of holding the conversation open."""
    record = _coworker_tasks[task_id]
    try:
        # The LLM picking delegate_to_coworker's optional "domain" arg
        # sometimes names a domain that isn't a real agent key (confirmed
        # live: it once passed "general", which doesn't exist) -- validate
        # against the real roster rather than letting agent_service.run()
        # log a scary "agent not found" error for what's really just an
        # invalid-argument case with a perfectly good fallback already below.
        routed_key = domain if domain in agent_service._agents else None
        if not routed_key and agent_service.is_ready():
            from agents.agent_service import _auto_route
            routed_key = _auto_route(description)

        if routed_key:
            result = await agent_service.run(
                routed_key, {"type": "query", "query": description}, timeout=300.0,
            )
            response_text = str(result.get("response") or result.get("result") or "")
            if not response_text or result.get("success", True) is False:
                # The routed specialist came up empty -- a general-purpose
                # answer is still worth more than reporting failure outright.
                response_text, _ = await _generate_response_via_hierarchy(description, channel="telegram")
        else:
            response_text, _ = await _generate_response_via_hierarchy(description, channel="telegram")

        record["status"] = "done"
        record["result"] = response_text
    except Exception as e:
        logger.exception("Coworker task %s failed", task_id)
        record["status"] = "failed"
        record["result"] = f"Ran into an error: {e}"
    finally:
        record["finished_at"] = _time.time()

    elapsed = record["finished_at"] - record["started_at"]
    icon = "✅" if record["status"] == "done" else "⚠️"
    from telegram_bot import _escape_html
    # Telegram hard-caps a single message at 4096 chars -- confirmed live,
    # a genuinely thorough Telegram-style answer (see the channel="telegram"
    # style addendum, which explicitly asks for real depth) can exceed that
    # on its own, and the send silently 400'd with no result ever reaching
    # the user. Truncate the body rather than trying to fit an unbounded
    # answer into a fixed-size push notification.
    header = f"{icon} <b>Coworker finished</b> ({elapsed:.0f}s)\n\n<i>{_escape_html(description)}</i>\n\n"
    body = _escape_html(record["result"])
    budget = 4000 - len(header)
    if len(body) > budget:
        body = body[:budget].rstrip() + "…"
    await telegram_notifier.send_html(header + body)
    asyncio.create_task(_broadcast_reply_to_web(f"[Coworker] {record['result']}", source="coworker"))


async def _delegate_to_coworker(task: str, domain: Optional[str] = None) -> Dict[str, Any]:
    task = (task or "").strip()
    if not task:
        return {"success": False, "error": "task description is required"}

    task_id = f"cw-{int(_time.time() * 1000)}"
    _coworker_tasks[task_id] = {
        "id": task_id, "task": task, "domain": domain,
        "status": "working", "result": None,
        "started_at": _time.time(), "finished_at": None,
    }
    # Trim in-memory history so this never grows without bound across a
    # long-running process -- same reasoning as _history_to_text's cap.
    if len(_coworker_tasks) > _COWORKER_MAX_HISTORY:
        oldest_id = min(_coworker_tasks, key=lambda k: _coworker_tasks[k]["started_at"])
        if _coworker_tasks[oldest_id]["status"] != "working":
            _coworker_tasks.pop(oldest_id, None)

    asyncio.create_task(_run_coworker_task(task_id, task, domain))
    return {
        "success": True,
        "task_id": task_id,
        "message": f"Sent to {domain or 'a specialist'} -- I'll let you know the moment it's done.",
    }


def _attach_python_syntax_check(result: Dict[str, Any], path: str) -> None:
    """Real verification after a write/edit actually lands on disk -- the
    same discipline Claude Code itself follows (compile-check a file right
    after touching it) rather than trusting a write succeeded just because
    no exception was raised. Only Python is covered here (file_access's
    check_python_syntax uses the builtin compiler, no external tooling
    needed); lsp_client's diagnostics check, called right after this,
    covers JS/TS too when a language server happens to be available."""
    if result.get("success") and path.endswith(".py"):
        error = file_access.check_python_syntax(path)
        if error:
            result["syntax_error"] = error


def _all_chat_tools() -> List[Dict[str, Any]]:
    """The single, real source of truth for "every tool Claude's tool-use
    loop can call" -- used by BOTH the interactive chat path
    (_generate_response_via_hierarchy) and the cron/webhook-triggered skill
    path (_run_skill_with_tools, further down this file). Factored out
    after finding live that the second call site had silently fallen out of
    sync with every tool added to the first one today (browser, camera,
    background tasks, clipboard, SMS, and the whole everyday/archive/
    network/personal tools batch) -- a real, easy-to-repeat mistake this
    function makes structurally impossible to repeat, since editing this
    list edits both callers at once."""
    return (
        FILE_TOOLS + terminal_tool.TERMINAL_TOOLS + [CREATE_SUBAGENT_TOOL, CANVAS_TOOL, CREATE_3D_SCENE_TOOL, ARTIFACT_TOOL, DELEGATE_TASK_TOOL]
        + mcp_manager.list_plugin_tools() + WEB_TOOLS + browser_tool.BROWSER_TOOLS
        + COMPUTER_USE_TOOLS + APP_LAUNCHER_TOOLS + BACKGROUND_TASK_TOOLS + CLIPBOARD_TOOLS
        + SMS_TOOLS + WATCH_TOOLS + SECURITY_MODE_TOOLS + MACRO_TOOLS + DEVICE_ROUTING_TOOLS + PRESENCE_TOOLS + PROFILE_TOOLS + SELF_MAINTENANCE_TOOLS + MEMORY_TOOLS + TRADING_BACKTEST_TOOLS + SWARM_TOOLS
        + git_tool.GIT_TOOLS + docker_tool.DOCKER_TOOLS + process_control.PROCESS_CONTROL_TOOLS + FLOW_TOOLS + LANGFLOW_TOOLS
        + everyday_tools.EVERYDAY_TOOLS + archive_tools.ARCHIVE_TOOLS
        + network_tools.NETWORK_TOOLS + personal_tools.PERSONAL_TOOLS + UTILITY_TOOLS
        + BACKUP_TOOLS + HOME_ASSISTANT_TOOLS + SPOTIFY_TOOLS + google_calendar.CALENDAR_TOOLS + NODE_TOOLS + DIFF_TOOLS
        + doc_extraction.DOC_EXTRACTION_TOOLS + VOICE_CALL_TOOLS + NUMBERED_OVERLAY_TOOLS + MEDIA_TOOLS
        + RESEARCH_TOOLS + DOCUMENT_TOOLS + EMAIL_TOOLS + JUPYTER_TOOLS
    )


async def _open_application_dispatch(target: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
    """Shared by open_application (chat tool) and /system/open-application
    (Command Layer REST route) -- this backend runs inside a Docker
    container with no display of its own (confirmed live:
    computer_use_tool.take_screenshot already fails the same way, "DISPLAY"
    unset), so launching anything here directly would only ever affect the
    invisible container, never the user's real desktop. If a "host" node is
    registered (node_agent_stub.py, run natively on the real machine),
    dispatch there instead so the app actually opens somewhere the user can
    see it; otherwise fall back to launching locally, which is correct when
    this backend happens to be running natively rather than containerized."""
    if HOST_NODE_ID in node_host.list_nodes():
        result = await node_host.dispatch_open_application(HOST_NODE_ID, target, args)
    else:
        result = await app_launcher.open_application(target, args)
    evidence_ledger.record_evidence("open_application", target, result.get("success", False))
    return result


def _voice_mismatch() -> bool:
    """Normally: True only when THIS turn's audio was actually checked
    against an enrolled voice profile and it did NOT match -- always False
    for typed input, and always False when no profile is enrolled (nothing
    to compare against, so there's no signal to act on).

    During lockdown_switch's window, the bar raises: anything short of a
    real, confirmed voice match counts as a mismatch, including typed text
    (no voice at all to check) and an inconclusive check (too-short/silent
    clip) -- "Billion, lock down" means "don't act on anything I didn't
    personally say," not just "flag the ones that clearly didn't match."""
    voice_match = _current_voice_match.get()
    if lockdown_switch.is_active():
        return not (voice_match and voice_match.get("match") is True)
    return bool(voice_match and voice_match.get("match") is False)


async def _request_approval(description: str, timeout: float = 120.0) -> bool:
    """The one place every chat-tool-triggered Telegram approval actually
    goes through. When this turn's voice didn't match the enrolled profile,
    prepends a real, visible warning so whoever approves on Telegram sees
    that signal before deciding -- see the call sites below, several of
    which also use _voice_mismatch() to force this approval to even be
    asked in the first place (a case that would otherwise be skipped, e.g.
    while arm_switch is active). This can never fully lock the real user
    out: Telegram approval remains the actual, final human gate regardless
    of what voice_id's real-but-lightweight MFCC matching decides -- a
    mismatch only makes the ask louder and harder to skip, so a false
    negative (background noise, a cold, a different mic) degrades to "one
    extra approval tap," never to a hard denial."""
    if _voice_mismatch():
        voice_match = _current_voice_match.get()
        if voice_match and voice_match.get("similarity") is not None:
            warning = f"⚠️ VOICE DID NOT MATCH your enrolled profile (similarity {voice_match['similarity']}) -- this command came from a voice Billion doesn't recognize."
        elif lockdown_switch.is_active():
            warning = "⚠️ LOCKDOWN ACTIVE and this command had no confirmed matching voice (typed, or an unclear sample) -- Billion is treating it as unverified."
        else:
            warning = "⚠️ VOICE CHECK inconclusive for this command -- treating it as unverified."
        description = f"{warning}\n\n{description}"
    return await telegram_notifier.request_approval(description, timeout=timeout)


async def _run_macro(macro: "macro_store.Macro") -> Dict[str, Any]:
    """Replays each step of a saved macro through the exact same
    _execute_file_tool dispatcher every other tool call goes through, so
    each step's own safety gating (approval, arm_switch, voice match) still
    applies exactly as if it had been called directly -- a macro is a
    shortcut for calling several real tools in a row, never a way to skip
    what any one of them would normally require. Stops at the first real
    step failure rather than blindly running the rest."""
    results: List[Dict[str, Any]] = []
    for step in macro.steps:
        step_tool = step.get("tool", "")
        step_args = step.get("args") or {}
        try:
            result = await _execute_file_tool(step_tool, step_args)
        except Exception as e:
            result = {"success": False, "error": str(e)}
        results.append({"tool": step_tool, "result": result})
        if not result.get("success", True):
            break
    return {"success": all(r["result"].get("success", True) for r in results), "steps_run": results}


async def _execute_file_tool(name: str, tool_input: Dict[str, Any], user_hint: str = "") -> Dict[str, Any]:
    if mcp_manager.is_plugin_tool(name):
        return await mcp_manager.call_tool(name, tool_input)

    if name == "delegate_to_coworker":
        return await _delegate_to_coworker(tool_input.get("task", ""), tool_input.get("domain"))

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

    if name == "create_3d_scene":
        scene = {
            "description": tool_input.get("description", ""),
            "objects": tool_input.get("objects", []),
        }
        try:
            item = canvas_store.create("3d_scene", tool_input.get("title", ""), json.dumps(scene))
        except ValueError as e:
            return {"success": False, "error": str(e)}
        await event_bus.publish("CANVAS_ITEM_ADDED", {"item": item.to_public_dict()})
        return {"success": True, "item_id": item.id}

    if name == "create_artifact":
        html = tool_input.get("html", "")
        lint_findings = security_lint.lint_content(html)
        try:
            item = canvas_store.create("html_preview", tool_input.get("title", ""), html)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        await event_bus.publish("CANVAS_ITEM_ADDED", {"item": item.to_public_dict()})
        result: Dict[str, Any] = {"success": True, "item_id": item.id}
        if lint_findings:
            result["lint_warning"] = security_lint.format_findings(lint_findings)
        return result

    if name == "fetch_url":
        return await fetch_url(tool_input.get("url", ""))

    if name == "web_search":
        return await web_search(tool_input.get("query", ""), max_results=tool_input.get("max_results", 5))

    if name == "generate_image":
        result = await generate_image(tool_input.get("prompt", ""), title=tool_input.get("title", ""))
        evidence_ledger.record_evidence("generate_image", tool_input.get("prompt", "")[:80], result.get("success", False))
        return result

    if name == "search_arxiv":
        return await search_arxiv(tool_input.get("query", ""), max_results=tool_input.get("max_results", 5))

    if name == "get_prediction_markets":
        return await get_prediction_markets(tool_input.get("query", ""), max_results=tool_input.get("max_results", 5))

    if name in ("create_word_document", "create_excel_spreadsheet", "create_pdf_document", "create_powerpoint_presentation"):
        loop = asyncio.get_event_loop()
        if name == "create_word_document":
            fn = lambda: create_word_document(tool_input.get("path", ""), tool_input.get("title", ""), tool_input.get("sections"))
        elif name == "create_excel_spreadsheet":
            fn = lambda: create_excel_spreadsheet(
                tool_input.get("path", ""), tool_input.get("headers", []), tool_input.get("rows", []),
                sheet_name=tool_input.get("sheet_name", "Sheet1"),
            )
        elif name == "create_powerpoint_presentation":
            fn = lambda: create_powerpoint_presentation(
                tool_input.get("path", ""), tool_input.get("title", ""), tool_input.get("slides", []),
                subtitle=tool_input.get("subtitle", ""),
            )
        else:
            fn = lambda: create_pdf_document(tool_input.get("path", ""), tool_input.get("title", ""), tool_input.get("sections"))
        result = await loop.run_in_executor(None, fn)
        evidence_ledger.record_evidence(name, tool_input.get("path", ""), result.get("success", False))
        return result

    if name == "send_email":
        to, subject, body = tool_input.get("to", ""), tool_input.get("subject", ""), tool_input.get("body", "")
        if not await _request_approval(f"Nancy wants to email {to}: {subject!r}", timeout=120.0):
            return {"success": False, "error": "User did not approve this email."}
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: send_email(to, subject, body))
        evidence_ledger.record_evidence("send_email", f"to {to}: {subject}", result.get("success", False))
        return result

    if name == "list_recent_emails":
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: list_recent_emails(tool_input.get("limit", 10), tool_input.get("unread_only", False))
        )

    if name == "run_python_kernel":
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: run_python_kernel(tool_input.get("code", "")))
        evidence_ledger.record_evidence("run_python_kernel", tool_input.get("code", "")[:80], result.get("success", False))
        return result

    if name == "restart_python_kernel":
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, restart_python_kernel)

    if name == "llm_structured_task":
        return await structured_llm_call(tool_input.get("prompt", ""), tool_input.get("json_schema", {}))

    if name == "create_backup":
        if not arm_switch.is_armed() or _voice_mismatch():
            approved = await _request_approval(
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

    if name == "list_calendar_events":
        return await google_calendar.list_events(
            tool_input.get("time_min"), tool_input.get("time_max"), tool_input.get("max_results", 10),
        )
    if name == "check_calendar_conflicts":
        return await google_calendar.check_conflicts(tool_input.get("start", ""), tool_input.get("end", ""))
    if name == "create_calendar_event":
        approved = await _request_approval(
            f"Nancy wants to create a calendar event: {tool_input.get('summary')} "
            f"({tool_input.get('start')} - {tool_input.get('end')})", timeout=120.0,
        )
        if not approved:
            return {"success": False, "error": "User did not approve this calendar event."}
        return await google_calendar.create_event(
            tool_input.get("summary", ""), tool_input.get("start", ""), tool_input.get("end", ""),
            tool_input.get("description"), tool_input.get("location"), tool_input.get("timezone_name"),
        )
    if name == "delete_calendar_event":
        approved = await _request_approval(
            f"Nancy wants to delete calendar event: {tool_input.get('event_id')}", timeout=120.0,
        )
        if not approved:
            return {"success": False, "error": "User did not approve deleting this calendar event."}
        return await google_calendar.delete_event(tool_input.get("event_id", ""))

    if name == "node_execute_command":
        return await node_host.dispatch_command(
            tool_input.get("node_id", ""), tool_input.get("command", ""), cwd=tool_input.get("cwd"),
        )

    if name == "show_diff":
        return await post_diff_to_canvas(tool_input.get("old_text", ""), tool_input.get("new_text", ""), tool_input.get("title", "Diff"))

    if name == "extract_document_text":
        return doc_extraction.extract_document(tool_input.get("path", ""))

    if name == "place_phone_call":
        if not arm_switch.is_armed() or _voice_mismatch():
            approved = await _request_approval(
                f"Nancy wants to call {tool_input.get('to_number')} and say: {tool_input.get('message', '')[:200]}", timeout=120.0,
            )
            if not approved:
                return {"success": False, "error": "User did not approve this phone call."}
        from providers.registry import get_ordered_providers
        providers = get_ordered_providers("telephony")
        if not providers:
            return {"success": False, "error": "No telephony provider is configured (e.g. TWILIO_ACCOUNT_SID)."}
        return await providers[0].place_call(tool_input.get("to_number", ""), message=tool_input.get("message", ""))

    if name in ("take_screenshot", "get_screen_size"):
        loop = asyncio.get_event_loop()
        fn = computer_use_tool.take_screenshot if name == "take_screenshot" else computer_use_tool.get_screen_size
        return await loop.run_in_executor(None, fn)

    if name == "open_application":
        # Ungated -- same risk profile as take_screenshot/get_screen_size:
        # launching an app (not an arbitrary shell command with flags) is
        # the same action as double-clicking an icon, not a destructive one.
        target = tool_input.get("target", "")
        args = tool_input.get("args")
        return await _open_application_dispatch(target, args)

    if name == "look_at_camera":
        # Gated -- turning on the user's real webcam is meaningfully more
        # privacy-sensitive than a screenshot, even though the user just
        # asked for it in this same turn; a phone approval is a cheap extra
        # check against a model deciding to check the camera when the user
        # didn't really mean it. Same container-has-no-hardware-access
        # reasoning as open_application: dispatches to the real host node
        # if one's registered, since a webcam is real hardware the Docker
        # container has no path to at all.
        if not await _request_approval("Nancy wants to: take a single snapshot from your webcam", timeout=120.0):
            return {"success": False, "error": "User did not approve this camera snapshot."}
        if HOST_NODE_ID in node_host.list_nodes():
            result = await node_host.dispatch_camera_snapshot(HOST_NODE_ID)
        else:
            return {"success": False, "error": "No camera-capable node is registered (see node_agent_stub.py) and this backend has no direct camera access."}
        evidence_ledger.record_evidence("look_at_camera", "webcam", result.get("success", False))
        if result.get("success") and result.get("image_base64"):
            result["_image_base64"] = result.pop("image_base64")
        return result

    if name == "check_security_camera":
        url = os.getenv("SECURITY_CAMERA_SNAPSHOT_URL")
        if not url:
            return {"success": False, "error": "SECURITY_CAMERA_SNAPSHOT_URL is not configured."}
        if not await _request_approval("Nancy wants to: check the security camera", timeout=120.0):
            return {"success": False, "error": "User did not approve this camera check."}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
            evidence_ledger.record_evidence("check_security_camera", "security_camera", True)
            return {"success": True, "_image_base64": base64.b64encode(resp.content).decode()}
        except Exception as e:
            evidence_ledger.record_evidence("check_security_camera", "security_camera", False)
            return {"success": False, "error": str(e)}

    if name == "run_background_task":
        # Ungated -- starting the task itself is harmless; whatever real
        # actions it performs along the way (file writes, commands, ...)
        # still go through their own normal approval gates individually,
        # same as any chat-driven tool call.
        description = str(tool_input.get("description", "")).strip()
        if not description:
            return {"success": False, "error": "description is required"}
        mission = mission_store.create(
            title=description[:80], description=description,
            owner="nancy_background", priority="medium", risk="low", tags=["background"],
        )
        await event_bus.publish("MISSION_CREATED", {"mission": mission.to_public_dict()})
        try:
            mission_store.transition(mission.id, "execution")
        except MissionError as e:
            return {"success": False, "error": f"Could not start background task: {e}"}
        started = mission_store.get(mission.id)
        mission_store.set_dispatched(mission.id)
        await event_bus.publish("MISSION_STARTED", {"mission": started.to_public_dict() if started else None})
        asyncio.create_task(_execute_background_chat_task(mission.id, description))
        return {
            "success": True,
            "mission_id": mission.id,
            "response": "Started in the background -- I'll notify you when it's done, nothing until then.",
        }

    if name in ("clipboard_read", "clipboard_write"):
        # Same container-has-no-real-desktop reasoning as open_application/
        # look_at_camera -- a headless Linux container has no OS clipboard of
        # its own to share with the user's real desktop.
        if HOST_NODE_ID not in node_host.list_nodes():
            return {"success": False, "error": "No node is registered (see node_agent_stub.py) and this backend has no direct clipboard access."}
        if name == "clipboard_read":
            return await node_host.dispatch_clipboard_read(HOST_NODE_ID)
        return await node_host.dispatch_clipboard_write(HOST_NODE_ID, tool_input.get("text", ""))

    if name == "send_sms":
        to_number = tool_input.get("to_number", "")
        message = tool_input.get("message", "")
        if not await _request_approval(f"Nancy wants to text {to_number}: {message[:200]}", timeout=120.0):
            return {"success": False, "error": "User did not approve this text message."}
        from providers.registry import get_ordered_providers
        providers = get_ordered_providers("telephony")
        if not providers:
            return {"success": False, "error": "No telephony provider is configured (e.g. TWILIO_ACCOUNT_SID)."}
        return await providers[0].send_sms(to_number, message)

    if name == "trigger_sos":
        contact = os.getenv("EMERGENCY_CONTACT_NUMBER")
        if not contact:
            return {"success": False, "error": "EMERGENCY_CONTACT_NUMBER is not configured."}
        situation = tool_input.get("situation", "").strip()
        message = f"SOS from Billion, Sir requested help: {situation}" if situation else "SOS triggered -- Billion's user requested help."
        from providers.registry import get_ordered_providers
        providers = get_ordered_providers("telephony")
        if not providers:
            return {"success": False, "error": "No telephony provider is configured (e.g. TWILIO_ACCOUNT_SID)."}
        sms_result = await providers[0].send_sms(contact, message)
        call_result = await providers[0].place_call(contact, message=message)
        # Also alert the owner's own Telegram -- if the emergency contact is
        # someone else, the owner should still know this fired.
        await telegram_notifier.send(f"🚨 SOS triggered, Sir: {message}")
        return {"success": True, "sms": sms_result, "call": call_result}

    if name == "create_watch":
        try:
            watch = watch_store.watch_store.create(
                tool_input["url"], tool_input.get("description", ""), tool_input.get("kind", "text"),
                tool_input.get("target_price"), tool_input.get("check_interval_minutes", 60.0),
                tool_input.get("one_shot", True),
            )
        except ValueError as e:
            return {"success": False, "error": str(e)}
        return {"success": True, "watch_id": watch.id}
    if name == "list_watches":
        return {"success": True, "watches": [w.to_public_dict() for w in watch_store.watch_store.list()]}
    if name == "delete_watch":
        deleted = watch_store.watch_store.delete(tool_input.get("watch_id", ""))
        return {"success": deleted} if deleted else {"success": False, "error": "No such watch."}

    if name == "enable_lockdown":
        return lockdown_switch.enable(tool_input.get("duration_minutes", 60) * 60.0, tool_input.get("reason"))
    if name == "disable_lockdown":
        return lockdown_switch.disable()
    if name == "enable_focus_mode":
        return focus_mode.enable(tool_input.get("duration_minutes", 60) * 60.0)
    if name == "disable_focus_mode":
        queued = focus_mode.disable_and_flush()
        if queued:
            digest = "While you were focused, Sir, here's what happened:\n\n" + "\n".join(f"- {m['text']}" for m in queued)
            await telegram_notifier.send(digest)
        return {"success": True, "queued_count": len(queued)}

    if name == "create_macro":
        try:
            macro = macro_store.macro_store.create(tool_input.get("name", ""), tool_input.get("steps", []))
        except ValueError as e:
            return {"success": False, "error": str(e)}
        return {"success": True, "macro_id": macro.id}
    if name == "run_macro":
        macro = macro_store.macro_store.find_by_name(tool_input.get("name", ""))
        if macro is None:
            return {"success": False, "error": f"No macro named {tool_input.get('name')!r}."}
        return await _run_macro(macro)
    if name == "list_macros":
        return {"success": True, "macros": [m.to_public_dict() for m in macro_store.macro_store.list()]}
    if name == "delete_macro":
        deleted = macro_store.macro_store.delete(tool_input.get("macro_id", ""))
        return {"success": deleted} if deleted else {"success": False, "error": "No such macro."}

    if name == "schedule_macro":
        macro_name = tool_input.get("macro_name", "")
        macro = macro_store.macro_store.find_by_name(macro_name)
        if macro is None:
            return {"success": False, "error": f"No macro named {macro_name!r}. Create it first with create_macro."}
        hour = int(tool_input.get("hour", 0))
        minute = int(tool_input.get("minute", 0))
        job = cron_store.create(
            name=f"Macro: {macro.name}", description=f"Auto-runs the '{macro.name}' scene macro daily.",
            hour=hour, minute=minute, action_type="run_macro", action_payload={"name": macro.name},
        )
        return {"success": True, "cron_job_id": job.id, "hour": hour, "minute": minute}

    if name == "set_active_device":
        manager.active_device_label = tool_input.get("device_label", "").strip() or None
        return {"success": True, "active_device_label": manager.active_device_label}
    if name == "list_connected_devices":
        return {
            "success": True,
            "connected_devices": manager.connected_device_labels(),
            "active_device_label": manager.active_device_label,
        }

    if name == "register_presence_device":
        try:
            device = presence_store.presence_store.create(
                tool_input.get("person_name", ""), tool_input.get("host", ""),
                tool_input.get("on_arrive_macro"), tool_input.get("on_leave_macro"),
            )
        except ValueError as e:
            return {"success": False, "error": str(e)}
        return {"success": True, "device_id": device.id}
    if name == "list_presence_devices":
        return {"success": True, "devices": [d.to_public_dict() for d in presence_store.presence_store.list()]}
    if name == "remove_presence_device":
        deleted = presence_store.presence_store.delete(tool_input.get("device_id", ""))
        return {"success": deleted} if deleted else {"success": False, "error": "No such device."}
    if name == "who_is_present":
        return {"success": True, "present": presence_store.presence_store.who_is_present()}

    if name == "create_profile":
        try:
            profile = profiles_store.profile_store.create(tool_input.get("name", ""))
        except ValueError as e:
            return {"success": False, "error": str(e)}
        return {"success": True, "profile_id": profile.id}
    if name == "list_profiles":
        return {"success": True, "profiles": [p.to_public_dict() for p in profiles_store.profile_store.list()]}
    if name == "delete_profile":
        deleted = profiles_store.profile_store.delete(tool_input.get("profile_id", ""))
        return {"success": deleted} if deleted else {"success": False, "error": "No such profile."}
    if name == "enroll_profile_voice":
        profile_id = tool_input.get("profile_id", "")
        profile = profiles_store.profile_store.get(profile_id)
        if profile is None:
            return {"success": False, "error": "No such profile."}
        turn_audio = _current_turn_audio.get()
        if turn_audio is None:
            return {"success": False, "error": "No voice audio captured for this turn -- ask them to say something while enrolling."}
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, household_voice_id.enroll_member, profile_id, turn_audio)
        if result.get("success"):
            profiles_store.profile_store.mark_voice_enrolled(profile_id)
        return result
    if name == "who_is_speaking":
        profile_id = _current_speaker_profile_id.get()
        if profile_id is None:
            return {"success": True, "speaking": None}
        profile = profiles_store.profile_store.get(profile_id)
        return {"success": True, "speaking": profile.to_public_dict() if profile else {"id": profile_id}}

    if name == "run_self_maintenance_check":
        vuln_result = await self_maintenance.check_dependency_vulnerabilities()
        marker_result = self_maintenance.scan_stale_markers()
        return {"success": True, "vulnerabilities": vuln_result, "stale_markers": marker_result}
    if name == "get_system_alerts":
        return {
            "success": True,
            "overall_severity": alert_center.alert_center.overall_severity(),
            "statuses": [s.to_public_dict() for s in alert_center.alert_center.list()],
        }

    if name == "run_agent_swarm":
        max_agents = int(tool_input.get("max_agents", 8))
        return await agent_service.run(
            "swarm_coordinator", {"type": "swarm_execute", "goal": tool_input.get("goal", ""), "max_agents": max_agents},
            timeout=120.0,
        )

    if name == "list_langflow_flows":
        return await langflow_client.list_flows()
    if name == "run_langflow_flow":
        return await langflow_client.run_flow(tool_input.get("flow_id_or_name", ""), tool_input.get("input_value", ""))

    if name == "create_flow":
        try:
            flow = flow_engine.flow_store.create(tool_input.get("name", ""), tool_input.get("nodes", []), tool_input.get("edges", []))
        except ValueError as e:
            return {"success": False, "error": str(e)}
        return {"success": True, "flow_id": flow.id}
    if name == "list_flows":
        return {"success": True, "flows": [f.to_public_dict() for f in flow_engine.flow_store.list()]}
    if name == "get_flow":
        flow = flow_engine.flow_store.get(tool_input.get("flow_id", ""))
        return {"success": True, "flow": flow.to_public_dict()} if flow else {"success": False, "error": "No such flow."}
    if name == "update_flow":
        try:
            flow = flow_engine.flow_store.update(
                tool_input.get("flow_id", ""), tool_input.get("name"), tool_input.get("nodes"), tool_input.get("edges"),
            )
        except ValueError as e:
            return {"success": False, "error": str(e)}
        return {"success": True, "flow": flow.to_public_dict()} if flow else {"success": False, "error": "No such flow."}
    if name == "delete_flow":
        deleted = flow_engine.flow_store.delete(tool_input.get("flow_id", ""))
        return {"success": deleted} if deleted else {"success": False, "error": "No such flow."}
    if name == "run_flow":
        flow = flow_engine.flow_store.get(tool_input.get("flow_id", ""))
        if flow is None:
            return {"success": False, "error": "No such flow."}
        # Every node's real tool call still goes through THIS SAME
        # dispatcher recursively, so each step's own approval/voice-match
        # gating applies exactly as if called directly -- same principle
        # as _run_macro's macro replay.
        return await flow_engine.execute_flow(
            flow, tool_input.get("inputs", {}) or {},
            tool_executor=lambda n, a: _execute_file_tool(n, a, user_hint=user_hint),
            llm_generate=lambda p: llm_backend.generate(p, max_tokens=800, temperature=0.5),
        )

    if name == "list_trading_strategies":
        return {"success": True, "strategies": list_trading_strategies_impl()}
    if name == "run_forex_backtest":
        try:
            return await run_forex_backtest(
                tool_input.get("pair", ""), tool_input.get("strategy", ""),
                days=int(tool_input.get("days", 90)), params=tool_input.get("params"),
            )
        except ValueError as e:
            return {"success": False, "error": str(e)}
    if name == "run_crypto_backtest":
        symbol = tool_input.get("symbol", "")
        strategy = tool_input.get("strategy", "")
        days = int(tool_input.get("days", 90))
        candles = await crypto_data.get_historical(symbol, days=days)
        if len(candles) < 10:
            return {"success": False, "error": f"Not enough historical data for {symbol} ({len(candles)} candles fetched)."}
        try:
            result = run_full_validation(candles, strategy, tool_input.get("params"))
        except ValueError as e:
            return {"success": False, "error": str(e)}
        result["symbol"] = symbol
        return result

    if name == "search_memory":
        top_k = min(int(tool_input.get("top_k", 10)), 30)
        results = memory_manager.graph.query_with_scores(tool_input.get("query", ""), top_k=top_k)
        return {
            "success": True,
            "results": [
                {
                    "type": node.type.value,
                    "content": node.content,
                    "similarity": round(score, 3),
                    "importance": node.importance,
                    "first_mentioned_at": node.created_at,
                    "last_mentioned_at": node.metadata.get("last_mentioned_at", node.created_at),
                    "mention_count": node.metadata.get("mention_count", 1),
                }
                for node, score in results
            ],
        }

    if name == "get_automation_suggestions":
        suggestions = pattern_suggestions.get_new_suggestions(memory_manager.graph)
        return {"success": True, "suggestions": suggestions}

    if name == "search_conversation_history":
        results = conversation_log.search(
            tool_input.get("query", ""), limit=int(tool_input.get("limit", 10))
        )
        return {"success": True, "results": results, "stats": conversation_log.stats()}

    if name in ("calculate", "convert_units", "convert_currency", "get_weather", "generate_password", "generate_qr_code", "shorten_url", "get_public_ip_info"):
        fn = getattr(everyday_tools, name)
        kwargs = {k: v for k, v in tool_input.items() if v is not None}
        return await fn(**kwargs)

    if name in ("zip_files", "unzip_file", "resize_image", "merge_pdfs", "split_pdf"):
        # Sync functions (pure local file I/O, same convention as file_access.py) -- ungated:
        # these are additive/reorganizing operations on files the user already has, not
        # destructive ones (nothing existing gets overwritten or deleted).
        fn = getattr(archive_tools, name)
        kwargs = {k: v for k, v in tool_input.items() if v is not None}
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(**kwargs))

    if name in (
        "ping_host", "check_port_open", "dns_lookup", "get_public_ip",
        "lan_scan", "traceroute", "get_network_interfaces",
    ):
        fn = getattr(network_tools, name)
        kwargs = {k: v for k, v in tool_input.items() if v is not None}
        if asyncio.iscoroutinefunction(fn):
            return await fn(**kwargs)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(**kwargs))

    if name in ("add_note", "list_notes", "search_notes", "track_expense", "list_expenses"):
        fn = getattr(personal_tools, name)
        kwargs = {k: v for k, v in tool_input.items() if v is not None}
        return await fn(**kwargs)

    if name in ("browser_navigate", "browser_get_text", "browser_screenshot"):
        # Ungated, read-oriented -- same tier as fetch_url/take_screenshot.
        # SSRF-checked inside browser_navigate itself (net_policy.is_blocked_host).
        fn = getattr(browser_tool, name)
        kwargs = {k: v for k, v in tool_input.items() if v is not None}
        return await fn(**kwargs)

    if name in ("browser_click", "browser_fill"):
        # Gated -- a real action on a real page (submitting a form, following
        # a link, etc.), same tier as computer_use_tool's click/type actions.
        description = (
            f"click on the current page: {tool_input.get('selector')}" if name == "browser_click"
            else f"type into the current page ({tool_input.get('selector')}): {tool_input.get('text', '')!r}"
        )
        approved = await _request_approval(f"Nancy wants to: {description}", timeout=120.0)
        if not approved:
            return {"success": False, "error": "User did not approve this browser action."}
        fn = getattr(browser_tool, name)
        kwargs = {k: v for k, v in tool_input.items() if v is not None}
        return await fn(**kwargs)

    if name in COMPUTER_ACTION_TOOLS:
        description = {
            "click_screen": f"click the screen at ({tool_input.get('x')}, {tool_input.get('y')})",
            "move_mouse": f"move the mouse to ({tool_input.get('x')}, {tool_input.get('y')})",
            "type_text": f"type: {tool_input.get('text', '')!r}",
            "press_key": f"press the '{tool_input.get('key')}' key",
            "scroll_screen": f"scroll by {tool_input.get('amount')}",
        }[name]
        approved = await _request_approval(
            f"Nancy wants to control your screen: {description}", timeout=120.0
        )
        if not approved:
            return {"success": False, "error": "User did not approve this screen control action."}
        # Same container-has-no-display problem as _open_application_dispatch:
        # route to the paired host node when one is registered, otherwise fall
        # back to local pyautogui (correct when this backend happens to be
        # running natively rather than inside Docker).
        if HOST_NODE_ID in node_host.list_nodes():
            host_dispatch = {
                "click_screen": lambda: node_host.dispatch_mouse_click(
                    HOST_NODE_ID, x=tool_input.get("x"), y=tool_input.get("y"),
                    button=tool_input.get("button", "left"), double=tool_input.get("double", False),
                ),
                "move_mouse": lambda: node_host.dispatch_mouse_move(
                    HOST_NODE_ID, tool_input.get("x"), tool_input.get("y")
                ),
                "type_text": lambda: node_host.dispatch_keyboard_type(HOST_NODE_ID, tool_input.get("text", "")),
                "press_key": lambda: node_host.dispatch_keyboard_key(HOST_NODE_ID, tool_input.get("key", "")),
                "scroll_screen": lambda: node_host.dispatch_mouse_scroll(HOST_NODE_ID, tool_input.get("amount", -3)),
            }
            result = await host_dispatch[name]()
        else:
            loop = asyncio.get_event_loop()
            fn = getattr(computer_use_tool, name)
            result = await loop.run_in_executor(None, lambda: fn(**tool_input))
        evidence_ledger.record_evidence(name, description, result.get("success", False))
        return result

    if name in ("list_screen_elements", "click_numbered_element"):
        # Host-only -- Windows UI Automation enumeration has no meaning inside
        # the display-less Docker container, unlike click_screen's pyautogui
        # fallback above (pyautogui can still move a virtual/headless pointer;
        # pywinauto's UIA backend genuinely has nothing to enumerate there).
        if HOST_NODE_ID not in node_host.list_nodes():
            return {"success": False, "error": "No host node registered -- numbered element control requires node_agent_stub.py running on the real desktop."}
        if name == "list_screen_elements":
            result = await node_host.dispatch_list_elements(HOST_NODE_ID)
            evidence_ledger.record_evidence(name, "list foreground window elements", result.get("success", False))
            return result
        number = tool_input.get("number")
        approved = await _request_approval(
            f"Nancy wants to click numbered element #{number} on your screen", timeout=120.0
        )
        if not approved:
            return {"success": False, "error": "User did not approve this screen control action."}
        result = await node_host.dispatch_click_element(
            HOST_NODE_ID, number, background=tool_input.get("background", False)
        )
        evidence_ledger.record_evidence(name, f"click element #{number}", result.get("success", False))
        return result

    if name == "create_subagent":
        return await _execute_create_subagent_tool(tool_input)

    if name == "execute_command":
        command = str(tool_input.get("command", ""))
        # A voice mismatch never forces approval for a genuinely safe/
        # allowlisted command (git status, ls, ...) -- only escalates the
        # cases that were already sensitive enough to consider approval.
        if not terminal_tool._is_safe_command(command) and (not arm_switch.is_armed() or _voice_mismatch()):
            approved = await _request_approval(
                f"Nancy wants to run a command:\n\n{command}", timeout=120.0
            )
            if not approved:
                return {"success": False, "error": "User did not approve this command."}
        return await terminal_tool.execute_command(
            command, cwd=tool_input.get("cwd"), use_egress_proxy=tool_input.get("use_egress_proxy", False), sandbox=tool_input.get("sandbox"),
        )

    if name in ("git_status", "git_diff", "git_log", "git_branch", "git_commit", "git_push", "git_pull"):
        # git_branch is only mutating when it's actually creating/switching
        # branches (create/checkout set) -- a bare listing is read-only.
        is_mutating = name in ("git_commit", "git_push", "git_pull") or (
            name == "git_branch" and (tool_input.get("create") or tool_input.get("checkout"))
        )
        if is_mutating and (not arm_switch.is_armed() or _voice_mismatch()):
            description = {
                "git_commit": f"git commit: {str(tool_input.get('message', ''))[:200]!r} in {tool_input.get('cwd') or 'current dir'}",
                "git_push": f"git push to {tool_input.get('remote', 'origin')} in {tool_input.get('cwd') or 'current dir'}",
                "git_pull": f"git pull from {tool_input.get('remote', 'origin')} in {tool_input.get('cwd') or 'current dir'}",
                "git_branch": f"git branch {'create ' + str(tool_input.get('create')) if tool_input.get('create') else 'checkout ' + str(tool_input.get('checkout'))} in {tool_input.get('cwd') or 'current dir'}",
            }[name]
            if not await _request_approval(f"Nancy wants to: {description}", timeout=120.0):
                return {"success": False, "error": "User did not approve this git operation."}
        if name == "git_status":
            return await git_tool.git_status(tool_input.get("cwd"))
        if name == "git_diff":
            return await git_tool.git_diff(tool_input.get("cwd"), bool(tool_input.get("staged", False)), tool_input.get("path"))
        if name == "git_log":
            return await git_tool.git_log(tool_input.get("cwd"), int(tool_input.get("count", 15)))
        if name == "git_branch":
            return await git_tool.git_branch(tool_input.get("cwd"), tool_input.get("create"), tool_input.get("checkout"))
        if name == "git_commit":
            return await git_tool.git_commit(str(tool_input.get("message", "")), tool_input.get("cwd"), tool_input.get("paths"))
        if name == "git_push":
            return await git_tool.git_push(tool_input.get("cwd"), tool_input.get("remote", "origin"), tool_input.get("branch"))
        if name == "git_pull":
            return await git_tool.git_pull(tool_input.get("cwd"), tool_input.get("remote", "origin"), tool_input.get("branch"))

    if name in ("docker_ps", "docker_logs", "docker_images", "docker_build", "docker_compose_up", "docker_compose_down", "docker_restart"):
        is_mutating = name in ("docker_build", "docker_compose_up", "docker_compose_down", "docker_restart")
        if is_mutating and (not arm_switch.is_armed() or _voice_mismatch()):
            description = {
                "docker_build": f"docker build {tool_input.get('context')} as {tool_input.get('tag')}",
                "docker_compose_up": f"docker compose up in {tool_input.get('cwd')}",
                "docker_compose_down": f"docker compose down in {tool_input.get('cwd')}",
                "docker_restart": f"docker restart {tool_input.get('container')}",
            }[name]
            if not await _request_approval(f"Nancy wants to: {description}", timeout=120.0):
                return {"success": False, "error": "User did not approve this Docker operation."}
        if name == "docker_ps":
            return await docker_tool.docker_ps(bool(tool_input.get("all_containers", False)))
        if name == "docker_logs":
            return await docker_tool.docker_logs(tool_input.get("container", ""), int(tool_input.get("tail", 100)))
        if name == "docker_images":
            return await docker_tool.docker_images()
        if name == "docker_build":
            return await docker_tool.docker_build(tool_input.get("context", ""), tool_input.get("tag", ""), tool_input.get("dockerfile"))
        if name == "docker_compose_up":
            return await docker_tool.docker_compose_up(tool_input.get("cwd", ""), tool_input.get("service"))
        if name == "docker_compose_down":
            return await docker_tool.docker_compose_down(tool_input.get("cwd", ""))
        if name == "docker_restart":
            return await docker_tool.docker_restart(tool_input.get("container", ""))

    if name in ("deploy_server", "restart_background_process", "stop_background_process", "list_background_processes"):
        if name != "list_background_processes" and (not arm_switch.is_armed() or _voice_mismatch()):
            description = {
                "deploy_server": f"start a background process {tool_input.get('name')!r}: {tool_input.get('command')}",
                "restart_background_process": f"restart background process {tool_input.get('name')!r}",
                "stop_background_process": f"stop background process {tool_input.get('name')!r}",
            }[name]
            if not await _request_approval(f"Nancy wants to: {description}", timeout=120.0):
                return {"success": False, "error": "User did not approve this process operation."}
        if name == "deploy_server":
            return await process_control.deploy_server(tool_input.get("name", ""), tool_input.get("command", ""), tool_input.get("cwd"))
        if name == "restart_background_process":
            return await process_control.restart_background_process(tool_input.get("name", ""))
        if name == "stop_background_process":
            return await process_control.stop_background_process(tool_input.get("name", ""))
        if name == "list_background_processes":
            return await process_control.list_background_processes()

    resolved_write_path: Optional[Path] = None
    if name == "write_file":
        resolved_write_path = _resolve_write_path(tool_input["path"], tool_input["content"], user_hint)

    if name in _FILE_WRITE_TOOLS and (not arm_switch.is_armed() or _voice_mismatch()):
        description = {
            "write_file": f"Write to file: {resolved_write_path}",
            "edit_file": (
                f"Edit file: {tool_input.get('path')}\n\n"
                f"- {tool_input.get('old_string', '')[:200]!r}\n"
                f"+ {tool_input.get('new_string', '')[:200]!r}"
            ),
            "multi_edit_file": (
                f"Apply {len(tool_input.get('edits', []))} edits to file: {tool_input.get('path')}\n\n"
                + "\n".join(
                    f"- {e.get('old_string', '')[:120]!r}\n+ {e.get('new_string', '')[:120]!r}"
                    for e in tool_input.get("edits", [])[:5]
                )
            ),
            "edit_notebook_cell": (
                f"{tool_input.get('edit_mode', 'replace').capitalize()} cell {tool_input.get('cell_index')} "
                f"in notebook: {tool_input.get('path')}\n\n{tool_input.get('new_source', '')[:200]!r}"
            ),
            "delete_file": f"Delete: {tool_input.get('path')}",
            "move_file": f"Move {tool_input.get('src')} -> {tool_input.get('dst')}",
        }[name]
        if name in ("write_file", "edit_file"):
            lint_findings = security_lint.lint_content(tool_input.get("content") or tool_input.get("new_string", ""))
            description += security_lint.format_findings(lint_findings)
        elif name == "multi_edit_file":
            lint_findings = security_lint.lint_content(
                "\n".join(e.get("new_string", "") for e in tool_input.get("edits", []))
            )
            description += security_lint.format_findings(lint_findings)
        elif name == "edit_notebook_cell":
            lint_findings = security_lint.lint_content(tool_input.get("new_source", ""))
            description += security_lint.format_findings(lint_findings)
        approved = await _request_approval(
            f"Nancy wants to: {description}", timeout=120.0
        )
        if not approved:
            return {"success": False, "error": "User did not approve this file operation."}

    if name == "read_file":
        result = file_access.read_file(tool_input["path"], tool_input.get("offset", 0), tool_input.get("limit"))
        if result.get("is_image") and result.get("image_base64"):
            result["_image_base64"] = result.pop("image_base64")
        return result
    if name == "list_directory":
        return file_access.list_directory(tool_input["path"])
    if name == "glob_files":
        return file_access.glob_files(tool_input.get("pattern", ""), tool_input.get("path", "."))
    if name == "search_files":
        return file_access.search_files(
            tool_input.get("pattern", ""), tool_input.get("path", "."),
            tool_input.get("glob", ""), tool_input.get("case_sensitive", False),
        )
    if name == "edit_file":
        path = str(tool_input["path"])
        await lifecycle_hooks.fire_hook("pre_write", {"path": path})
        result = file_access.edit_file(
            path, tool_input["old_string"], tool_input["new_string"], tool_input.get("replace_all", False),
        )
        evidence_ledger.record_evidence("edit_file", path, result.get("success", False))
        if result.get("success"):
            _attach_python_syntax_check(result, path)
            try:
                diag_result = await asyncio.wait_for(
                    lsp_client.diagnostics_before_after_write(path, result.get("old_content"), result.get("new_content")),
                    timeout=15.0,
                )
                if diag_result.get("success") and not diag_result.get("unsupported") and diag_result.get("new_diagnostics"):
                    result["new_diagnostics"] = diag_result["new_diagnostics"]
            except Exception as e:
                logger.info("lsp_client diagnostics check skipped: %s", e)
            # Don't balloon the model's context with the whole before/after
            # file on every edit -- the diagnostics check above already used it.
            result.pop("old_content", None)
            result.pop("new_content", None)
        return result
    if name == "multi_edit_file":
        path = str(tool_input["path"])
        await lifecycle_hooks.fire_hook("pre_write", {"path": path})
        result = file_access.multi_edit_file(path, tool_input.get("edits", []))
        evidence_ledger.record_evidence("multi_edit_file", path, result.get("success", False))
        if result.get("success"):
            _attach_python_syntax_check(result, path)
            try:
                diag_result = await asyncio.wait_for(
                    lsp_client.diagnostics_before_after_write(path, result.get("old_content"), result.get("new_content")),
                    timeout=15.0,
                )
                if diag_result.get("success") and not diag_result.get("unsupported") and diag_result.get("new_diagnostics"):
                    result["new_diagnostics"] = diag_result["new_diagnostics"]
            except Exception as e:
                logger.info("lsp_client diagnostics check skipped: %s", e)
            result.pop("old_content", None)
            result.pop("new_content", None)
        return result
    if name == "read_notebook":
        return notebook_tools.read_notebook(tool_input["path"])
    if name == "edit_notebook_cell":
        path = str(tool_input["path"])
        await lifecycle_hooks.fire_hook("pre_write", {"path": path})
        result = notebook_tools.edit_notebook_cell(
            path, tool_input["cell_index"], tool_input.get("new_source", ""),
            tool_input.get("cell_type"), tool_input.get("edit_mode", "replace"),
        )
        evidence_ledger.record_evidence("edit_notebook_cell", path, result.get("success", False))
        return result
    if name == "write_file":
        await lifecycle_hooks.fire_hook("pre_write", {"path": str(resolved_write_path)})
        old_content_result = file_access.read_file(str(resolved_write_path))
        old_content = old_content_result.get("content") if old_content_result.get("success") else None
        result = file_access.write_file(str(resolved_write_path), tool_input["content"])
        evidence_ledger.record_evidence("write_file", str(resolved_write_path), result.get("success", False))
        if result.get("success"):
            _attach_python_syntax_check(result, str(resolved_write_path))
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
    approved = await _request_approval(
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


def _build_chat_parts(user_text: str, history_text: str, channel: str = "voice") -> tuple[str, str, str]:
    """Shared prompt assembly, split into (static_system, dynamic_context,
    user_turn) so backends that support a real system role can use it:

    - static_system: _system_prompt_for_channel(channel) -- byte-identical
      every turn FOR A GIVEN CHANNEL, which is exactly what makes Anthropic
      prompt caching effective (the cache key is a prefix match; see
      llm.py's _anthropic_system_blocks) -- caching still applies per-channel,
      just as two distinct cached prefixes instead of one.
    - dynamic_context: live system/UI context, matched skills, detected
      links, retrieved memories -- changes turn to turn, still system-role
      material rather than something the "user said".
    - user_turn: conversation history + this turn's user text.

    _build_chat_prompt() below joins these back into the exact single-string
    prompt the OpenAI-compat fallbacks and non-Claude backends always used,
    so the two shapes can't silently drift."""
    skills_block = skill_loader.build_skill_prompt_block(user_text)
    links_block = ""
    detected_urls = extract_urls(user_text)
    if detected_urls:
        links_block = "Links detected in the user's message (already SSRF-checked, safe to fetch_url if relevant): " + ", ".join(detected_urls)
    # Real retrieval-augmentation from memory_manager.graph -- semantically
    # relevant past memories, not just this turn's own history_text (which
    # is only the last several messages of THIS conversation). Empty string
    # (no-op) until the graph actually has something relevant to surface.
    try:
        memory_block = _active_memory_manager().get_memory_context_string(user_text)
    except Exception as e:
        logger.debug("Memory context lookup failed, continuing without it: %s", e)
        memory_block = ""
    dynamic_context = (
        f"{_live_datetime_prompt_block()}\n\n{_live_system_context()}\n\n{_live_context_bridge_context()}\n\n"
        f"{skills_block}\n\n{links_block}\n\n{memory_block}"
    )
    user_turn = f"{history_text}\nuser: {user_text}\nassistant:"
    return _system_prompt_for_channel(channel), dynamic_context, user_turn


def _chat_system_blocks(static_system: str, dynamic_context: str) -> list:
    """Anthropic system blocks: cacheable static persona first (llm.py adds
    the actual cache_control marker), per-turn dynamic context second."""
    blocks = [{"type": "text", "text": static_system}]
    if dynamic_context.strip():
        blocks.append({"type": "text", "text": dynamic_context})
    return blocks


def _build_chat_prompt(user_text: str, history_text: str, channel: str = "voice") -> str:
    """Single-string prompt for backends without a usable system role --
    identical content to _build_chat_parts, just joined."""
    static_system, dynamic_context, user_turn = _build_chat_parts(user_text, history_text, channel)
    return f"{static_system}\n\n{dynamic_context}\n\n{user_turn}"


async def _generate_response_via_hierarchy(user_text: str, channel: str = "voice") -> tuple[str, dict]:
    """Thin wrapper around _generate_response_via_hierarchy_impl that adds
    real memory population -- this function (not the impl) is the single
    chokepoint every real caller actually uses (WS chat/voice turns,
    Telegram, background tasks, cron/webhook skills), so this is the one
    place that guarantees the memory graph actually grows from real usage.
    Previously, extract_memories_from_conversation()/learn_from_response()
    were only ever called from the legacy /chat REST endpoint, which the
    real frontend never uses (it goes over the WebSocket) -- confirmed live
    by "Loaded 0 memories from disk" on every single startup this session
    despite hours of real conversation. Uses extract_memories_from_message
    (works directly off this turn's real text) rather than the original
    extract_memories_from_conversation (depends on nancy_brain.context,
    which the real path never populates either)."""
    global _last_real_activity_at
    _last_real_activity_at = _time.time()
    response_text, debug = await _generate_response_via_hierarchy_impl(user_text, channel)
    try:
        active_manager = _active_memory_manager()
        active_manager.extract_memories_from_message(user_text, role="user")
        active_manager.learn_from_response(user_text, response_text)
    except Exception:
        logger.exception("Memory extraction/learning failed for this turn")
    # Verbatim FTS5 log -- same chokepoint reasoning as the memory graph
    # above: every real caller goes through here, so every real turn is
    # findable by exact text later (search_conversation_history tool).
    conversation_log.log_turn("user", user_text)
    conversation_log.log_turn("assistant", response_text)
    # Solve → distill → reuse (Hermes-style): a turn that took several real
    # tool calls to solve is a candidate for becoming a named, reusable
    # skill. Fire-and-forget so distillation never adds latency to the
    # actual reply; the human approval gate lives inside.
    try:
        if len(debug.get("tool_trace") or []) >= _DISTILL_MIN_TOOL_CALLS:
            asyncio.create_task(_maybe_distill_skill(user_text, response_text, debug["tool_trace"]))
    except Exception:
        logger.exception("Skill-distillation scheduling failed (reply unaffected)")
    return response_text, debug


# ---------------------------------------------------------------------------
# Skill distillation -- the solve → distill → reuse loop (borrowed from
# Hermes Agent's procedural-memory design). When a chat turn genuinely
# required a multi-step tool procedure, ask Claude to distill the solution
# path into a SKILL.md-shaped procedure, get real Telegram approval, and
# save it via skill_loader.save_skill so match_skills() injects it into
# future prompts. Guardrails: never fires when an existing skill already
# matched this request (that skill was already injected -- re-distilling it
# would just accumulate near-duplicates), never overwrites an existing
# skill, and always goes through the same _request_approval chokepoint as
# every other sensitive action.
# ---------------------------------------------------------------------------
_DISTILL_MIN_TOOL_CALLS = 2

_DISTILL_PROMPT = """A user request was just solved using a sequence of real tool calls. Decide whether this solution path is a REUSABLE PROCEDURE worth saving as a named skill, i.e. the same kind of request is likely to recur and the tool sequence is not trivially obvious.

User request: {user_text}

Tool calls made (in order): {tool_trace}

Final answer given (truncated): {response_text}

If it is NOT worth saving (one-off request, trivial single-purpose lookup, or too situation-specific), respond with exactly: NO

Otherwise respond with ONLY a JSON object (no prose, no markdown fences):
{{"name": "short-kebab-case-name", "description": "one sentence: what this skill does", "trigger_keywords": ["3-6", "lowercase", "keywords"], "instructions": "Step-by-step procedure in imperative Markdown, referencing the tools by name, generalized (no user-specific values hardcoded)"}}"""


async def _maybe_distill_skill(user_text: str, response_text: str, tool_trace: List[str]) -> None:
    try:
        # An existing skill already covered this request -- don't distill a
        # near-duplicate of it. (Keyword scan directly rather than
        # match_skills(), which would wrongly bump the usage telemetry for
        # a match that never got injected into any prompt.)
        text_lower = user_text.lower()
        if any(kw in text_lower for s in skill_loader.list_skills() for kw in s.trigger_keywords):
            return
        if not os.getenv("ANTHROPIC_API_KEY"):
            return
        claude = AnthropicLLM()
        raw = await asyncio.wait_for(
            claude.generate(
                _DISTILL_PROMPT.format(
                    user_text=user_text[:600],
                    tool_trace="; ".join(tool_trace)[:1200],
                    response_text=response_text[:600],
                ),
                max_tokens=800,
            ),
            timeout=30.0,
        )
        raw = raw.strip()
        if raw.upper().startswith("NO"):
            return
        # Tolerate markdown fences / stray prose around the JSON object.
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return
        try:
            spec = json.loads(match.group(0))
        except (json.JSONDecodeError, ValueError):
            return
        name = str(spec.get("name", "")).strip()
        instructions = str(spec.get("instructions", "")).strip()
        keywords = spec.get("trigger_keywords") or []
        if not name or not instructions or not isinstance(keywords, list):
            return
        if skill_loader.get_skill(name):
            return
        approved = await _request_approval(
            f"🧠 Billion wants to save a new skill distilled from the last task:\n\n"
            f"Name: {name}\nDescription: {spec.get('description', '')}\n"
            f"Triggers: {', '.join(str(k) for k in keywords[:6])}\n\n"
            f"Procedure:\n{instructions[:700]}\n\nSave this skill?",
            timeout=300.0,
        )
        if not approved:
            logger.info("Skill distillation for '%s' not approved, discarding", name)
            return
        saved = skill_loader.save_skill(
            name=name,
            description=str(spec.get("description", "")),
            trigger_keywords=[str(k) for k in keywords],
            instructions=instructions,
        )
        if saved:
            await telegram_notifier.send(
                f"✅ Skill '{saved.name}' saved -- Billion will follow it automatically "
                f"when a matching request comes in."
            )
    except asyncio.TimeoutError:
        logger.info("Skill distillation LLM call timed out (reply was unaffected)")
    except Exception:
        logger.exception("Skill distillation failed (reply was unaffected)")


async def _generate_response_via_hierarchy_impl(user_text: str, channel: str = "voice") -> tuple[str, dict]:
    """Route a chat message to Claude's real tool-use loop when it clearly
    wants a real action, to a real specialized agent when the text clearly
    matches one of the 29 registered domains, or otherwise to the
    general-purpose LLM.

    Tool-use is checked BEFORE specialized-agent routing -- it used to be the
    other way around, which meant a message like "list the files in the
    current directory" (containing "file", routing to file_management) never
    reached Claude's real list_directory tool at all: file_management's
    process_task only recognizes specific structured task types ("list",
    "create", "read", ...), not the generic {"type": "query", ...} payload
    this function used to send unconditionally, so it fell through to
    _general_file_overview -- a bare LLM guess with no real filesystem
    access, dressed up as a successful response (confirmed live: a real
    "list the files" request got routed here, "succeeded", and returned a
    plain-text non-answer instead of an actual directory listing). Several
    other specialized agents have the exact same generic-query fallback
    shape; reordering these two checks fixes it for all of them at once
    instead of special-casing file_management. Domain-expertise questions
    that don't ask for a real action (astrophysics, quantum reasoning, etc.)
    never match _WANTS_TOOLS_RE, so they still route to their specialist
    agent exactly as before.

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
    static_system, dynamic_context, user_turn = _build_chat_parts(user_text, history_text, channel)
    # Single-string shape for backends without a usable system role
    # (OpenAI-compat tool fallbacks, plain-chat fallback chain) -- same
    # content, just joined.
    prompt = f"{static_system}\n\n{dynamic_context}\n\n{user_turn}"

    # Real tool-use, with a real multi-backend fallback chain. Claude is
    # tried first (richest: vision support in tool results, native
    # structured tool_use) -- but confirmed live this session that when
    # Anthropic alone is unavailable, every real tool call (file access,
    # terminal, canvas, ...) used to fail and silently fall all the way
    # through to a tool-less plain-chat guess, even though other configured
    # backends could have handled it. Each round-trip costs real latency
    # (up to 5 sequential calls per backend even when no tool ends up being
    # called), which is why this only runs when the message plausibly needs
    # a tool at all -- not for every message the way it originally did.
    if _wants_tools(user_text) or (_ALWAYS_ENGAGE_TOOLS and not _is_pure_smalltalk(user_text)):
        async def _file_tool_executor(name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
            # Binds this turn's real user_text in as a write_file extension
            # hint -- see _explicit_language_hint -- without changing the
            # tool_executor(name, input) contract generate_with_tools calls.
            return await _execute_file_tool(name, tool_input, user_hint=user_text)

        all_tools = _all_chat_tools()

        # Real per-turn tool trace -- which tools ran, with what inputs
        # (truncated). Feeds the solve → distill → reuse skill loop (see
        # _maybe_distill_skill): a turn that took several real tool calls
        # to solve is a candidate for becoming a named, reusable skill.
        tool_trace: List[str] = []

        async def _traced_tool_progress(name: str, tool_input: Dict[str, Any]) -> None:
            try:
                tool_trace.append(f"{name}({json.dumps(tool_input, default=str)[:200]})")
            except Exception:
                tool_trace.append(name)
            await _broadcast_tool_progress(name, tool_input)

        # A real screenshot/canvas image a tool produces used to only ever
        # be shown to the model internally -- the human never actually saw
        # it in either the web UI or Telegram. Collected here so both
        # channels can push it out for real (see _run_chat_turn and
        # _telegram_chat_handler).
        captured_images: List[bytes] = []

        # RESPECT THE USER'S PICKED PRIMARY (/model, /llm/primary): if the
        # live chain's front backend is one of the OpenAI-compat tool-capable
        # providers (Groq/OpenRouter/OpenCode), it gets first crack at the
        # tool loop and Claude becomes the fallback -- previously Claude was
        # hardcoded first whenever ANTHROPIC_API_KEY existed, which silently
        # ignored an explicit model selection for every tool-using turn.
        _primary_cls = _tool_backend_class(
            llm_backend.backends[0].__class__.__name__ if llm_backend.backends else ""
        )
        _compat_classes = {t[4] for t in TOOL_FALLBACK_BACKENDS}
        claude_first = _primary_cls not in _compat_classes
        ordered_fallbacks = sorted(
            TOOL_FALLBACK_BACKENDS,
            key=lambda t: 0 if t[4] == _primary_cls else 1,
        )
        logger.info(
            "Tool loop order: %s (primary=%s)",
            "Claude first" if claude_first else f"{_primary_cls} first",
            _primary_cls or "none",
        )

        async def _try_claude_tools():
            claude = AnthropicLLM()
            resp = await asyncio.wait_for(
                claude.generate_with_tools(
                    user_turn, all_tools, _file_tool_executor, max_tokens=1024,
                    on_tool_image=captured_images.append,
                    on_tool_call=_traced_tool_progress,
                    # Real system role + prompt caching: the static
                    # persona prompt and the tool schemas are cached
                    # across every round of this loop (and across
                    # turns), instead of re-billed at full input price
                    # inside a single 45s-budget call.
                    system=_chat_system_blocks(static_system, dynamic_context),
                ),
                timeout=45.0,
            )
            return _enforce_sir(resp), {"tool_use": True, "tool_backend": "AnthropicLLM", "images": captured_images, "tool_trace": tool_trace}

        if claude_first and os.getenv("ANTHROPIC_API_KEY"):
            try:
                return await _try_claude_tools()
            except Exception as e:
                logger.warning("Claude tool-use path failed, trying next tool-capable backend: %s", e)

        fallback_tools = _trim_tools_for_fallback(all_tools)
        # The compat providers can't be handed the full ~35-tool schema list
        # (it blows Groq's per-minute token cap outright), so they get a
        # trimmed set. The catch: _WANTS_TOOLS_RE still routes "what's on my
        # calendar" into this loop, the picked model has no calendar tool, and
        # it answers from imagination -- reported to the UI as a real tool turn.
        # If a compat backend finishes a tool-wanting turn WITHOUT calling a
        # single tool, and tools were withheld from it, we don't trust the
        # answer: Claude gets the turn with the full arsenal.
        _withheld = {t.get("name") for t in all_tools} - {t.get("name") for t in fallback_tools}
        _claude_available = bool(os.getenv("ANTHROPIC_API_KEY"))
        for env_var, base_url, model_env, model_default, label in ordered_fallbacks:
            api_key = _tool_backend_key(env_var)
            if not api_key:
                continue
            try:
                resp = await asyncio.wait_for(
                    generate_with_tools_openai_compat(
                        _tool_backend_base_url(env_var, base_url), api_key,
                        os.getenv(model_env, model_default),
                        prompt, fallback_tools, _file_tool_executor,
                        max_tokens=1024, provider_label=label,
                        on_tool_image=captured_images.append,
                        on_tool_call=_traced_tool_progress,
                    ),
                    timeout=45.0,
                )
                if _withheld and not tool_trace and _claude_available:
                    logger.info(
                        "%s answered a tool-wanting turn without calling any tool, and %d tools "
                        "were withheld from it -- handing this turn to Claude rather than trusting it",
                        label, len(_withheld),
                    )
                    try:
                        return await _try_claude_tools()
                    except Exception as e:
                        logger.warning(
                            "Claude could not take over the turn (%s); using %s's answer", e, label
                        )
                return _enforce_sir(resp), {"tool_use": True, "tool_backend": label, "images": captured_images, "tool_trace": tool_trace}
            except Exception as e:
                logger.warning("%s tool-use path failed, trying next tool-capable backend: %s", label, e)

        # Non-Claude primary exhausted its compat providers -- Claude is
        # still the strongest tool runner, so it stays as the last resort.
        if not claude_first and os.getenv("ANTHROPIC_API_KEY"):
            try:
                return await _try_claude_tools()
            except Exception as e:
                logger.warning("Claude last-resort tool-use path failed too: %s", e)

    if agent_service.is_ready():
        try:
            from agents.agent_service import _auto_route
            routed_key = _auto_route(user_text)
        except Exception:
            routed_key = None

        if routed_key:
            try:
                # See agents/base.py's _current_conversation_context: the
                # "context" key in task_data below is passed through, but
                # confirmed live that individual agents' generic/_llm_answer
                # fallbacks never actually read it -- a message that
                # happened to match this agent's routing keywords got
                # answered in total isolation from the conversation so far,
                # reading as an abrupt topic change. The ContextVar reaches
                # _llm_answer directly without needing every specialized
                # agent file to thread task_data["context"] through itself.
                from agents.base import _current_conversation_context
                _current_conversation_context.set(history_text)
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

    try:
        # Telegram gets real headroom for the "4 well-developed paragraphs"
        # depth its style addendum asks for. Voice/web used to cap at 512,
        # sized for short spoken replies -- but the voice style prompt
        # explicitly asks for real depth on genuine depth-worthy questions
        # (not just short casual replies), and 512 tokens confirmed live cut
        # a real, in-progress, substantive answer off mid-sentence ("...not
        # even neutron degeneracy pressure can" -- nothing after it). 900
        # gives a real depth answer room to actually finish while still
        # being far short of Telegram's budget; a genuinely short/casual
        # reply stays short on its own from the prompt's own calibration,
        # not because the ceiling forces it to.
        max_tokens = 1600 if channel == "telegram" else 1400
        resp = await asyncio.wait_for(
            llm_backend.generate(prompt, max_tokens=max_tokens, temperature=0.7),
            timeout=30.0,
        )
        resp = _enforce_sir(resp)
    except Exception as llm_e:
        resp = f"I'm having trouble processing that right now, Sir. ({llm_e})"
    return resp, {}


# ---------------------------------------------------------------------------
# Streaming chat turn -- real token streaming (Claude) accumulates the full
# reply text (agent-routed and tool-use replies arrive as one block anyway),
# then synthesizes it in a SMALL number of multi-sentence batches rather than
# either extreme: one call per sentence (confirmed live as the cause of a
# fresh ~15-20s dead-air gap before EVERY sentence on this CPU-only NeuTTS
# hardware, which read as broken/out-of-sync mid-reply), or one call for the
# whole reply (tried first -- confirmed live to blow straight through the
# WebSocket's 10MB frame limit for a real ~2400-char detailed answer, whose
# ~195s of 24kHz WAV audio base64-encodes to ~12MB and drops the connection
# outright). Batching a few sentences per call keeps the per-call audio small
# enough to always fit in one frame while cutting the number of inter-chunk
# gaps to 2-4 for a long reply instead of 6-10.
# ---------------------------------------------------------------------------
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
# Sized from the actual failure: a 2437-char reply's audio exceeded the 10MB
# WS frame limit (base64), i.e. over ~3080 bytes of raw 24kHz/16-bit WAV per
# source character. 1500 chars stays comfortably under that limit (~6MB
# base64 even at that same density) while meaning most real replies --
# including a genuinely detailed multi-paragraph one -- still fit in a
# single batch, matching the smooth one-shot playback the user confirmed
# they preferred; only unusually long replies ever split into more than one.
_TTS_BATCH_TARGET_CHARS = 1500


def _batch_sentences_for_tts(text: str, target_chars: int = _TTS_BATCH_TARGET_CHARS) -> list[str]:
    """Groups sentences into batches up to ~target_chars each. A short reply
    (the common case) naturally becomes a single batch, unchanged from
    speaking it in one shot; a long detailed reply becomes a handful of
    batches instead of one-per-sentence or one giant blob."""
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]
    if not sentences:
        return []
    batches: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if current and len(candidate) > target_chars:
            batches.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        batches.append(current)
    return batches


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

    # Either condition below hands off to _generate_response_via_hierarchy,
    # which internally tries Claude's real tool-use loop before specialized-
    # agent routing (see its docstring) -- so it doesn't matter here which
    # condition fired, only whether either did. A message wanting a real
    # action (matches _WANTS_TOOLS_RE) or matching a specialist domain
    # (agent_service auto-route) both need that non-streaming path; only
    # genuinely plain conversational text falls through to direct streaming
    # below.
    routed_key = None
    if agent_service.is_ready():
        try:
            from agents.agent_service import _auto_route
            routed_key = _auto_route(user_text)
        except Exception:
            routed_key = None
    wants_tools = _any_tool_backend_configured() and (
        _wants_tools(user_text) or (_ALWAYS_ENGAGE_TOOLS and not _is_pure_smalltalk(user_text))
    )

    if routed_key or wants_tools:
        text, debug = await _generate_response_via_hierarchy(user_text)
        yield {"kind": "delta", "text": text}
        yield {"kind": "meta", "debug": debug}
        return

    # Streaming is Claude-only (other backends don't stream), but ONLY when
    # Claude is actually the user's live primary -- if /model picked another
    # provider, fall through to the non-streaming chain below, which starts
    # from that picked primary instead of silently overriding it.
    _stream_primary = llm_backend.backends[0].__class__.__name__ if llm_backend.backends else ""
    if os.getenv("ANTHROPIC_API_KEY") and _stream_primary in ("", "AnthropicLLM"):
        static_system, dynamic_context, user_turn = _build_chat_parts(user_text, history_text)
        try:
            claude = AnthropicLLM()
            got_any = False
            full_text = ""
            async for delta in claude.generate_stream(
                user_turn, max_tokens=1400, temperature=0.7,
                system=_chat_system_blocks(static_system, dynamic_context),
            ):
                got_any = True
                full_text += delta
                yield {"kind": "delta", "text": delta}
            if got_any:
                yield {"kind": "meta", "debug": {"streamed": True}}
                # Real memory population for the plain-conversational path too
                # -- this is the MAJORITY of real turns (anything that didn't
                # need a tool or specialist agent), and without this it was
                # the single biggest reason the memory graph stayed empty:
                # only tool-use/agent-routed turns ever reached
                # _generate_response_via_hierarchy's wrapper.
                try:
                    active_manager = _active_memory_manager()
                    active_manager.extract_memories_from_message(user_text, role="user")
                    active_manager.learn_from_response(user_text, full_text)
                except Exception:
                    logger.exception("Memory extraction/learning failed for this streamed turn")
                # Same verbatim FTS5 log as the wrapper path -- streamed
                # turns bypass _generate_response_via_hierarchy entirely.
                conversation_log.log_turn("user", user_text)
                conversation_log.log_turn("assistant", full_text)
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
    # _last_real_activity_at is otherwise only set once, at the START of
    # _generate_response_via_hierarchy -- fine when a whole turn used to
    # finish in a couple seconds, but a real multi-sentence reply now
    # legitimately spends 15-20s of NeuTTS synthesis PER sentence, so a
    # 5-6-sentence reply already runs past the proactive/training loops'
    # 90s quiet window while still genuinely mid-turn. Without refreshing
    # here, those loops see a stale timestamp and conclude the user's gone
    # quiet, firing a real background LLM/agent cycle that competes for the
    # exact same CPU this synthesis call is still using.
    global _last_real_activity_at
    _last_real_activity_at = _time.time()
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
                # The sentence this chunk's audio actually contains -- the
                # frontend uses this to compute which words in the full
                # transcript this specific chunk covers, so the live lyrics
                # highlight can be timed against THIS chunk's real audio
                # duration instead of a single whole-reply estimate that
                # starts counting before any audio has even begun playing.
                "text": text,
            }),
            websocket,
        )
    except Exception:
        pass  # connection likely gone; the outer turn will be cancelled/cleaned up


async def _push_reply_to_telegram(text: str, images: Optional[List[bytes]] = None) -> None:
    """Mirrors a real reply from the web/voice UI into Telegram, so the two
    conversations are genuinely the same conversation -- not two separate
    ones that happen to share memory. Best-effort and fire-and-forget from
    the caller's perspective: a failed Telegram push should never affect
    the channel that actually generated the reply."""
    try:
        await telegram_notifier.send(text)
        for image_bytes in (images or []):
            await telegram_notifier.send_document(image_bytes, filename="capture.png")
    except Exception as e:
        logger.warning("Failed to mirror reply to Telegram: %s", e)


def _update_alert_status(key: str, category: str, title: str, severity: str, detail: str) -> None:
    """The one place every real category-status update goes through --
    upserts alert_center's stored status, then fires the live WS broadcast
    as a background task so callers (loops, request handlers) never block
    on it."""
    status = alert_center.alert_center.set_status(
        key=key, category=category, title=title, severity=severity, detail=detail,
    )
    asyncio.create_task(_broadcast_alert_status(status))


async def _pulse_orb(color: str, reason: str = "") -> None:
    """Real-time transient orb pulse: 'yellow' the instant a real check/
    process starts running, 'green' when it completes cleanly, 'red' on an
    error or a genuine security/attack signal. Purely a live event -- the
    frontend (NancyOrb) owns the ~3s auto-revert timing itself, this just
    fires it. Broadcast to every connected tab, same as _broadcast_alert_status."""
    try:
        await manager.broadcast(json.dumps({"type": "orb_pulse", "color": color, "reason": reason}))
    except Exception as e:
        logger.warning("Failed to broadcast orb pulse: %s", e)


async def _broadcast_alert_status(status: "alert_center.CategoryStatus") -> None:
    """Pushes a real green/yellow/red category-status change to every
    connected web/voice UI session -- unlike _broadcast_reply_to_web's
    proactive-text path, this always reaches every open tab (not just an
    active continuous-conversation session), since a status dashboard should
    reflect reality the instant it changes, not only during a live chat."""
    try:
        await manager.broadcast(json.dumps({"type": "alert_status", "status": status.to_public_dict()}))
    except Exception as e:
        logger.warning("Failed to broadcast alert status: %s", e)


async def _broadcast_reply_to_web(text: str, images: Optional[List[bytes]] = None, *, source: str) -> None:
    """Mirrors a real reply from Telegram into every connected web/voice UI
    session, same reasoning as _push_reply_to_telegram in the other
    direction. Images go out as a separate real message (type: chat_image)
    the frontend renders inline in the transcript -- previously a real
    screenshot/canvas image a tool produced was never actually shown to the
    human in either channel, only fed to the model internally. `text` is
    optional (empty/falsy skips the agent_response broadcast entirely) --
    a Telegram location-query reply's real caption text was already
    broadcast once via the normal chat-reply path, so its image-only
    follow-up (see set_image_broadcaster) doesn't send it a second time."""
    for image_bytes in (images or []):
        try:
            await manager.broadcast_or_route(json.dumps({
                "type": "chat_image",
                "data": base64.b64encode(image_bytes).decode(),
                "source": source,
            }))
        except Exception as e:
            logger.warning("Failed to broadcast image to web clients: %s", e)
    if not text:
        return
    try:
        await manager.broadcast_or_route(json.dumps({
            "type": "agent_response",
            "data": text,
            "source": source,
            "turn_id": 0,
        }))
    except Exception as e:
        logger.warning("Failed to broadcast reply to web clients: %s", e)


async def _run_chat_turn(
    websocket: WebSocket, turn_id: int, user_text: str, voice_match: Optional[Dict[str, Any]] = None,
    speaker_profile_id: Optional[str] = None, turn_audio: Optional[Any] = None,
) -> None:
    """The actual per-message work, run as its own cancellable asyncio.Task
    (see ConnectionManager.start_turn) so a new message can supersede a slow
    one in progress instead of queuing behind it. voice_match is the real
    voice_id.verify() result for this turn's audio, computed by the WS
    handler before this task started (None if the turn was typed, or no
    voice profile is enrolled) -- stashed in a ContextVar so the generic
    tool-dispatch callback (_execute_file_tool) can read it without its
    signature needing to change. speaker_profile_id is the household member
    household_voice_id.identify_speaker() matched this turn's audio to (see
    _active_memory_manager); turn_audio is that same real decoded audio
    itself, so the enroll_profile_voice tool can use it directly -- same
    ContextVar-stashing reasoning for both."""
    _current_turn_ctx.set((websocket, turn_id))
    _current_voice_match.set(voice_match)
    _current_speaker_profile_id.set(speaker_profile_id)
    _current_turn_audio.set(turn_audio)
    await _history_add({"role": "user", "content": user_text})

    full_text = ""
    debug_payload: Dict[str, Any] = {}

    try:
        async for item in _generate_response_stream(user_text):
            if item["kind"] == "delta":
                full_text += item["text"]
            elif item["kind"] == "meta":
                debug_payload = item.get("debug", {})

        full_text = _enforce_sir(full_text.strip()) or "I'm not sure how to respond to that, Sir."

        await _history_add({"role": "assistant", "content": full_text})

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

        # Real conversation sync -- Telegram sees the same reply, including
        # any real image a tool call produced (previously only ever shown
        # to the model internally, never to a human in either channel).
        # Fire-and-forget: never let a Telegram hiccup delay or break the
        # reply already delivered above.
        asyncio.create_task(_push_reply_to_telegram(full_text, debug_payload.get("images")))

        # A small number of multi-sentence batches, not one call per sentence
        # and not one call for the whole reply -- see the module-level note
        # above _batch_sentences_for_tts for why both extremes were tried and
        # rejected. A short reply (most of them) collapses to a single batch,
        # i.e. behaves exactly like the one-shot design the user confirmed
        # played back smoothly; only a genuinely long reply ever splits into
        # more than one, and even then it's 2-4 gaps instead of 6-10.
        for i, batch in enumerate(_batch_sentences_for_tts(full_text)):
            await _synthesize_and_send_chunk(websocket, turn_id, i + 1, batch)

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


class LlmOrderRequest(BaseModel):
    #: Backend stems in desired priority order, e.g. ["groq","opencode","gemini"].
    order: List[str]


class AgentCollaborateRequest(BaseModel):
    # Both optional: with neither supplied the fleet selects its own
    # producer and reviewer by real semantic fit to the goal (see
    # agents/capability_index.py), which is what makes this a society
    # choosing its own collaborators rather than a caller wiring two
    # hardcoded keys together.
    goal: str
    producer: Optional[str] = None
    reviewer: Optional[str] = None
    rounds: int = 2
    timeout: float = 45.0

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
    # Real job chaining -- see cron_store.CronJob's own docstring on these
    # two fields for exactly how they interact.
    chain_to: List[str] = []
    chain_input_key: Optional[str] = None

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


@app.get("/persona/preview")
async def persona_preview():
    """Static representative greeting text for every persona, read straight
    off NancyGreeting.GREETINGS -- lets the Profiles page show what each
    persona actually sounds like before switching to it, instead of a bare
    name + first-letter badge with no indication of what's actually
    different about "nancy" vs "billion" vs "jarvis". Doesn't touch
    startup_coordinator's real active-persona state."""
    return {"success": True, "personas": NancyGreeting.GREETINGS}


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
    # text -- illustrative of the tone, not real data). meetings_today is
    # real Google Calendar data when providers/google_calendar.py is
    # configured (GOOGLE_CALENDAR_REFRESH_TOKEN etc.), and honestly empty --
    # never fabricated -- when it isn't. Every other field is best-effort:
    # any source that errors has nothing to report is just omitted, not faked.
    # The three I/O-bound sections below (calendar, per-pair forex, self-
    # improvement status) used to run one after another -- confirmed live,
    # that sequential chain was the real reason the whole "personalized
    # greeting" endpoint could take 25-30+ seconds, well past the frontend's
    # own abort timer for it, meaning the user essentially never actually
    # heard the real personalized greeting and always got the generic
    # fallback line instead. Each section already degrades independently on
    # its own failure (empty result, not raised), so running them
    # concurrently via asyncio.gather changes total wall-clock time from
    # "sum of every section" to "the slowest single section" with no change
    # in what gets reported.
    async def _get_meetings() -> list:
        if not google_calendar.is_configured():
            return []
        try:
            now = datetime.now(timezone.utc)
            end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0)
            cal_result = await google_calendar.list_events(
                time_min=now.isoformat(), time_max=end_of_day.isoformat(), max_results=10,
            )
            out = []
            if cal_result.get("success"):
                for event in cal_result.get("events", []):
                    start = event.get("start") or ""
                    time_part = start[11:16] if len(start) >= 16 else start
                    out.append(f"{event.get('summary', 'Untitled event')} at {time_part}")
            return out
        except Exception as e:
            logger.debug("Greeting: calendar data unavailable: %s", e)
            return []

    async def _get_one_pair_alert(pair: str) -> Optional[str]:
        try:
            snapshot = await forex_aggregator.get_price(pair)
            if not snapshot:
                return None
            direction = "up" if snapshot.change_24h > 0 else "down" if snapshot.change_24h < 0 else "flat"
            return f"{pair} is trading at {snapshot.price:.4f}, {direction} {abs(snapshot.change_24h):.2f}% on the day"
        except Exception as e:
            logger.debug("Greeting: market data unavailable for %s: %s", pair, e)
            return None

    async def _get_market_alerts() -> list:
        # Real pairs the user actually trades/watches --
        # trading_manager.watched_pairs (explicit) unioned with whatever
        # pairs appear in real trade history, never a hardcoded pair list.
        # Confirmed live: this used to always report EUR/USD and GBP/USD
        # regardless of what the user actually trades.
        pairs = trading_manager.get_relevant_pairs()
        results = await asyncio.gather(*(_get_one_pair_alert(p) for p in pairs))
        return [r for r in results if r]

    async def _get_tasks_due() -> list:
        try:
            si_result = await agent_service.run("self_improvement", {"type": "status"}, timeout=5.0)
            pending = si_result.get("pending_proposals", 0)
            if pending:
                return [f"{pending} self-improvement proposal{'s' if pending != 1 else ''} awaiting your approval"]
            return []
        except Exception as e:
            logger.debug("Greeting: self-improvement status unavailable: %s", e)
            return []

    meetings_today, market_alerts, tasks_due = await asyncio.gather(
        _get_meetings(), _get_market_alerts(), _get_tasks_due(),
    )

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
        meetings_today=meetings_today,
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
    live forex rates, memory/projects, open trades, pending self-improvement
    proposals, and today's real Google Calendar events when
    providers/google_calendar.py is configured. build_status is still
    honestly omitted (no CI integration exists) rather than invented.

    Optional request body fields override/extend the real-data context.
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

    # Nancy actually SAYS this out loud (see page.tsx's boot flow) -- without
    # recording it as a real assistant turn, the very next thing the user
    # says arrives with no record that Nancy ever spoke, let alone asked
    # anything. Confirmed live: the greeting often ends on its own question
    # ("Shall I run through the task highlights first?"), and replying "yes"
    # to it got a context-free non-sequitur back instead of Nancy actually
    # running through the highlights, because _history_to_text() (what every
    # chat prompt is built from) had zero record this greeting ever happened.
    greeting_text = startup_data.get("greeting")
    if greeting_text:
        await _history_add({"role": "assistant", "content": greeting_text})
        conversation_log.log_turn("assistant", greeting_text)

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


_CONTEXT_BRIDGE_STALE_S = 60.0


def get_live_context_snapshot() -> Dict[str, Any]:
    """Latest UI context, or {} once it has gone stale.

    The dashboard heartbeats /context every ~10s while it's actually open
    (see frontend app/page.tsx's context-bridge effect), so anything older
    than a minute means the dashboard is gone -- injecting e.g. a stale
    speaking=True from hours ago into the system prompt would be worse
    than no context at all.
    """
    snapshot = _context_bridge.snapshot()
    updated_at = snapshot.get("updated_at")
    if updated_at:
        try:
            age = (datetime.now() - datetime.fromisoformat(updated_at)).total_seconds()
            if age > _CONTEXT_BRIDGE_STALE_S:
                return {}
        except (ValueError, TypeError):
            return {}
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


@app.get("/memory/conversations/search")
async def search_conversation_history_rest(q: str, limit: int = 10):
    """Verbatim FTS5 search over every logged chat turn -- the REST face of
    the search_conversation_history chat tool (see conversation_log.py).
    Exact-text recall with snippets, distinct from the semantic
    /memory/search."""
    return {
        "success": True,
        "query": q,
        "results": conversation_log.search(q, limit=limit),
        "stats": conversation_log.stats(),
    }


@app.get("/memory/conversations")
async def get_conversation_history(limit: int = 30):
    """Real persisted conversation turns (MemoryType.CONVERSATION nodes --
    see memory/manager.py's process_conversation, which stores every real
    turn as it happens). Unlike the frontend Sessions page's in-tab `logs`
    (lost on refresh), this survives across reloads and browser tabs --
    it's the same memory graph every other memory-backed feature reads
    from. Embeddings are stripped before serialization (irrelevant to a
    UI, and large)."""
    nodes = memory_manager.graph.get_conversation_context(num_memories=limit)
    return {
        "success": True,
        "conversations": [
            {
                "id": n.id,
                "content": n.content,
                "source": n.metadata.get("source"),
                "timestamp": n.metadata.get("timestamp"),
                "created_at": n.created_at,
            }
            for n in nodes
        ],
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


@app.get("/memory/graph", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def get_memory_graph():
    """Full memory graph for the Memory Galaxy view -- every node Nancy has
    ever stored, plus its precomputed links (memory/graph.py's add_memory
    finds and links the most similar existing memories at write time, and
    lancedb_store.py's backend does the same -- both expose the same
    .nodes dict, so this works regardless of MEMORY_BACKEND). Embeddings
    are stripped -- large vectors, zero UI use."""
    nodes = memory_manager.graph.nodes
    return {
        "success": True,
        "nodes": [
            {
                "id": n.id,
                "type": n.type.value,
                "content": n.content,
                "metadata": n.metadata,
                "links": n.links,
                "importance": n.importance,
                "created_at": n.created_at,
            }
            for n in nodes.values()
        ],
    }


@app.post("/memory/graph/{node_id}/share", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def share_memory_node(node_id: str):
    """Real Telegram share for one memory-graph node -- the Galaxy view's
    'Share to Telegram' button. Sends the node's full content plus its
    real metadata (type, first/last mentioned, mention count), not just a
    bare content dump."""
    node = memory_manager.graph.nodes.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="No such memory node")
    mention_count = (node.metadata or {}).get("mention_count", 1)
    last_mentioned = (node.metadata or {}).get("last_mentioned_at", node.created_at)
    text = (
        f"🧠 Memory ({node.type.value}), Sir:\n\n{node.content}\n\n"
        f"First noted: {node.created_at}\nLast mentioned: {last_mentioned} ({mention_count}x)"
    )
    await telegram_notifier.send(text)
    return {"success": True}


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
        importance=0.8,
        # A real trade actually recorded by trading_manager -- this is an
        # observed system fact, not a model recollection.
        confidence=1.0, provenance="measured", source="trading_manager.record_trade",
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


@app.get("/trading/quotes")
async def get_trading_quotes(pairs: str = ""):
    """Real live quotes (forex_engine.ForexDataAggregator -- Frankfurter/ECB
    for fiat pairs, Yahoo COMEX futures for XAU/XAG) for either an explicit
    comma-separated `pairs` query param or, when omitted, the user's real
    watched/relevant pairs -- the same list the greeting/alerts use. Powers
    a live quotes ticker without requiring the caller to already know what
    to ask for. A pair that fails to fetch is simply omitted, never
    backfilled with a stale or invented price."""
    requested = [p.strip().upper() for p in pairs.split(",") if p.strip()] or trading_manager.get_relevant_pairs()
    results = await asyncio.gather(*(forex_aggregator.get_price(p) for p in requested), return_exceptions=True)
    quotes = []
    for pair, snap in zip(requested, results):
        if isinstance(snap, Exception) or snap is None:
            continue
        quotes.append({
            "pair": snap.pair, "price": snap.price, "bid": snap.bid, "ask": snap.ask,
            "change_24h": snap.change_24h, "high_24h": snap.high_24h, "low_24h": snap.low_24h,
            "timestamp": snap.timestamp,
        })
    return {"success": True, "quotes": quotes}


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
        # ONE brain for every surface: this REST path (terminal CLI, curl,
        # third-party callers) now goes through the exact same
        # _generate_response_via_hierarchy chokepoint the WebSocket chat,
        # voice turns, and Telegram already use -- full tool-use loop (file
        # access, terminal, browser, canvas -- each sensitive action still
        # Telegram-approval-gated), skill injection, agent routing, memory
        # growth, verbatim FTS5 logging, and skill distillation included.
        # Previously this endpoint ran its own reduced pipeline (plain LLM
        # call, no tools, separate memory calls), which meant a terminal
        # user talked to a measurably dumber Billion than the web UI did.
        response, _hier_debug = await _generate_response_via_hierarchy(text)

        # Record response in the brain's own context (kept from the old
        # path -- the intent classifier reads it for follow-up turns).
        nancy_brain.add_response(response)

        # Append this REST turn to the same shared history the WS path
        # maintains, so a terminal conversation and a web conversation are
        # ONE continuous conversation with follow-up context, not two
        # parallel amnesiacs.
        await _history_add({"role": "user", "content": text})
        await _history_add({"role": "assistant", "content": response})

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


@app.get("/health")
async def health():
    """Bare liveness ping -- exempt from auth (see _AUTH_EXEMPT_PATHS) since
    it carries no data, just 'the process is up and answering HTTP'. Distinct
    from /system/health, which is the real psutil metrics dump the dashboard
    polls. This is what package.json's `npm run health` and any external
    uptime/orchestration probe expects at the conventional /health path."""
    return {"success": True, "status": "healthy"}


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


@app.get("/system/alerts")
async def system_alerts():
    """Real green/yellow/red status per monitored category (alert_center.py)
    -- system resource health, primary LLM backend reliability, dependency
    vulnerabilities, and any active security-failure burst. Populated by
    _update_system_health_status/_update_dependency_vuln_status (self-healing
    and self-maintenance loops) and _record_security_failure (real
    auth/webhook-signature rejection points) -- this endpoint only reads
    the current stored state, it computes nothing itself."""
    return {
        "success": True,
        "overall_severity": alert_center.alert_center.overall_severity(),
        "statuses": [s.to_public_dict() for s in alert_center.alert_center.list()],
    }


class FlowRequest(BaseModel):
    name: str
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []


class FlowUpdateRequest(BaseModel):
    name: Optional[str] = None
    nodes: Optional[List[Dict[str, Any]]] = None
    edges: Optional[List[Dict[str, Any]]] = None


class FlowRunRequest(BaseModel):
    inputs: Dict[str, Any] = {}


@app.get("/flows", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def list_flows_endpoint():
    """Real saved flows (flow_engine.py) -- Billion's native, dependency-
    light equivalent of a Langflow project list."""
    return {"success": True, "flows": [f.to_public_dict() for f in flow_engine.flow_store.list()]}


@app.get("/flows/{flow_id}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def get_flow_endpoint(flow_id: str):
    flow = flow_engine.flow_store.get(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="No such flow.")
    return {"success": True, "flow": flow.to_public_dict()}


@app.post("/flows", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def create_flow_endpoint(req: FlowRequest):
    try:
        flow = flow_engine.flow_store.create(req.name, req.nodes, req.edges)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "flow": flow.to_public_dict()}


@app.put("/flows/{flow_id}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def update_flow_endpoint(flow_id: str, req: FlowUpdateRequest):
    try:
        flow = flow_engine.flow_store.update(flow_id, req.name, req.nodes, req.edges)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if flow is None:
        raise HTTPException(status_code=404, detail="No such flow.")
    return {"success": True, "flow": flow.to_public_dict()}


@app.delete("/flows/{flow_id}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def delete_flow_endpoint(flow_id: str):
    if not flow_engine.flow_store.delete(flow_id):
        raise HTTPException(status_code=404, detail="No such flow.")
    return {"success": True}


@app.post("/flows/{flow_id}/run", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def run_flow_endpoint(flow_id: str, req: FlowRunRequest):
    flow = flow_engine.flow_store.get(flow_id)
    if flow is None:
        raise HTTPException(status_code=404, detail="No such flow.")
    return await flow_engine.execute_flow(
        flow, req.inputs,
        tool_executor=lambda n, a: _execute_file_tool(n, a),
        llm_generate=lambda p: llm_backend.generate(p, max_tokens=800, temperature=0.5),
    )


@app.get("/system/activity")
async def system_activity():
    """Real, live "what is Billion doing right now" aggregation -- every
    in-flight background mission, every active watch (with its next check
    time), lockdown/focus mode state, and the next few due cron jobs, all
    in one call. Previously the only way to find any of this out was a
    Telegram ping when something finished; this is the always-visible
    dashboard version, not a new tracking mechanism -- everything here
    already existed in its own store, just never aggregated into one view."""
    now = _time.time()
    active_missions = [m.to_public_dict() for m in mission_store.list() if m.stage != "archive"]
    active_watches = [
        {**w.to_public_dict(), "next_check_in_s": max(
            0.0, (w.last_checked_at or now) + w.check_interval_minutes * 60 - now,
        )}
        for w in watch_store.watch_store.list() if w.active
    ]
    upcoming_cron = sorted(
        [j.to_public_dict() for j in cron_store.list() if j.enabled],
        key=lambda j: (j.get("hour", 0), j.get("minute", 0)),
    )[:5]
    return {
        "success": True,
        "active_missions": active_missions,
        "active_watches": active_watches,
        "upcoming_cron_jobs": upcoming_cron,
        "macro_count": len(macro_store.macro_store.list()),
        "lockdown": lockdown_switch.status(),
        "focus_mode": focus_mode.status(),
    }


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
    if req.action_type not in ("telegram_message", "agent_task", "run_skill", "terminal_command", "run_script", "channel_message", "memory_consolidate", "commitment_checkin", "run_macro"):
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
    if req.action_type == "run_macro" and not req.action_payload.get("name"):
        raise HTTPException(status_code=400, detail="run_macro jobs need action_payload.name")
    for chain_id in req.chain_to:
        if cron_store.get(chain_id) is None:
            raise HTTPException(status_code=400, detail=f"chain_to references unknown job id {chain_id!r}")
    job = cron_store.create(
        req.name, req.description, req.hour, req.minute, req.action_type, req.action_payload,
        cron_expression=req.cron_expression, chain_to=req.chain_to, chain_input_key=req.chain_input_key,
    )
    return {"success": True, "job": job.to_public_dict()}


@app.patch("/cron/jobs/{job_id}")
async def toggle_cron_job(job_id: str, enabled: bool):
    job = cron_store.set_enabled(job_id, enabled)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"success": True, "job": job.to_public_dict()}


class CronChainUpdateRequest(BaseModel):
    chain_to: List[str] = []
    chain_input_key: Optional[str] = None


@app.patch("/cron/jobs/{job_id}/chain")
async def update_cron_job_chain(job_id: str, req: CronChainUpdateRequest):
    for chain_id in req.chain_to:
        if cron_store.get(chain_id) is None:
            raise HTTPException(status_code=400, detail=f"chain_to references unknown job id {chain_id!r}")
    job = cron_store.update_chain(job_id, req.chain_to, req.chain_input_key)
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
    if req.action_type not in ("telegram_message", "agent_task", "run_skill", "terminal_command", "run_script", "channel_message", "memory_consolidate", "commitment_checkin", "run_macro"):
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
            _record_security_failure(f"webhook:{hook_id}", f"Invalid signature on inbound webhook \"{hook.name}\"")
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


@app.get("/voice/status")
async def voice_status():
    """Whether a voice profile is currently enrolled -- lets the frontend
    show real enrollment state without needing a live WebSocket connection
    just to ask (enroll/verify themselves stay on the WS, alongside every
    other audio message this app already sends that way)."""
    return {"success": True, "enrolled": voice_id.is_enrolled()}


@app.post("/voice/clear", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def voice_clear():
    """Removes the enrolled voice profile -- after this, _voice_mismatch()
    is always False again (nothing to compare against) until re-enrolled."""
    return voice_id.clear_enrollment()


class VoiceTranscribeRequest(BaseModel):
    audio_b64: str


@app.post("/voice/transcribe", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def voice_transcribe(req: VoiceTranscribeRequest):
    """One-shot server-side STT: a base64 WebM/Opus clip (the exact format
    frontend voice-capture.ts's MediaRecorder produces) in, a transcript
    out, via the same faster-whisper backend the WS audio path uses.

    This is the REST fallback for browsers without the Web Speech API
    (Firefox, Safari) -- see frontend lib/nancy/use-voice.ts's server-STT
    loop. Chrome keeps using its native on-device recognition (lower
    latency, zero backend load) and never calls this."""
    if not req.audio_b64 or len(req.audio_b64) > 8_000_000:  # ~6MB decoded cap
        raise HTTPException(status_code=400, detail="audio_b64 missing or too large")
    try:
        decoded = decode_webm_opus_b64_to_pcm(
            req.audio_b64,
            target_sample_rate=int(os.getenv("STT_SAMPLE_RATE", "16000")),
        )
        audio_np = pcm_int16_to_float32(decoded.pcm_int16)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not decode audio: {e}")
    try:
        transcript = await stt_backend.transcribe(audio_np)
    except Exception as e:
        logger.warning("voice_transcribe STT failed: %s", e)
        raise HTTPException(status_code=503, detail=f"STT backend unavailable: {e}")
    return {"success": True, "transcript": (transcript or "").strip()}


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


class CanvasItemEditRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    language: Optional[str] = None


@app.put("/canvas/{item_id}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def edit_canvas_item(item_id: str, req: CanvasItemEditRequest):
    """Real in-place edit of an existing canvas item's title/content/language
    -- previously the only way to change one was delete + recreate, which
    lost its id, pinned state, and created_at."""
    item = canvas_store.update(item_id, title=req.title, content=req.content, language=req.language)
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


@app.get("/screen-context/status")
async def screen_context_status():
    """Real ambient screen-awareness state -- whether it's on, the last
    real captured summary (if any), and whether vision (ANTHROPIC_API_KEY)
    is even configured. Off and empty by default; nothing here is ever
    fabricated -- see screen_context.py."""
    return {"success": True, **screen_context.status()}


class ScreenContextToggleRequest(BaseModel):
    enabled: bool


@app.post("/screen-context/toggle", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def screen_context_toggle(req: ScreenContextToggleRequest):
    """User-controlled opt-in/out for ambient screen awareness. Turning it
    off immediately clears any cached summary -- no stale screen content
    lingers in Nancy's context after opting out."""
    screen_context.set_enabled(req.enabled)
    if req.enabled:
        # Capture immediately on enable rather than waiting up to 45s for
        # the background loop's next tick, so the toggle feels responsive.
        asyncio.create_task(screen_context.capture_now())
    return {"success": True, **screen_context.status()}


@app.post("/screen-context/capture-now", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def screen_context_capture_now():
    """On-demand real capture + describe, independent of the background
    loop's cadence -- e.g. a manual 'refresh' button in the UI."""
    result = await screen_context.capture_now()
    return result


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


# Every vendor adapter that self-registers into providers/registry.py if its
# env var is set (see providers/bootstrap.py's _VENDOR_MODULES) -- kept here
# as an explicit (capability, vendor, env_var) catalog rather than derived,
# so an *unconfigured* vendor still shows up (PROVIDER_REGISTRIES only ever
# contains the ones that already registered).
_CAPABILITY_CATALOG = [
    ("web_search", "brave", "BRAVE_API_KEY"),
    ("web_search", "tavily", "TAVILY_API_KEY"),
    ("web_search", "searxng", "SEARXNG_BASE_URL"),
    ("image", "fal", "FAL_API_KEY"),
    ("image", "deepinfra", "DEEPINFRA_API_KEY"),
    ("tts", "elevenlabs", "ELEVENLABS_API_KEY"),
    ("transcription", "deepgram", "DEEPGRAM_API_KEY"),
    ("telephony", "twilio", "TWILIO_ACCOUNT_SID"),
    ("sandbox", "crabbox", "CRABBOX_API_KEY"),
    ("memory", "mem0", "MEM0_API_KEY"),
    ("memory", "supermemory", "SUPERMEMORY_API_KEY"),
    ("memory", "honcho", "HONCHO_API_KEY"),
    ("memory", "hindsight", "HINDSIGHT_API_KEY"),
    ("memory", "byterover", "BYTEROVER_API_KEY"),
    ("memory", "openviking", "OPENVIKING_API_KEY"),
    ("memory", "retaindb", "RETAINDB_API_KEY"),
]


@app.get("/config/capabilities")
async def config_capabilities():
    """Real optional-integration status for every vendor adapter that can
    self-register into providers/registry.py. `configured` reflects actual
    live registration (env var set AND construction didn't throw), not just
    whether the env var happens to be set. Never returns a secret value."""
    from providers.registry import PROVIDER_REGISTRIES

    capabilities: Dict[str, List[Dict[str, Any]]] = {}
    for capability, vendor, env_var in _CAPABILITY_CATALOG:
        capabilities.setdefault(capability, []).append({
            "vendor": vendor,
            "configured": vendor in PROVIDER_REGISTRIES.get(capability, {}),
            "env_var": env_var,
        })
    return {"success": True, "capabilities": capabilities}


# Real one-off credentials with no dedicated live-status source (Spotify's
# tool only exposes a plain is_configured() bool with no registry entry;
# FRED and node-pairing have no self-registration mechanism at all).
OTHER_CREDENTIAL_CATALOG = [
    ("FRED_API_KEY", "FRED (economic calendar data)"),
    ("NODE_SHARED_SECRET", "Node pairing shared secret"),
    ("SPOTIFY_CLIENT_ID", "Spotify client ID"),
    ("SPOTIFY_CLIENT_SECRET", "Spotify client secret"),
    ("SPOTIFY_REFRESH_TOKEN", "Spotify refresh token"),
]

# Real fields a channel accepts but doesn't strictly require (see
# CHANNEL_DEFINITIONS' required_env for what's mandatory) -- still worth
# being settable through the same form.
OPTIONAL_CHANNEL_FIELD_CATALOG = [
    ("NTFY_SERVER", "ntfy — server URL (optional, self-hosted)"),
    ("NTFY_TOKEN", "ntfy — token (optional, private servers)"),
    ("SLACK_SIGNING_SECRET", "Slack — signing secret (optional)"),
    ("REEF_PEER_ID", "Reef — peer ID"),
]

_CAPABILITY_GROUPS = {
    "web_search": "Web Search", "image": "Media & Voice", "tts": "Media & Voice",
    "transcription": "Media & Voice", "telephony": "Channels", "sandbox": "Sandbox",
    "memory": "External Memory",
}


def _build_key_catalog() -> List[Dict[str, Any]]:
    """The single real source of truth for every writable credential this
    app has a use for, and for the Keys page's displayed configured-state --
    assembled entirely from the same declarative lists that already drive
    the live LLM chain (llm.LLM_PROVIDER_CATALOG), the channel registry
    (CHANNEL_DEFINITIONS, defined below), and the provider registries
    (_CAPABILITY_CATALOG), plus two small catalogs for the handful of fields
    those don't cover. Adding a new provider/channel/vendor to any of those
    lists is the *only* change needed for it to automatically become
    writable via /config/keys and visible on the Keys page -- nothing here,
    on the frontend, or in a second allowlist ever needs a manual update."""
    from providers.registry import PROVIDER_REGISTRIES
    from channels.registry import list_channels

    entries: List[Dict[str, Any]] = []
    seen: set = set()

    def add(name: str, label: str, group: str, configured: Optional[bool] = None):
        if name in seen:
            return
        seen.add(name)
        entries.append({"name": name, "label": label, "group": group, "configured": configured})

    configured_llm = {b.__class__.__name__ for b in getattr(llm_backend, "backends", [])}
    for env_var, label, backend_cls, _role in LLM_PROVIDER_CATALOG:
        add(env_var, label, "Reasoning", backend_cls.__name__ in configured_llm)

    telegram_ok = bool(telegram_notifier.status.get("available"))
    add("TELEGRAM_BOT_TOKEN", "Telegram bot token", "Messaging", telegram_ok)
    add("TELEGRAM_CHAT_ID", "Telegram chat ID", "Messaging", telegram_ok)

    registered_channels = list_channels()
    for defn in CHANNEL_DEFINITIONS:
        chan_configured = defn["key"] in registered_channels
        for env_var in defn["required_env"]:
            add(env_var, f"{defn['label']} — {env_var}", "Channels", chan_configured)
    for env_var, label in OPTIONAL_CHANNEL_FIELD_CATALOG:
        add(env_var, label, "Channels")

    for capability, vendor, env_var in _CAPABILITY_CATALOG:
        configured = vendor in PROVIDER_REGISTRIES.get(capability, {})
        group = _CAPABILITY_GROUPS.get(capability, capability.replace("_", " ").title())
        add(env_var, f"{vendor} ({capability.replace('_', ' ')})", group, configured)

    for env_var, label in OTHER_CREDENTIAL_CATALOG:
        add(env_var, label, "Other")

    return entries


@app.get("/config/keys/catalog")
async def config_keys_catalog():
    """Real, always-current list of every writable credential (see
    _build_key_catalog) -- the Keys page renders entirely from this response,
    so a new provider/channel/vendor added to any of the source catalogs
    appears here automatically, with no separate frontend list to maintain."""
    return {"success": True, "entries": _build_key_catalog()}


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

    writable_names = {e["name"] for e in _build_key_catalog()}
    name = req.name.strip().upper()
    if name not in writable_names:
        raise HTTPException(status_code=400, detail=f"'{name}' is not a writable key. Allowed: {sorted(writable_names)}")
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


# ---------------------------------------------------------------------------
# Ollama Cloud connect flow -- one-click connect from the Overview page.
# Unlike the generic /config/keys write above (honest "takes effect on
# restart"), these endpoints validate the key against ollama.com LIVE and
# hot-rebuild the running FallbackLLM chain in place, so connect/disconnect
# genuinely applies immediately. Disconnect is also reachable from the
# built-in terminal: `curl -X POST http://localhost:8000/ollama-cloud/disconnect`.
# ---------------------------------------------------------------------------

class OllamaCloudConnectRequest(BaseModel):
    api_key: str


def _ollama_cloud_masked_key() -> Optional[str]:
    key = os.getenv("OLLAMA_CLOUD_API_KEY") or os.getenv("OLLAMA_API_KEY")
    if not key:
        return None
    return f"{key[:4]}…{key[-4:]}" if len(key) > 10 else "…"


def _rebuild_llm_chain() -> List[str]:
    """Swap the live FallbackLLM's backend list in place (same object every
    module already holds a reference to, so the whole app picks it up)."""
    from llm import get_llm_backends
    llm_backend.backends = get_llm_backends()
    return [b.__class__.__name__ for b in llm_backend.backends]


@app.get("/tools/catalog")
async def tools_catalog():
    """Grouped catalog of every REAL tool the chat tool-use loop can call
    (the same _all_chat_tools() list both the WS chat and skill runner
    use). Powers the CLI boot screen's 'Available Tools' column -- names
    grouped by their leading prefix (file_*, browser_*, ...), singletons
    folded into 'general'."""
    groups: Dict[str, List[str]] = {}
    for tool in _all_chat_tools():
        name = tool.get("name", "")
        if not name:
            continue
        prefix = name.split("_", 1)[0] if "_" in name else name
        groups.setdefault(prefix, []).append(name)
    merged: Dict[str, List[str]] = {}
    general: List[str] = []
    for prefix, names in groups.items():
        if len(names) == 1:
            general.extend(names)
        else:
            merged[prefix] = sorted(names)
    if general:
        merged["general"] = sorted(general)
    total = sum(len(v) for v in merged.values())
    return {"success": True, "groups": dict(sorted(merged.items())), "total": total}


# Provider slug → (env var for the key, env var for the model, live models fetcher)
# Each fetcher returns a plain list of model-id strings, best-effort: a
# provider whose listing endpoint can't be reached reports [] rather than
# failing the whole response.
async def _list_models_opencode(session) -> List[str]:
    key = os.getenv("OPENCODE_API_KEY")
    if not key:
        return []
    async with session.get("https://opencode.ai/zen/v1/models",
                           headers={"Authorization": f"Bearer {key}"}) as r:
        if r.status != 200:
            return []
        data = await r.json()
    return sorted(str(m.get("id")) for m in data.get("data", []) if m.get("id"))


async def _list_models_ollama_cloud(session) -> List[str]:
    key = os.getenv("OLLAMA_CLOUD_API_KEY") or os.getenv("OLLAMA_API_KEY")
    if not key:
        return []
    base = os.getenv("OLLAMA_CLOUD_BASE_URL", "https://ollama.com")
    async with session.get(f"{base}/api/tags", headers={"Authorization": f"Bearer {key}"}) as r:
        if r.status != 200:
            return []
        data = await r.json()
    return sorted(str(m.get("name")) for m in data.get("models", []) if m.get("name"))


async def _list_models_ollama_local(session) -> List[str]:
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    async with session.get(f"{base}/api/tags") as r:
        if r.status != 200:
            return []
        data = await r.json()
    return sorted(str(m.get("name")) for m in data.get("models", []) if m.get("name"))


async def _list_models_groq(session) -> List[str]:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return []
    async with session.get("https://api.groq.com/openai/v1/models",
                           headers={"Authorization": f"Bearer {key}"}) as r:
        if r.status != 200:
            return []
        data = await r.json()
    return sorted(str(m.get("id")) for m in data.get("data", []) if m.get("id"))


async def _list_models_anthropic(session) -> List[str]:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return []
    async with session.get("https://api.anthropic.com/v1/models",
                           headers={"x-api-key": key, "anthropic-version": "2023-06-01"}) as r:
        if r.status != 200:
            return []
        data = await r.json()
    return [str(m.get("id")) for m in data.get("data", []) if m.get("id")]


_MODEL_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "anthropic":   {"label": "Anthropic (Claude)", "model_env": "ANTHROPIC_MODEL",    "backend_cls": "AnthropicLLM",       "fetch": _list_models_anthropic},
    "groq":        {"label": "Groq",               "model_env": "GROQ_MODEL",         "backend_cls": "GroqLLM",            "fetch": _list_models_groq},
    "opencode":    {"label": "OpenCode Zen",       "model_env": "OPENCODE_MODEL",     "backend_cls": "OpenCodeLLM",        "fetch": _list_models_opencode},
    "ollamacloud": {"label": "Ollama Cloud",       "model_env": "OLLAMA_CLOUD_MODEL", "backend_cls": "OllamaCloudLLM",     "fetch": _list_models_ollama_cloud},
    "ollama":      {"label": "Ollama (local)",     "model_env": "OLLAMA_MODEL",       "backend_cls": "OllamaAutoModelsLLM", "fetch": _list_models_ollama_local},
}


@app.get("/llm/models")
async def llm_list_models(backend: Optional[str] = None):
    """LIVE per-provider model enumeration -- each list is fetched from the
    provider's own real listing endpoint with YOUR key, so it shows exactly
    the models your account can actually call (OpenCode Zen's /v1/models,
    Ollama Cloud's and local Ollama's /api/tags, Groq's and Anthropic's
    model APIs). Powers the CLI's /model picker. `backend` narrows to one
    provider slug (anthropic|groq|opencode|ollamacloud|ollama)."""
    import aiohttp
    wanted = {backend.strip().lower()} if backend else set(_MODEL_PROVIDERS)
    out: Dict[str, Any] = {}
    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(timeout=timeout, headers={"Accept-Encoding": "identity"}) as session:
        for slug, spec in _MODEL_PROVIDERS.items():
            if slug not in wanted:
                continue
            try:
                models = await spec["fetch"](session)
            except Exception as e:
                logger.debug("Model listing for %s failed: %s", slug, e)
                models = []
            out[slug] = {
                "label": spec["label"],
                "current": os.getenv(spec["model_env"]) or None,
                "models": models[:60],
                "total": len(models),
            }
    if backend and not out:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{backend}'. Known: {sorted(_MODEL_PROVIDERS)}")
    return {"success": True, "providers": out}


class LlmModelRequest(BaseModel):
    backend: str
    model: str
    make_primary: bool = True


def _persist_primary(backend_cls: str) -> None:
    """Write the chosen primary to backend/.env so it survives a restart.

    Both /llm/model and /llm/primary used to reorder the live chain in memory
    only, which meant an explicit pick was silently dropped on the next
    restart -- and llm.get_llm_backends() rebuilds from the catalog's default
    order, putting Claude back in front along with its tool-loop priority.
    """
    try:
        os.environ["LLM_PRIMARY"] = backend_cls
        from dotenv import set_key
        env_path = Path(__file__).parent / ".env"
        if not env_path.exists():
            env_path.touch()
        set_key(str(env_path), "LLM_PRIMARY", backend_cls)
    except Exception as e:
        # Never fail the request over this -- the in-memory switch already
        # worked, persistence is the bonus.
        logger.warning("Could not persist LLM_PRIMARY=%s: %s", backend_cls, e)


@app.post("/llm/model", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def llm_set_model(req: LlmModelRequest):
    """Set the ACTIVE model for a provider, live: updates the running
    backend instance, the process env (chat paths construct fresh backend
    instances per call, which read env), and persists to backend/.env so
    the choice survives a restart. Optionally also promotes that provider
    to primary in the chain (the default -- picking a model usually means
    'talk to this now')."""
    slug = req.backend.strip().lower().replace(" ", "")
    spec = _MODEL_PROVIDERS.get(slug)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{req.backend}'. Known: {sorted(_MODEL_PROVIDERS)}")
    model = req.model.strip()
    if not model:
        raise HTTPException(status_code=400, detail="model cannot be empty")

    os.environ[spec["model_env"]] = model
    from dotenv import set_key
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        env_path.touch()
    set_key(str(env_path), spec["model_env"], model)

    switched = False
    for i, b in enumerate(llm_backend.backends):
        if b.__class__.__name__ == spec["backend_cls"]:
            if hasattr(b, "model"):
                b.model = model
            if req.make_primary:
                llm_backend.backends.insert(0, llm_backend.backends.pop(i))
                _persist_primary(spec["backend_cls"])
            switched = True
            break

    chain = [b.__class__.__name__ for b in llm_backend.backends]
    logger.info("Model set: %s -> %s (primary=%s); chain %s", slug, model, req.make_primary, chain)
    return {
        "success": True,
        "backend": spec["label"],
        "model": model,
        "primary": req.make_primary and switched,
        "in_chain": switched,
        "chain": chain,
        "message": (f"{spec['label']} now uses {model}"
                    + (" and is the live primary." if req.make_primary and switched else ".")
                    + ("" if switched else f" ({spec['label']} isn't in the live chain yet -- configure its key first.)")),
    }


class LlmPrimaryRequest(BaseModel):
    backend: str


@app.post("/llm/primary", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def llm_set_primary(req: LlmPrimaryRequest):
    """Live /model switch: move the named backend to the FRONT of the
    running FallbackLLM chain (in-memory reorder of the same list every
    caller already holds -- applies to the very next message, survives
    until restart). Matches on class name or its lowercase stem, e.g.
    'anthropic', 'groq', 'OllamaCloudLLM', 'opencode'."""
    want = req.backend.strip().lower().replace(" ", "")
    if not want:
        raise HTTPException(status_code=400, detail="backend cannot be empty")
    for i, b in enumerate(llm_backend.backends):
        cls = b.__class__.__name__
        stem = cls.lower().removesuffix("llm")
        if want in (cls.lower(), stem) or want == stem.removesuffix("automodels"):
            llm_backend.backends.insert(0, llm_backend.backends.pop(i))
            _persist_primary(cls)
            chain = [x.__class__.__name__ for x in llm_backend.backends]
            logger.info("LLM primary switched to %s via /llm/primary; chain now %s", cls, chain)
            return {"success": True, "primary": cls, "chain": chain, "persisted": True}
    raise HTTPException(
        status_code=404,
        detail=f"No backend matching '{req.backend}' in the live chain: "
               f"{[b.__class__.__name__ for b in llm_backend.backends]}",
    )


@app.get("/llm/order")
async def llm_get_order():
    """The live chain, in priority order, with why each entry sits where it
    does. Backs the frontend's reordering UI -- every caller in the system
    (web chat, Telegram, all 70 agents) shares this exact list, so what is
    shown here IS what runs."""
    from llm import _is_local_backend

    chain = []
    for i, b in enumerate(llm_backend.backends):
        cls = b.__class__.__name__
        chain.append({
            "position": i,
            "backend": cls,
            "stem": cls.lower().removesuffix("llm"),
            "model": getattr(b, "model", None),
            "local": _is_local_backend(cls),
            "configured": bool(getattr(b, "api_key", True)),
        })
    return {
        "success": True,
        "chain": chain,
        "order_env": os.getenv("LLM_ORDER", ""),
        "primary": chain[0]["backend"] if chain else None,
    }


@app.post("/llm/order", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def llm_set_order(req: LlmOrderRequest):
    """Reorder the ENTIRE chain and persist it.

    /llm/primary can only ever promote one backend, so expressing "try these
    four in this sequence" was impossible without editing .env and
    restarting. This reorders the live list every caller already holds --
    so it applies to the very next message across web chat, Telegram and
    every agent simultaneously -- and writes LLM_ORDER so it survives a
    restart.

    Named backends move to the front in the given order; unnamed ones keep
    their relative order behind them; local backends are always forced last
    (reaching them means every cloud option failed, and they compete with
    TTS for CPU on this machine).
    """
    from llm import _is_local_backend, matches_backend_name

    wanted = [w.strip() for w in req.order if w and w.strip()]
    if not wanted:
        raise HTTPException(status_code=400, detail="order cannot be empty")

    live = list(llm_backend.backends)
    ordered, remaining = [], list(live)
    unmatched = []
    for want in wanted:
        hits = [b for b in remaining if matches_backend_name(b.__class__.__name__, want)]
        if not hits:
            unmatched.append(want)
            continue
        for b in hits:  # move a vendor's models as a group, keeping siblings adjacent
            ordered.append(b)
            remaining.remove(b)

    merged = ordered + remaining
    cloud = [b for b in merged if not _is_local_backend(b.__class__.__name__)]
    local = [b for b in merged if _is_local_backend(b.__class__.__name__)]
    llm_backend.backends[:] = cloud + local  # in-place: every holder of this list sees it

    try:
        os.environ["LLM_ORDER"] = ",".join(wanted)
        from dotenv import set_key
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            set_key(str(env_path), "LLM_ORDER", ",".join(wanted))
        persisted = True
    except Exception:
        logger.exception("Failed to persist LLM_ORDER")
        persisted = False

    chain = [b.__class__.__name__ for b in llm_backend.backends]
    logger.info("LLM chain reordered via /llm/order; chain now %s", chain)
    return {
        "success": True, "chain": chain, "persisted": persisted,
        "unmatched": unmatched,
        "primary": chain[0] if chain else None,
    }


@app.get("/ollama-cloud/status")
async def ollama_cloud_status():
    connected = bool(os.getenv("OLLAMA_CLOUD_API_KEY") or os.getenv("OLLAMA_API_KEY"))
    return {
        "success": True,
        "connected": connected,
        "key_masked": _ollama_cloud_masked_key(),
        "model": os.getenv("OLLAMA_CLOUD_MODEL", "gpt-oss:120b"),
        "base_url": os.getenv("OLLAMA_CLOUD_BASE_URL", "https://ollama.com"),
        "in_chain": any(b.__class__.__name__ == "OllamaCloudLLM" for b in llm_backend.backends),
        "connect_url": "https://ollama.com/settings/keys",
    }


@app.post("/ollama-cloud/connect", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def ollama_cloud_connect(req: OllamaCloudConnectRequest):
    """Validate the pasted key against ollama.com for real (GET /api/tags
    with the Bearer token), persist it to backend/.env, and hot-rebuild the
    live LLM chain so Ollama Cloud is usable on the very next message."""
    import aiohttp
    api_key = req.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="api_key cannot be empty")
    base_url = os.getenv("OLLAMA_CLOUD_BASE_URL", "https://ollama.com")
    try:
        async with aiohttp.ClientSession(headers={"Accept-Encoding": "identity"}) as session:
            async with session.get(
                f"{base_url}/api/tags",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=aiohttp.ClientTimeout(total=12),
            ) as resp:
                if resp.status in (401, 403):
                    raise HTTPException(status_code=401, detail="ollama.com rejected this key (unauthorized). Check it at https://ollama.com/settings/keys")
                if resp.status != 200:
                    raise HTTPException(status_code=502, detail=f"ollama.com answered {resp.status} while validating the key")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach ollama.com to validate the key: {e}")

    from dotenv import set_key
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        env_path.touch()
    set_key(str(env_path), "OLLAMA_CLOUD_API_KEY", api_key)
    os.environ["OLLAMA_CLOUD_API_KEY"] = api_key
    chain = _rebuild_llm_chain()
    logger.info("Ollama Cloud connected (key validated live); chain rebuilt: %s", chain)
    return {
        "success": True,
        "connected": True,
        "key_masked": _ollama_cloud_masked_key(),
        "chain": chain,
        "message": "Ollama Cloud connected and live in the fallback chain -- no restart needed.",
    }


@app.post("/ollama-cloud/disconnect", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def ollama_cloud_disconnect():
    """Logout: remove the key from .env and the process env, and hot-rebuild
    the chain so Ollama Cloud drops out immediately."""
    from dotenv import unset_key
    env_path = Path(__file__).parent / ".env"
    removed = False
    for name in ("OLLAMA_CLOUD_API_KEY", "OLLAMA_API_KEY"):
        if os.environ.pop(name, None) is not None:
            removed = True
        if env_path.exists():
            try:
                unset_key(str(env_path), name)
            except Exception:
                logger.debug("unset_key(%s) failed (key may not be in .env)", name)
    chain = _rebuild_llm_chain()
    logger.info("Ollama Cloud disconnected; chain rebuilt: %s", chain)
    return {
        "success": True,
        "connected": False,
        "removed": removed,
        "chain": chain,
        "message": "Ollama Cloud disconnected -- key removed from .env and the live chain.",
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


@app.get("/sessions/status")
async def sessions_status():
    """Real count of currently-open WebSocket connections (manager.active_connections
    -- each browser tab/device actively talking to this backend right now)
    plus real backend process uptime. Distinct from the frontend's own
    per-tab `logs` state, which only reflects the current tab's turns."""
    return {
        "success": True,
        "active_connections": len(manager.active_connections),
        "uptime_hours": (_time.time() - _PROCESS_START_TIME) / 3600.0,
    }


@app.get("/telegram/status")
async def telegram_status():
    """Whether Telegram is configured and the reply-polling loop is running -
    see telegram_bot.py. TelegramNotifier's status is a plain attribute (not
    a property doing I/O), so no executor offload is needed here."""
    return {"success": True, **telegram_notifier.status}


# Real definitions for every channel this backend actually knows how to
# speak (channels/bootstrap.py's _CHANNEL_MODULES) -- used so /channels/status
# can honestly report *why* an unconfigured channel isn't live (which real
# env vars it needs) instead of just omitting it, the way the old frontend
# Discord/WhatsApp placeholders pretended channels existed that were never
# actually built.
CHANNEL_DEFINITIONS: List[Dict[str, Any]] = [
    {"key": "ntfy", "label": "ntfy", "description": "Free push notifications to your phone or desktop via ntfy.sh (or a self-hosted server).", "required_env": ["NTFY_TOPIC"], "two_way": False},
    {"key": "home_assistant", "label": "Home Assistant", "description": "Notifies and calls services on a real Home Assistant instance on your network.", "required_env": ["HOME_ASSISTANT_URL", "HOME_ASSISTANT_TOKEN"], "two_way": False},
    {"key": "photon", "label": "iMessage (Photon)", "description": "Real iMessage delivery via a Photon sidecar process running on a Mac -- this IS the iMessage integration.", "required_env": ["PHOTON_SIDECAR_URL", "PHOTON_SHARED_SECRET"], "two_way": True},
    {"key": "reef", "label": "Reef", "description": "Encrypted agent-to-agent messaging over the Reef network.", "required_env": ["REEF_API_KEY", "REEF_ENDPOINT", "REEF_PEER_ID"], "two_way": True},
    {"key": "clickclack", "label": "ClickClack", "description": "Messaging via the ClickClack chat platform.", "required_env": ["CLICKCLACK_API_KEY"], "two_way": False},
    {"key": "slack", "label": "Slack", "description": "Posts to a Slack channel via a bot token.", "required_env": ["SLACK_BOT_TOKEN"], "two_way": True},
    {"key": "voice_call", "label": "Voice Call", "description": "Real outbound phone calls via Twilio.", "required_env": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"], "two_way": False},
    {"key": "discord", "label": "Discord", "description": "Posts to a Discord channel via a real bot token (Discord's REST API).", "required_env": ["DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_ID"], "two_way": False},
    {"key": "whatsapp", "label": "WhatsApp", "description": "Real WhatsApp messages via Meta's WhatsApp Business Cloud API.", "required_env": ["WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID"], "two_way": False},
]


@app.get("/channels/status")
async def channels_status():
    """Real status for every channel this backend can speak: Telegram
    (predates channels/registry.py, checked via telegram_notifier) plus
    every channel in the real registry. A channel is only 'configured' if
    it actually registered (its own is_configured() passed) -- otherwise
    it's reported honestly as not configured, with the real env vars it
    needs, never a fabricated entry for an integration that doesn't exist."""
    from channels.registry import list_channels
    registered = list_channels()

    channels = [{
        "key": "telegram",
        "label": "Telegram",
        "description": "Two-way chat, the approval-request gate, and proactive alerts (economic calendar, daily briefing).",
        "configured": bool(telegram_notifier.status.get("available")),
        "detail": telegram_notifier.status.get("error"),
        "two_way": True,
        "required_env": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
    }]
    for defn in CHANNEL_DEFINITIONS:
        channels.append({
            "key": defn["key"],
            "label": defn["label"],
            "description": defn["description"],
            "configured": defn["key"] in registered,
            "detail": None,
            "two_way": defn["two_way"],
            "required_env": defn["required_env"],
        })
    return {"success": True, "channels": channels}


class ChannelTestRequest(BaseModel):
    message: str = "Test message from Nancy's Signal Board."


@app.post("/channels/{name}/test", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def channel_test(name: str, req: ChannelTestRequest):
    """Send a real test message through a real, currently-configured
    channel. 404 if it isn't registered -- never pretends to send through
    something that was never actually set up."""
    if name == "telegram":
        if not telegram_notifier.status.get("available"):
            raise HTTPException(status_code=404, detail="Telegram is not configured")
        await telegram_notifier.send(req.message)
        return {"success": True}

    from channels.registry import get_channel
    channel = get_channel(name)
    if channel is None:
        raise HTTPException(status_code=404, detail=f"Channel {name!r} is not configured")
    ok = await channel.send(req.message)
    return {"success": ok}


@app.get("/telegram/pair/bot")
async def telegram_pair_bot():
    """Real bot username (Telegram getMe), so the Pairing page can render a
    clickable https://t.me/<username> link instead of just saying "message
    this code to your bot" with no indication of which bot that is."""
    return await telegram_pairing.get_bot_username()


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


@app.post("/agents/collaborate", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def agents_collaborate(req: AgentCollaborateRequest):
    """Run a real produce -> critique -> revise cycle between two agents.

    The 'agents improve one another' pillar, exposed. Distinct from
    /agents/run (one agent, one task) and from DispatcherAgent (fan out to
    several agents in parallel, then merge): here the reviewer's objections
    are fed back to the producer as a genuine revision request, and the
    revised work is reviewed again -- see agents/collaboration.py.
    """
    from agents.capability_index import capability_index
    from agents.collaboration import produce_and_refine

    if not agent_service.is_ready():
        raise HTTPException(status_code=503, detail="Agent service not ready yet")

    producer = req.producer
    if not producer:
        best = await capability_index.best_expert(req.goal)
        if not best:
            raise HTTPException(
                status_code=422,
                detail="No agent is a convincing fit for that goal -- name a producer explicitly.",
            )
        producer = best[0]
    reviewer = req.reviewer or await capability_index.pick_reviewer(producer, req.goal)
    if not reviewer:
        raise HTTPException(
            status_code=422,
            detail=f"No qualified reviewer found for '{producer}' on that goal -- name one explicitly.",
        )

    result = await produce_and_refine(
        req.goal, producer, reviewer,
        rounds=max(1, min(req.rounds, 4)), timeout=req.timeout,
    )
    result["auto_selected"] = {
        "producer": req.producer is None, "reviewer": req.reviewer is None,
    }
    # Real collaborative output is worth keeping -- it's the kind of
    # multi-agent finding the memory graph exists to accumulate.
    try:
        if result.get("success") and result.get("approved"):
            memory_manager.graph.add_or_merge_memory(
                f"[{producer}+{reviewer}] {req.goal} -> {result['final'][:1000]}",
                MemoryType.INSIGHT,
                {
                    "source": "agent_collaboration", "producer": producer,
                    "reviewer": reviewer, "rounds": result.get("rounds_used"),
                    "verified": True,
                },
                importance=0.5,
                # Reasoned output that a second agent reviewed and approved.
                # Not a measurement, so INFERRED -- trust.py caps it below
                # anything actually observed, which is correct.
                confidence=0.6, provenance="inferred",
                source=f"collaboration:{producer}+{reviewer}",
            )
    except UntrustedMemoryRejected as e:
        logger.info("Collaboration result not stored: %s", e)
    except Exception:
        logger.exception("Failed to record collaboration result")
    return {"success": True, **result}


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


ARM_MAX_SECONDS = float(os.getenv("ARM_MAX_SECONDS", "1800"))  # 30 minutes


@app.post("/safety/arm", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def arm_safety_switch(req: ArmRequest):
    """Arming is the keystone: every other gate in this file is written as
    `if not arm_switch.is_armed()`, so one call here disables all of them at
    once. That made it the single most valuable endpoint to reach, and it was
    the only dangerous one with no approval of its own -- an unauthenticated
    caller could arm for a day and then walk through every gate unprompted.

    It now costs a Telegram approval, and the window is capped so a
    typo'd (or hostile) duration can't leave the system armed indefinitely.
    """
    duration = max(1.0, min(float(req.duration_s), ARM_MAX_SECONDS))
    capped = duration < float(req.duration_s)

    reason = req.reason or "no reason given"
    if not await _request_approval(
        f"Nancy wants to ARM the safety switch for {int(duration)}s "
        f"({reason}).\n\nWhile armed, file writes, shell commands and Docker "
        f"operations run WITHOUT asking you again.",
        timeout=120.0,
    ):
        logger.warning("Arm request denied (duration=%ss, reason=%s)", duration, reason)
        raise HTTPException(status_code=403, detail="Arming was not approved.")

    result = arm_switch.arm(duration, req.reason)
    logger.info("Safety switch ARMED for %ss (reason=%s)", duration, reason)
    if isinstance(result, dict) and capped:
        result["capped_to_seconds"] = duration
        result["note"] = f"Requested window shortened to the {int(ARM_MAX_SECONDS)}s maximum."
    return result


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
# Command Layer -- direct, human-initiated entry points into the exact same
# real terminal/file/web tools Claude's tool-use loop already calls, gated by
# the exact same safety rules (safe-prefix-or-approval for commands, Telegram
# approval + the security linter for writes). This replaces what used to be
# a fully simulated "app launcher" (random fake PIDs, no real backend call).
# ---------------------------------------------------------------------------
class TerminalExecuteRequest(BaseModel):
    command: str
    cwd: Optional[str] = None


@app.post("/terminal/execute", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def terminal_execute_route(req: TerminalExecuteRequest):
    if not req.command.strip():
        raise HTTPException(status_code=400, detail="command is required")
    if not terminal_tool._is_safe_command(req.command) and not arm_switch.is_armed():
        approved = await telegram_notifier.request_approval(
            f"Command Layer wants to run a command:\n\n{req.command}", timeout=120.0
        )
        if not approved:
            return {"success": False, "error": "User did not approve this command."}
    return await terminal_tool.execute_command(req.command, cwd=req.cwd)


@app.get("/files/browse", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def files_browse_route(path: str = "."):
    return file_access.list_directory(path)


@app.get("/files/read", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def files_read_route(path: str, offset: int = 0, limit: Optional[int] = None):
    """offset/limit added so the Command Layer's code editor can page through
    a file bigger than the per-call byte cap (this codebase's own
    main_new.py is one) instead of only ever seeing a silent truncation."""
    return file_access.read_file(path, offset, limit)


@app.get("/files/search", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def files_search_route(pattern: str, path: str = ".", glob: str = "", case_sensitive: bool = False):
    return file_access.search_files(pattern, path, glob, case_sensitive)


@app.get("/files/glob", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def files_glob_route(pattern: str, path: str = "."):
    return file_access.glob_files(pattern, path)


class FileWriteRequest(BaseModel):
    path: str
    content: str


@app.post("/files/write", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def files_write_route(req: FileWriteRequest):
    if not arm_switch.is_armed():
        description = f"Write to file: {req.path}"
        lint_findings = security_lint.lint_content(req.content)
        description += security_lint.format_findings(lint_findings)
        approved = await telegram_notifier.request_approval(f"Command Layer wants to: {description}", timeout=120.0)
        if not approved:
            return {"success": False, "error": "User did not approve this file write."}
    await lifecycle_hooks.fire_hook("pre_write", {"path": req.path})
    result = file_access.write_file(req.path, req.content)
    evidence_ledger.record_evidence("write_file", req.path, result.get("success", False))
    if result.get("success"):
        _attach_python_syntax_check(result, req.path)
    return result


class FileEditRequest(BaseModel):
    path: str
    old_string: str
    new_string: str
    replace_all: bool = False


@app.post("/files/edit", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def files_edit_route(req: FileEditRequest):
    """Surgical old_string/new_string replace for the Command Layer editor --
    same idiom and safety pipeline as write, see files_write_route."""
    if not arm_switch.is_armed():
        description = (
            f"Edit file: {req.path}\n\n- {req.old_string[:200]!r}\n+ {req.new_string[:200]!r}"
        )
        approved = await telegram_notifier.request_approval(f"Command Layer wants to: {description}", timeout=120.0)
        if not approved:
            return {"success": False, "error": "User did not approve this file edit."}
    await lifecycle_hooks.fire_hook("pre_write", {"path": req.path})
    result = file_access.edit_file(req.path, req.old_string, req.new_string, req.replace_all)
    evidence_ledger.record_evidence("edit_file", req.path, result.get("success", False))
    if result.get("success"):
        _attach_python_syntax_check(result, req.path)
        result.pop("old_content", None)
        result.pop("new_content", None)
    return result


class MkdirRequest(BaseModel):
    path: str


@app.post("/files/mkdir", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def files_mkdir_route(req: MkdirRequest):
    """"New Folder" for the Command Layer editor -- ungated, same risk
    profile as creating an empty file: nothing destructive, nothing to
    lose. Real write/delete/move stay approval-gated below."""
    return file_access.create_directory(req.path)


class DeleteRequest(BaseModel):
    path: str


@app.post("/files/delete", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def files_delete_route(req: DeleteRequest):
    if not arm_switch.is_armed():
        approved = await telegram_notifier.request_approval(f"Command Layer wants to: Delete {req.path}", timeout=120.0)
        if not approved:
            return {"success": False, "error": "User did not approve this deletion."}
    result = file_access.delete_file(req.path)
    evidence_ledger.record_evidence("delete_file", req.path, result.get("success", False))
    return result


class MoveRequest(BaseModel):
    src: str
    dst: str


@app.post("/files/move", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def files_move_route(req: MoveRequest):
    """Also doubles as rename -- src and dst in the same directory."""
    if not arm_switch.is_armed():
        approved = await telegram_notifier.request_approval(
            f"Command Layer wants to: Move/rename {req.src} -> {req.dst}", timeout=120.0
        )
        if not approved:
            return {"success": False, "error": "User did not approve this move/rename."}
    result = file_access.move_file(req.src, req.dst)
    evidence_ledger.record_evidence("move_file", f"{req.src} -> {req.dst}", result.get("success", False))
    return result


class OpenApplicationRequest(BaseModel):
    target: str
    args: Optional[List[str]] = None


@app.post("/system/open-application", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def open_application_route(req: OpenApplicationRequest):
    """Direct Command Layer entry point into the same real app-launching
    open_application uses as a chat tool -- see _open_application_dispatch."""
    return await _open_application_dispatch(req.target, req.args)


class WebFetchRequest(BaseModel):
    url: str


@app.post("/web/fetch", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def web_fetch_route(req: WebFetchRequest):
    return await fetch_url(req.url)


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


@app.post("/mdns/advertise", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def mdns_advertise_route():
    return await mdns_discovery.advertise(port=int(os.getenv("PORT", "8000")))


@app.post("/mdns/stop", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def mdns_stop_route():
    return await mdns_discovery.stop_advertising()


@app.get("/mdns/status", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def mdns_status_route():
    return {"success": True, **mdns_discovery.status()}


@app.get("/mdns/discover", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def mdns_discover_route(timeout_s: float = 3.0):
    return {"success": True, "services": await mdns_discovery.discover(timeout_s=timeout_s)}


class FleetCellCreateRequest(BaseModel):
    tenant_id: str
    image: str = "python:3.11-slim"
    mem_limit: str = "256m"
    nano_cpus: float = 0.5
    allowed_env_keys: List[str] = []
    command: Optional[str] = None


class FleetCellExecRequest(BaseModel):
    command: str
    timeout: int = 30


@app.get("/fleet/health", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def fleet_health_route():
    return fleet_manager.check_docker_health()


@app.get("/fleet/cells", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def list_fleet_cells_route(tenant_id: Optional[str] = None):
    return {"success": True, "cells": fleet_manager.list_cells(tenant_id)}


@app.post("/fleet/cells", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def create_fleet_cell_route(req: FleetCellCreateRequest):
    approved = await telegram_notifier.request_approval(
        f"Nancy wants to create a new fleet cell (Docker container) for tenant '{req.tenant_id}' from image {req.image}.", timeout=120.0,
    )
    if not approved:
        raise HTTPException(status_code=403, detail="User did not approve creating this cell.")
    return await fleet_manager.create_cell(req.tenant_id, req.image, req.mem_limit, req.nano_cpus, req.allowed_env_keys, req.command)


@app.post("/fleet/cells/{cell_id}/exec", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def exec_fleet_cell_route(cell_id: str, req: FleetCellExecRequest):
    return await fleet_manager.exec_in_cell(cell_id, req.command, req.timeout)


@app.post("/fleet/cells/{cell_id}/stop", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def stop_fleet_cell_route(cell_id: str):
    return await fleet_manager.stop_cell(cell_id)


@app.post("/fleet/cells/{cell_id}/backup", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def backup_fleet_cell_route(cell_id: str):
    return await fleet_manager.backup_cell(cell_id)


@app.delete("/fleet/cells/{cell_id}", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def remove_fleet_cell_route(cell_id: str):
    approved = await telegram_notifier.request_approval(f"Nancy wants to remove fleet cell {cell_id}.", timeout=120.0)
    if not approved:
        raise HTTPException(status_code=403, detail="User did not approve removing this cell.")
    return await fleet_manager.remove_cell(cell_id)


@app.get("/achievements", dependencies=[Depends(require_auth), Depends(rate_limit)])
async def list_achievements_route():
    activity = _gather_activity_stats()
    unlocked = achievements_store.compute_unlocked(activity)
    unlocked_keys = {a["key"] for a in unlocked}
    unlock_times, newly_unlocked = achievements_store.record_unlocks(list(unlocked_keys))
    for a in unlocked:
        a["unlocked_at"] = unlock_times.get(a["key"])
    for a in unlocked:
        if a["key"] in newly_unlocked:
            await _fire_webhooks("achievement_unlocked", {"key": a["key"], "title": a["title"], "tier": a["tier"]})
    all_ach = achievements_store.all_achievements(activity)
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


async def _execute_background_chat_task(mission_id: str, description: str) -> None:
    """Real background execution for the run_background_task chat tool --
    unlike _dispatch_mission above (which only runs a mission that has a
    specialized agent assigned), this runs the description through the SAME
    general tool-use hierarchy any chat message gets (files, terminal, web,
    browser, camera, everything), for a task that isn't mapped to one of the
    47 specialized agents. Still tracked as a real mission (Mission Control
    sees it), still real async execution via asyncio.create_task in the
    caller, not a blocking call.

    Explicitly clears the tool-progress turn context (_current_turn_ctx) and
    the voice-match context first -- asyncio.create_task copies the CALLING
    turn's context by default, and without this, this task's own tool calls
    would both broadcast "tool_progress" messages tagged with the original
    (now long since answered) turn, AND incorrectly inherit whatever
    voice-match result the triggering turn happened to have, confusing that
    conversation's log and misrepresenting this task's own (voice-less)
    origin. Matches the user's explicit "need-to-know basis" ask directly:
    no intermediate visibility, exactly one real notification when it's
    actually done."""
    _current_turn_ctx.set(None)
    _current_voice_match.set(None)
    _current_speaker_profile_id.set(None)
    _current_turn_audio.set(None)
    try:
        response, debug = await _generate_response_via_hierarchy(description)
        success = True
    except Exception as e:
        response = f"Background task failed: {e}"
        debug = {}
        success = False

    mission_store.record_result(mission_id, success=success, text=response)
    next_stage = "validation" if success else "agent_assignment"
    try:
        updated = mission_store.transition(mission_id, next_stage)
    except MissionError:
        updated = mission_store.get(mission_id)
    await event_bus.publish(
        "MISSION_COMPLETED" if success else "MISSION_UPDATED",
        {"mission": updated.to_public_dict() if updated else None},
    )

    prefix = "Background task done, Sir" if success else "Background task failed, Sir"
    await telegram_notifier.send(f"{prefix}: {description[:100]}\n\n{response}")
    await _broadcast_reply_to_web(response, debug.get("images"), source="background_task")


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
    if _BACKEND_AUTH_TOKEN:
        supplied = websocket.query_params.get("token", "")
        # A browser can't set an Authorization header on a WebSocket, and the
        # real token has no business sitting in a URL (history, proxy logs,
        # referrers). So the page fetches a short-lived single-use ticket
        # through the authenticated proxy and presents that instead. The raw
        # token still works for non-browser clients like the CLI.
        ok = bool(supplied) and secrets.compare_digest(supplied, _BACKEND_AUTH_TOKEN)
        if not ok:
            ok = _redeem_ws_ticket(websocket.query_params.get("ticket", ""))
        if not ok:
            _record_security_failure("ws_auth", "Invalid or missing WebSocket auth token/ticket")
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

            # ---- Voice ID: enroll a reference sample ----
            elif msg_type == "voice_enroll":
                audio_b64 = message.get("data")
                if not audio_b64:
                    await manager.send(json.dumps({"type": "voice_enroll_result", "success": False, "error": "No audio data"}), websocket)
                else:
                    try:
                        decoded = decode_webm_opus_b64_to_pcm(audio_b64, target_sample_rate=voice_id.TARGET_SAMPLE_RATE)
                        audio_np = pcm_int16_to_float32(decoded.pcm_int16)
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(None, voice_id.enroll, np.asarray(audio_np, dtype=np.float32), voice_id.TARGET_SAMPLE_RATE)
                    except Exception as e:
                        result = {"success": False, "error": str(e)}
                    await manager.send(json.dumps({"type": "voice_enroll_result", **result}), websocket)

            # ---- Voice ID: verify a sample against the enrolled profile ----
            elif msg_type == "voice_verify":
                audio_b64 = message.get("data")
                if not audio_b64:
                    await manager.send(json.dumps({"type": "voice_verify_result", "success": False, "error": "No audio data"}), websocket)
                else:
                    try:
                        decoded = decode_webm_opus_b64_to_pcm(audio_b64, target_sample_rate=voice_id.TARGET_SAMPLE_RATE)
                        audio_np = pcm_int16_to_float32(decoded.pcm_int16)
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(None, voice_id.verify, np.asarray(audio_np, dtype=np.float32), voice_id.TARGET_SAMPLE_RATE)
                    except Exception as e:
                        result = {"success": False, "error": str(e), "match": None}
                    await manager.send(json.dumps({"type": "voice_verify_result", **result}), websocket)

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
            # ---- Continuous conversation ("phone call") mode -- real
            # session tracking so a proactive push (see _send_or_queue) can
            # reach you live in the conversation, and so an idle session gets
            # ended server-side even if the client never says so. ----
            elif msg_type == "conversation_start":
                manager.start_conversation(websocket)
                logger.info("Continuous conversation mode started")

            elif msg_type == "conversation_end":
                manager.end_conversation(websocket)
                logger.info("Continuous conversation mode ended")

            elif msg_type in ("final_transcript", "user_text"):
                text = message.get("data", "")
                client_turn_id = message.get("turn_id")
                logger.info("Received %s: %s", msg_type, text[:80])
                manager.touch_conversation(websocket)

                # Real voice-match check for THIS turn -- only runs when the
                # frontend actually attached the raw audio it just captured
                # for this utterance (voice-originated turns only; a typed
                # message has no audio_b64 and skips this entirely) and a
                # profile is actually enrolled. Computed here, before the turn
                # starts, so _execute_file_tool's approval gate can read a
                # real result the instant a sensitive tool call needs it,
                # rather than trying to fetch/verify audio mid-tool-call.
                voice_match: Optional[Dict[str, Any]] = None
                speaker_profile_id: Optional[str] = None
                turn_audio: Optional[Any] = None
                audio_b64_for_turn = message.get("audio_b64")
                if audio_b64_for_turn:
                    try:
                        decoded = decode_webm_opus_b64_to_pcm(audio_b64_for_turn, target_sample_rate=voice_id.TARGET_SAMPLE_RATE)
                        turn_audio = np.asarray(pcm_int16_to_float32(decoded.pcm_int16), dtype=np.float32)
                        loop = asyncio.get_event_loop()
                        if voice_id.is_enrolled():
                            voice_match = await loop.run_in_executor(None, voice_id.verify, turn_audio, voice_id.TARGET_SAMPLE_RATE)
                            logger.info("Voice match for this turn: %s", voice_match)
                        if household_voice_id.PROFILES_DIR.exists():
                            # Real household-member identification -- this is
                            # a personalization signal (see
                            # _active_memory_manager), fully separate from
                            # voice_match above's security-approval role.
                            identified = await loop.run_in_executor(None, household_voice_id.identify_speaker, turn_audio, voice_id.TARGET_SAMPLE_RATE)
                            if identified:
                                speaker_profile_id = identified[0]
                                logger.info("Household speaker identified for this turn: %s (similarity=%s)", *identified)
                    except Exception as e:
                        logger.warning("Voice verification/identification failed for this turn: %s", e)
                        if voice_id.is_enrolled():
                            voice_match = {"success": False, "error": str(e), "match": None}

                # Fire-and-forget: start_turn cancels any still-running previous
                # turn and spawns this one as its own task, so the receive loop
                # stays free to read the next message immediately instead of
                # blocking on the LLM/TTS pipeline for this one. See
                # _run_chat_turn for the actual streaming generation + TTS work.
                manager.start_turn(
                    websocket,
                    lambda turn_id, _text=text, _vm=voice_match, _sp=speaker_profile_id, _ta=turn_audio: _run_chat_turn(websocket, turn_id, _text, _vm, _sp, _ta),
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

            elif msg_type == "register_device":
                # Real "which device is this" declaration for cross-device
                # follow-me (see set_active_device tool / broadcast_or_route).
                label = str(message.get("label", "")).strip()
                if label:
                    manager.register_device(websocket, label)

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

async def _telegram_image_command(args: str) -> str:
    """/image <description> -- real image generation (media_tools.generate_image,
    same provider registry the chat tool-use path uses), sent back to this
    Telegram chat as a real photo/document instead of only ever landing on
    the web dashboard's canvas."""
    prompt = args.strip()
    if not prompt:
        return "Usage: /image a description of what you want, e.g. <code>/image a golden retriever wearing sunglasses</code>"

    result = await generate_image(prompt)
    if not result.get("success"):
        from telegram_bot import _escape_html
        return f"⚠️ Image generation failed: {_escape_html(result.get('error', 'unknown error'))}"

    image_b64 = result.get("_image_base64")
    if image_b64:
        await telegram_notifier.send_document(base64.b64decode(image_b64), filename="generated.png", caption=prompt[:200])
        return "\U0001f3a8 Done."
    if result.get("url"):
        from telegram_bot import _escape_html
        return f"\U0001f3a8 Generated: {_escape_html(result['url'])}"
    return "\U0001f3a8 Generated, but couldn't retrieve the image data."


async def _telegram_recall_command(args: str) -> str:
    """/recall <topic> -- real semantic memory search (the same
    get_memory_context_string retrieval the chat pipeline uses to ground its
    own answers), surfaced directly instead of only ever being invisible
    context behind an LLM call."""
    from telegram_bot import _escape_html

    query = args.strip()
    if not query:
        return "Usage: /recall a topic or keyword, e.g. <code>/recall project roxan</code>"
    try:
        block = _active_memory_manager().get_memory_context_string(query, max_memories=6)
    except Exception as e:
        return f"⚠️ Memory search failed: {_escape_html(str(e))}"
    if not block.strip():
        return f"Nothing in memory matches “{_escape_html(query)}”, Sir."
    return f"\U0001f9e0 <b>Memory recall</b>\n\n{_escape_html(block)}"


async def _telegram_coworkers_command(args: str = "") -> str:
    """/coworkers -- real visibility into every delegate_to_coworker task,
    past and present, so 'a coworker is looking into that' is always
    checkable rather than a black box."""
    from telegram_bot import _escape_html

    if not _coworker_tasks:
        return "\U0001f465 No coworker tasks yet, Sir. Ask me to delegate something and I'll put someone on it."
    lines = ["\U0001f465 <b>Coworkers</b>", ""]
    icons = {"working": "⏳", "done": "✅", "failed": "⚠️"}
    for record in sorted(_coworker_tasks.values(), key=lambda r: r["started_at"], reverse=True)[:10]:
        icon = icons.get(record["status"], "❔")
        lines.append(f"{icon} {_escape_html(record['task'][:80])}")
    return "\n".join(lines)


async def _telegram_crypto_command(args: str = "") -> str:
    """/crypto -- real multi-coin market snapshot ranked by real 24h
    momentum (CryptoIntelligenceAgent), distinct from /markets (forex)."""
    from telegram_bot import _escape_html

    result = await agent_service.run("crypto_intelligence", {"type": "top_movers"}, timeout=20.0)
    if not result.get("success"):
        return f"\U0001f4b0 <b>Crypto</b>\n\nCouldn't fetch live data right now: {_escape_html(result.get('error', 'unknown error'))}"
    lines = ["\U0001f4b0 <b>Crypto snapshot</b>", ""]
    for s in result.get("all_ranked", []):
        arrow = "\U0001f4c8" if s["change_24h_pct"] > 0 else "\U0001f4c9" if s["change_24h_pct"] < 0 else "➡️"
        lines.append(f"{arrow} <b>{_escape_html(s['symbol'])}</b> ${s['price_usd']:,.2f} ({s['change_24h_pct']:+.2f}%)")
    return "\n".join(lines)


async def _telegram_drafts_command(args: str = "") -> str:
    """/drafts -- real pending product/ad-copy drafts from EcommerceResearchAgent,
    never auto-published (see product_drafts_store.py)."""
    from telegram_bot import _escape_html
    from product_drafts_store import product_drafts_store

    drafts = product_drafts_store.list()
    if not drafts:
        return "\U0001f4e6 No product drafts yet, Sir. Ask me to research trending products or draft a listing."
    lines = ["\U0001f4e6 <b>Product drafts</b>", ""]
    icons = {"draft": "\U0001f4dd", "pending_approval": "⏳", "approved": "✅", "rejected": "❌"}
    for d in drafts[:10]:
        icon = icons.get(d.status, "❔")
        price = f"${d.suggested_price_usd:.2f}" if d.suggested_price_usd else "no price yet"
        lines.append(f"{icon} <b>{_escape_html(d.title)}</b> ({price}) -- <code>{d.id}</code>")
    return "\n".join(lines)


async def _telegram_tasks_command(args: str = "") -> str:
    """/tasks -- real visibility into the last proactive orchestrator batch,
    so "every agent is always doing something" is checkable, not a claim
    taken on faith."""
    from telegram_bot import _escape_html

    result = await agent_service.run("task_orchestration", {"type": "status"}, timeout=10.0)
    last_batch = result.get("last_batch") if isinstance(result, dict) else None
    if not last_batch:
        return "\U0001f916 No proactive task batch has run yet, Sir -- the first one fires shortly after startup."
    lines = ["\U0001f916 <b>Last proactive task batch</b>", ""]
    for item in last_batch.get("results", [])[:10]:
        icon = "✅" if item.get("success") else "⚠️"
        lines.append(f"{icon} <b>{_escape_html(item.get('agent_key', '?'))}</b>: {_escape_html(item.get('task', '')[:100])}")
    return "\n".join(lines)


async def _telegram_status_command(args: str = "") -> str:
    """Real /status command reply -- reuses the exact same agent-fleet and
    open-trade data as the personalized greeting's system_status/
    active_trades fields (see _build_real_personal_context), just formatted
    as its own HTML message instead of woven into greeting prose."""
    from telegram_bot import _escape_html

    lines = ["\U0001f4cb <b>System status</b>", ""]
    try:
        if agent_service.is_ready():
            stats = agent_service.get_service_stats()
            lines.append(
                f"\U0001f7e2 {stats['agents_online']} agents online, "
                f"{stats['total_tasks']} tasks completed at a {stats['success_rate'] * 100:.0f}% success rate"
            )
            if stats.get("queued_tasks"):
                lines.append(f"⏳ {stats['queued_tasks']} tasks queued")
        else:
            lines.append("\U0001f7e1 Agent fleet still starting up")
    except Exception as e:
        lines.append(f"⚠️ Agent status unavailable: {_escape_html(str(e))}")

    try:
        open_trades = [t for t in trading_manager.trades if t.status == "open"]
        if open_trades:
            lines.append("")
            lines.append("<b>Open trades</b>")
            for t in open_trades:
                lines.append(f"• {_escape_html(t.pair)} {_escape_html(t.direction)} @ {t.entry_price}")
    except Exception as e:
        logger.debug("Telegram /status: trade data unavailable: %s", e)

    return "\n".join(lines)


async def _telegram_markets_command(args: str = "") -> str:
    """Real /markets command reply -- concurrently fetches live prices for
    every pair the user actually trades/watches (trading_manager.get_relevant_pairs()),
    same real data source and the same concurrency fix as
    _build_real_personal_context's market_alerts section."""
    from telegram_bot import _escape_html

    pairs = trading_manager.get_relevant_pairs()
    if not pairs:
        return "\U0001f4ca <b>Markets</b>\n\nNo pairs configured to watch yet, Sir."

    async def _one(pair: str) -> Optional[str]:
        try:
            snapshot = await forex_aggregator.get_price(pair)
            if not snapshot:
                return None
            arrow = "\U0001f4c8" if snapshot.change_24h > 0 else "\U0001f4c9" if snapshot.change_24h < 0 else "➡️"
            return f"{arrow} <b>{_escape_html(pair)}</b> {snapshot.price:.4f} ({snapshot.change_24h:+.2f}%)"
        except Exception as e:
            logger.debug("Telegram /markets: unavailable for %s: %s", pair, e)
            return None

    results = await asyncio.gather(*(_one(p) for p in pairs))
    lines = [r for r in results if r]
    if not lines:
        return "\U0001f4ca <b>Markets</b>\n\nLive prices aren't reachable right now, Sir."
    return "\U0001f4ca <b>Markets</b>\n\n" + "\n".join(lines)


async def _telegram_chat_handler(text: str) -> str:
    """Routes a Telegram message through the same chat pipeline the voice/web
    UI uses, so 'chat with Billion from Telegram' means the same Billion --
    same context history, same agent routing, same LLM fallback chain.
    channel="telegram" gets it the text-chat system-prompt style (real depth
    on informational questions, "Sir" used sparingly rather than constantly)
    instead of the voice-first brevity default."""
    response, debug = await _generate_response_via_hierarchy(text, channel="telegram")
    await _history_add({"role": "user", "content": f"[telegram] {text}"})
    await _history_add({"role": "assistant", "content": response})
    # Real conversation sync -- the web/voice UI sees this reply too
    # (including any real image a tool call produced), not just whichever
    # channel happened to receive the message. Fire-and-forget: this must
    # never delay or break the reply Telegram itself is about to send.
    asyncio.create_task(_broadcast_reply_to_web(response, debug.get("images"), source="telegram"))
    # A screenshot/generated image a tool call produced during THIS Telegram
    # conversation used to only ever reach the web dashboard (via the
    # broadcast above), never the Telegram chat that actually asked for it --
    # confirmed live, a computer-use screenshot or an image-generation tool
    # call from Telegram produced a real image nobody on Telegram ever saw.
    # Sent as its own message after the text reply (Telegram's caption limit
    # is much shorter than a real detailed reply can run).
    images = debug.get("images") or []
    for image_bytes in images:
        asyncio.create_task(telegram_notifier.send_document(image_bytes, filename="capture.png"))
    return response


def _omniroute_host_port() -> tuple[str, int]:
    from urllib.parse import urlparse
    parsed = urlparse(os.getenv("OMNIROUTE_URL", "http://localhost:20128"))
    return parsed.hostname or "localhost", parsed.port or 20128


async def _ensure_omniroute_running() -> None:
    """Auto-launches the OmniRoute gateway (see OmniRouteLLM in llm.py) as
    its own independent background process if it isn't already listening,
    so starting THIS backend is enough on its own -- no separate manual
    `omniroute` terminal needed every time.

    On Windows this goes through WMI (Win32_Process.Create) rather than a
    plain subprocess.Popen, however "detached" -- confirmed live, in order,
    that (1) `omniroute serve --daemon`'s own internal fork-and-detach
    didn't survive being spawned from Python at all, and (2) even a plain
    `omniroute serve --no-open` spawned with BOTH DETACHED_PROCESS and
    CREATE_BREAKAWAY_FROM_JOB still got killed the moment the spawning
    shell's own job closed, because this backend runs under Git Bash/MSYS2,
    which assigns every child it spawns to a Windows Job Object -- and
    CREATE_BREAKAWAY_FROM_JOB only works if THAT job explicitly allows
    breakaway, which MSYS2's doesn't. WMI's Win32_Process.Create asks the
    WMI provider host service (a completely separate OS process, outside
    any job this backend belongs to) to create the process instead, so the
    result has no job-object relationship to this backend at all -- verified
    live to survive independently and answer real requests. Falls back to a
    plain detached Popen on non-Windows (no Job Object concept there).
    Best-effort and non-blocking either way: a failure here just means the
    LLM chain falls through to the backends below OmniRoute, exactly as if
    DISABLE_OMNIROUTE=1 were set -- never raises."""
    if os.getenv("DISABLE_OMNIROUTE", "0").strip() == "1":
        return
    import shutil
    import socket
    import subprocess

    host, port = _omniroute_host_port()
    try:
        with socket.create_connection((host, port), timeout=1.0):
            logger.info("OmniRoute already running at %s:%d", host, port)
            return
    except OSError:
        pass  # not reachable yet -- launch it below

    omniroute_cmd = shutil.which("omniroute")
    if not omniroute_cmd:
        logger.warning(
            "OmniRoute not found on PATH (npm install -g omniroute) -- "
            "the LLM chain will skip it and fall through to the backends below."
        )
        return

    loop = asyncio.get_event_loop()
    try:
        if os.name == "nt":
            def _launch_via_wmi():
                cmd_line = f'cmd /c "{omniroute_cmd}" serve --no-open'
                ps_script = (
                    "Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
                    f"-Arguments @{{CommandLine='{cmd_line}'}}"
                )
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", ps_script],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                    timeout=15,
                )
            await loop.run_in_executor(None, _launch_via_wmi)
            logger.info("Launched OmniRoute gateway via WMI process creation")
        else:
            subprocess.Popen(
                [omniroute_cmd, "serve", "--no-open"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            logger.info("Launched OmniRoute gateway as a detached background process")
    except Exception as e:
        logger.warning("Failed to auto-launch OmniRoute: %s", e)


def _seed_default_cron_jobs() -> None:
    """First-run only: schedules the maintenance blueprints that make the
    Memory Insights Dreams and Wiki tabs self-populating, instead of
    requiring the user to discover and manually fill them in via Cron Jobs
    -> Blueprints. Guarded on action_type already existing so re-running
    this on every restart never duplicates a job the user has since edited
    or re-timed -- same one-shot-seed idiom as _last_real_activity_at above."""
    existing_action_types = {j.action_type for j in cron_store.list()}
    for key in ("memory-dreaming", "commitment-checkin"):
        blueprint = get_blueprint(key)
        if blueprint is None:
            continue
        try:
            spec = fill_blueprint(blueprint, {})
        except BlueprintFillError as e:
            logger.warning("_seed_default_cron_jobs: failed to fill blueprint %r: %s", key, e)
            continue
        if spec["action_type"] in existing_action_types:
            continue
        cron_store.create(
            spec["name"], spec["description"], 0, 0, spec["action_type"], spec["action_payload"],
            cron_expression=spec["cron_expression"],
        )
        logger.info("_seed_default_cron_jobs: scheduled default job for blueprint %r", key)


@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()
    _seed_default_cron_jobs()
    logger.info("Nancy/Billion backend starting up...")
    asyncio.create_task(_ensure_omniroute_running())
    # Initialise all 29 specialized agents in background so startup is fast
    asyncio.create_task(_init_agents())
    telegram_notifier.set_chat_handler(_telegram_chat_handler)
    telegram_notifier.set_command_handler("status", _telegram_status_command)
    telegram_notifier.set_command_handler("markets", _telegram_markets_command)
    telegram_notifier.set_command_handler("image", _telegram_image_command)
    telegram_notifier.set_command_handler("recall", _telegram_recall_command)
    telegram_notifier.set_command_handler("coworkers", _telegram_coworkers_command)
    telegram_notifier.set_command_handler("tasks", _telegram_tasks_command)
    telegram_notifier.set_command_handler("crypto", _telegram_crypto_command)
    telegram_notifier.set_command_handler("drafts", _telegram_drafts_command)
    telegram_notifier.set_image_broadcaster(
        lambda image_bytes, caption: _broadcast_reply_to_web("", [image_bytes], source="telegram")
    )
    telegram_notifier.start_polling()
    # _last_real_activity_at defaults to 0.0 at module load, which makes
    # quiet_for (= now - _last_real_activity_at) a huge number until the
    # first real chat turn ever sets it -- defeating the proactive/training
    # loops' whole quiet-period check on the FIRST cycle after every restart.
    # Confirmed live: a fresh restart's proactive_agent_loop cycle (fires at
    # its fixed 120s post-boot delay regardless) landed squarely on top of a
    # real live chat request, both competing for the same CPU NeuTTS needs --
    # exactly the contention class this gate exists to prevent, just missed
    # on cycle one. Seeding it to "now" at startup makes the first cycle
    # respect real activity too, not just every cycle after it.
    global _last_real_activity_at
    _last_real_activity_at = _time.time()
    asyncio.create_task(_daily_briefing_loop())
    asyncio.create_task(_cron_execution_loop())
    asyncio.create_task(_self_healing_loop())
    asyncio.create_task(_self_maintenance_loop())
    asyncio.create_task(_proactive_agent_loop())
    asyncio.create_task(_fleet_sweep_loop())
    asyncio.create_task(_model_training_loop())
    # Both loops above only run their first real check after a full sleep
    # interval (5min / 24h by default) -- populate real initial statuses
    # immediately so the alert dashboard reflects reality from boot instead
    # of sitting empty for hours.
    asyncio.create_task(_update_system_health_status())
    asyncio.create_task(_update_dependency_vuln_status())
    asyncio.create_task(_pattern_suggestions_loop())
    asyncio.create_task(_presence_loop())
    asyncio.create_task(_subsystem_activity_loop())
    asyncio.create_task(_meeting_prep_loop())
    asyncio.create_task(_conversation_idle_watchdog())
    asyncio.create_task(_watch_execution_loop())
    asyncio.create_task(_economic_calendar_loop())
    asyncio.create_task(_screen_context_loop())
    asyncio.create_task(_prewarm_tts())
    asyncio.create_task(_prewarm_memory_embeddings())
    asyncio.create_task(mcp_manager.connect_all())


async def _prewarm_tts() -> None:
    """Every local TTS engine here pays a real one-time cold-start on its
    first synthesis, and it's large enough to matter: Piper's first call
    pays ONNX Runtime warmup (measured ~13s, vs ~0.5s for every call after);
    NeuTTS's constructs a GGUF backbone + ONNX codec from scratch and has
    been measured past 60s on this hardware. Paying that once here, at
    startup, means the user's actual first message doesn't have to."""
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


async def _conversation_idle_watchdog() -> None:
    """Server-side safety net for continuous conversation mode -- the client
    already ends a session on an exit phrase or explicit toggle, but a tab
    crash or lost connection would otherwise leave it marked active forever
    (has_active_conversation() would then wrongly keep routing proactive
    pushes into a dead session below). Ends any session idle longer than
    CONVERSATION_IDLE_TIMEOUT_SECONDS (default 120s) and tells the client so,
    mirroring the client's own "like a phone call" framing -- silence long
    enough eventually hangs up from either end."""
    timeout = float(os.getenv("CONVERSATION_IDLE_TIMEOUT_SECONDS", "120"))
    while True:
        await asyncio.sleep(15)
        now = _time.time()
        for ws, last in list(manager.conversation_last_activity.items()):
            if now - last <= timeout:
                continue
            manager.end_conversation(ws)
            try:
                await ws.send_text(json.dumps({"type": "conversation_ended", "reason": "idle_timeout"}))
            except Exception:
                pass


async def _send_or_queue(text: str) -> None:
    """The one chokepoint every INFORMATIONAL proactive push (self-healing
    status, watch alerts, scheduled telegram_message cron jobs) routes
    through -- sends immediately unless focus_mode is active, in which case
    it queues instead and delivers as part of one consolidated digest when
    focus mode ends. Approval requests never go through this: they're
    genuinely blocking work, not ambient noise, so they always call
    telegram_notifier.request_approval directly and arrive right away.

    Also mirrored live into any active continuous-conversation session (see
    ConnectionManager.has_active_conversation) regardless of focus_mode --
    being mid-conversation with Billion right now is a much stronger presence
    signal than focus_mode's "away/busy" assumption, so a proactive update
    should actually reach you there instead of silently queuing for later."""
    if focus_mode.is_active():
        focus_mode.queue_message(text)
    else:
        await telegram_notifier.send(text)
    if manager.has_active_conversation():
        await _broadcast_reply_to_web(text, source="proactive")


async def _meeting_prep_loop() -> None:
    """Checks real upcoming Google Calendar events every
    MEETING_PREP_INTERVAL_MINUTES (default 5), and for any event starting
    within MEETING_PREP_LEAD_MINUTES (default 20) that hasn't been prepped
    yet, runs a real web search on its topic and posts real notes to the
    canvas plus one Telegram heads-up -- the "Sir, I've taken the liberty
    of..." move, unprompted. No-ops entirely when Google Calendar isn't
    configured, and never re-preps the same event (see meeting_prep_store)."""
    interval = float(os.getenv("MEETING_PREP_INTERVAL_MINUTES", "5")) * 60.0
    lead_s = float(os.getenv("MEETING_PREP_LEAD_MINUTES", "20")) * 60.0
    while True:
        await asyncio.sleep(interval)
        if not google_calendar.is_configured():
            continue
        try:
            result = await google_calendar.list_events(max_results=10)
            if not result.get("success"):
                continue
            now = _time.time()
            for event in result.get("events", []):
                event_id = event.get("id")
                start_str = event.get("start")
                if not event_id or not start_str:
                    continue
                if meeting_prep_store.already_prepped(event_id):
                    continue
                try:
                    start_ts = datetime.fromisoformat(start_str).timestamp()
                except Exception:
                    continue
                if not (now <= start_ts <= now + lead_s):
                    continue

                summary = event.get("summary") or "your upcoming meeting"
                search_result = await web_search(summary, max_results=5)
                if search_result.get("success") and search_result.get("results"):
                    lines = [f"- {r.get('title', '')}: {r.get('url', '')}" for r in search_result["results"][:5]]
                    note = f"Prep notes for: {summary}\n\n" + "\n".join(lines)
                    try:
                        item = canvas_store.create("note", f"Prep: {summary}", note)
                        await event_bus.publish("CANVAS_ITEM_ADDED", {"item": item.to_public_dict()})
                    except ValueError:
                        pass
                    await telegram_notifier.send(
                        f"Sir, I've taken the liberty of prepping some background for your upcoming "
                        f"meeting: {summary}. Notes are on your canvas."
                    )
                else:
                    await telegram_notifier.send(f"Heads up, Sir -- {summary} is starting soon.")
                meeting_prep_store.mark_prepped(event_id)
        except Exception:
            logger.exception("Meeting prep loop failed")


async def _subsystem_activity_loop() -> None:
    """Broadcasts live per-subsystem activity so the Orb's rings reflect real
    system state (Book VI Ch.7), not fixed timers.

    2Hz: fast enough that a ring visibly responds to a real agent task or
    memory write, slow enough to be negligible on a socket that already
    carries audio. Health and network are sampled here rather than poked,
    since they are continuous conditions rather than discrete events.
    """
    from subsystem_activity import subsystem_activity

    while True:
        await asyncio.sleep(0.5)
        try:
            if not manager.active_connections:
                continue  # nobody watching -- don't do the work
            # Health: real psutil state, inverted so "unhealthy" lights the ring.
            try:
                health = system_monitor.get_comprehensive_health()
                status = health.get("overall_status", "healthy")
                subsystem_activity.set_level("health", {"healthy": 0.0, "warning": 0.55}.get(status, 0.95))
            except Exception:
                pass
            # Network: real connected clients.
            if manager.active_connections:
                subsystem_activity.set_level("network", min(1.0, 0.15 * len(manager.active_connections)))
            await manager.broadcast(json.dumps({
                "type": "subsystem_activity",
                "levels": subsystem_activity.snapshot(),
                "quiet": subsystem_activity.is_quiet(),
            }))
        except Exception:
            logger.debug("subsystem activity broadcast failed", exc_info=True)


async def _presence_loop() -> None:
    """Real periodic LAN presence check (default every 3 min) for every
    registered device -- pings it, detects real arrive/leave TRANSITIONS
    (not every unchanged check), notifies once per transition, and runs
    that device's own on_arrive_macro/on_leave_macro if one's set (the real
    'if I'm home, dim the lights' conditional trigger)."""
    interval = float(os.getenv("PRESENCE_CHECK_INTERVAL_MINUTES", "3")) * 60.0
    while True:
        await asyncio.sleep(interval)
        try:
            for device in presence_store.presence_store.list():
                try:
                    result = await network_tools.ping_host(device.host, count=1)
                    now_present = bool(result.get("success") and result.get("reachable"))
                    was_present = device.present
                    presence_store.presence_store.record_check(device.id, now_present)
                    if now_present == was_present:
                        continue
                    if now_present:
                        await _send_or_queue(f"{device.person_name} just got home, Sir.")
                        macro_name = device.on_arrive_macro
                    else:
                        await _send_or_queue(f"{device.person_name} just left, Sir.")
                        macro_name = device.on_leave_macro
                    if macro_name:
                        macro = macro_store.macro_store.find_by_name(macro_name)
                        if macro:
                            await _run_macro(macro)
                except Exception:
                    logger.exception("Presence check for device %s failed", device.id)
        except Exception as e:
            logger.exception("Presence loop failed: %s", e)


async def _update_dependency_vuln_status() -> str:
    """Real current-state check against self_maintenance's live OSV.dev
    query -- distinct from run_periodic_check's "new vulns only" Telegram
    messaging above: this reflects the FULL current truth (auto-resolves to
    green the moment a flagged package is upgraded), which is what a status
    dashboard needs and a "don't re-notify" message log doesn't. Returns the
    resulting severity so callers can drive a matching orb pulse."""
    result = await self_maintenance.check_dependency_vulnerabilities()
    if not result.get("success"):
        return "red"
    vulns = result.get("vulnerabilities", [])
    if vulns:
        detail = "; ".join(
            f"{v['package']}=={v['version']} ({', '.join(v['vuln_ids'])})" for v in vulns[:5]
        )
        if len(vulns) > 5:
            detail += f"; and {len(vulns) - 5} more"
        _update_alert_status(
            key="dependency_vulnerabilities", category="security",
            title=f"{len(vulns)} dependency vulnerability(ies) found", severity="red", detail=detail,
        )
        return "red"
    _update_alert_status(
        key="dependency_vulnerabilities", category="security",
        title="No known dependency vulnerabilities", severity="green",
        detail=f"{result.get('packages_checked', 0)} pinned package(s) checked against OSV.dev.",
    )
    return "green"


async def _update_system_health_status() -> str:
    """Real psutil-backed check (system_monitor.py, the same instance
    /system/health reports from) mapped straight onto the three real states
    it already computes -- healthy/warning/error become green/yellow/red,
    no new thresholds invented here. Also reflects the primary LLM backend's
    real success/failure record (usage_analytics.json) as its own category,
    since a paid-backend outage is a genuine operational concern distinct
    from CPU/memory/disk. Returns the worse of the two resulting severities
    so callers can drive a matching orb pulse."""
    health = system_monitor.get_comprehensive_health()
    overall = health.get("overall_status", "healthy")
    severity = {"healthy": "green", "warning": "yellow", "error": "red"}.get(overall, "yellow")
    alerts = system_monitor.should_trigger_alert(health)
    detail = "; ".join(alerts) if alerts else "CPU, memory, disk, and network are all within normal range."
    _update_alert_status(
        key="system_health", category="system", title="System resource health", severity=severity, detail=detail,
    )

    backend_healthy, last_error = self_healing.check_primary_backend()
    backend_severity = "green" if backend_healthy else "yellow"
    _update_alert_status(
        key="llm_backend", category="system",
        title=f"Primary reasoning backend ({self_healing._primary_backend_name()})",
        severity=backend_severity,
        detail="Operating normally." if backend_healthy else f"Down, running on a fallback backend instead. {last_error or ''}".strip(),
    )
    rank = {"green": 0, "yellow": 1, "red": 2}
    return severity if rank[severity] >= rank[backend_severity] else backend_severity


# ---------------------------------------------------------------------------
# Proactive agents -- every specialized agent gets real, periodic work to do
# instead of sitting idle until directly invoked. This was an explicit,
# repeated complaint: an agent that's "active" but never actually does
# anything unless called on is functionally decorative.
#
# TaskOrchestratorAgent (agents/specialized/task_orchestrator_agent.py) is
# the real engine: each cycle it proposes a batch of concrete, genuinely
# useful tasks against the real agent roster and runs them CONCURRENTLY via
# agent_service.run(), so one cycle covers several agents at once rather
# than one agent reflecting alone -- a materially faster path to "every
# agent has actually done real work recently" than checking in on agents
# one at a time.
#
# Still deliberately bounded on two axes, both learned the hard way earlier
# this session: TaskOrchestratorAgent caps a batch at a handful of tasks
# (not all ~60+ agents at once), and everything here runs through LOCAL-ONLY
# Ollama (_proactive_local_llm) rather than the global llm_backend fallback
# chain. Real user chat requests already fight through Gemini's exhausted
# free-tier quota and Anthropic's zero credit balance before landing on
# Groq/OpenRouter -- adding continuous background agent activity to that
# SAME shared budget would make real replies slower and more likely to
# fail, exactly the problem this session spent hours fixing. Local Ollama
# inference costs no API quota and doesn't compete for it, at the honest
# cost of a much slower per-call turnaround and lower answer quality -- an
# acceptable trade for background work that isn't blocking a live
# conversation.
# ---------------------------------------------------------------------------
PROACTIVE_AGENT_INTERVAL_S = float(os.getenv("PROACTIVE_AGENT_INTERVAL_S", "600"))  # 10 min
# Briefly lowered to 240s (with a 12-task batch) to get the 70-agent fleet
# exercised faster after "almost all agents show 0 completed tasks". That
# was reverted: the combination measurably starved Piper TTS of CPU (same
# text: ~1s idle vs 47s under proactive load). The quiet gate below only
# checks BEFORE a cycle starts, so a cycle that begins just before the user
# speaks still competes with them for the whole batch -- which makes an
# aggressive interval genuinely costly, not free. Slower fleet coverage is
# the right trade for a voice-first assistant.
# How recently the user must have been genuinely chatting (any channel --
# see _generate_response_via_hierarchy, the real chokepoint every chat
# caller goes through) before a proactive cycle backs off instead of
# running. Confirmed live: this system's own local-Ollama proactive work is
# genuinely CPU-heavy, and running it while the user is actively talking to
# Nancy competes for the exact same CPU NeuTTS needs to synthesize speech in
# real time -- precisely the class of self-inflicted contention this
# session spent hours fixing for Docker/wake-word. Skipping (not just
# delaying) a cycle here means a burst of chat activity never gets queued
# up behind it either.
PROACTIVE_QUIET_AFTER_ACTIVITY_S = float(os.getenv("PROACTIVE_QUIET_AFTER_ACTIVITY_S", "90"))
_last_real_activity_at: float = 0.0


async def _proactive_local_llm(prompt: str, max_tokens: int = 200) -> Optional[str]:
    """LLM call for background agent work. Goes through the normal
    llm_backend chain (Groq-first cloud, with local Ollama still present as
    its own last-resort link) rather than pinning to local Ollama directly.

    This deliberately REVERSES the original design, which forced local-only
    inference to avoid competing with the user's chat for cloud API quota.
    Confirmed live on this machine that the trade was backwards: local
    inference spawns llama-server, which saturates every core (measured at
    300+ CPU-seconds), and CPU is exactly what Piper TTS needs to speak. The
    effect was measured directly -- with llama-server ramping up, the SAME
    TTS text degraded 15s -> 19s -> 36s -> 47s across four consecutive
    calls, against ~1s on an idle CPU. Cloud quota is replaceable; the
    responsiveness of a voice-first assistant is the product. Returns None
    (never raises) if every backend fails; the caller just skips that cycle."""
    try:
        return await asyncio.wait_for(
            llm_backend.generate(prompt, max_tokens=max_tokens, temperature=0.4), timeout=90.0,
        )
    except Exception as e:
        logger.debug("Proactive LLM call unavailable: %s", e)
        return None


async def _proactive_agent_loop() -> None:
    """Runs TaskOrchestratorAgent's real generate-and-delegate cycle on a
    schedule: it proposes concrete tasks against the real agent roster,
    validates each against real agent keys, and runs them concurrently.
    Every genuinely useful finding gets written to the same memory graph
    the chat pipeline's get_memory_context_string reads from, so it's
    already there the next time the user asks about it -- not just a log
    line nobody sees."""
    await asyncio.sleep(120)  # let the rest of startup (agent init, etc.) settle first
    while True:
        try:
            quiet_for = _time.time() - _last_real_activity_at
            if agent_service.is_ready() and quiet_for >= PROACTIVE_QUIET_AFTER_ACTIVITY_S:
                result = await agent_service.run(
                    "task_orchestration", {"type": "generate_and_delegate"}, timeout=180.0,
                )
                if result.get("success"):
                    for item in result.get("results", []):
                        if not (item.get("success") and item.get("result")):
                            continue
                        try:
                            memory_manager.graph.add_or_merge_memory(
                                f"[{item['agent_key']}] {item['result']}",
                                MemoryType.INSIGHT,
                                {"source": "proactive_orchestrator", "agent_key": item["agent_key"]},
                                importance=0.4,
                                # Free-text LLM output with no tool behind it.
                                # RECALLED is capped at 0.4 and the write is
                                # refused outright if it claims a measurement.
                                confidence=0.4, provenance="recalled",
                                source=f"agent:{item['agent_key']}",
                            )
                        except UntrustedMemoryRejected as e:
                            # The Trust guard working as designed, not a fault.
                            logger.info("Proactive finding from %s not stored: %s", item.get("agent_key"), e)
                        except Exception:
                            logger.exception("Failed to record proactive finding from %s", item.get("agent_key"))
                    logger.info("Proactive orchestrator cycle: %d task(s) run", result.get("tasks_run", 0))
                else:
                    logger.debug("Proactive orchestrator cycle produced nothing usable: %s", result.get("error"))
        except Exception:
            logger.exception("Proactive agent cycle failed")
        await asyncio.sleep(PROACTIVE_AGENT_INTERVAL_S)


# --- Fleet sweep -----------------------------------------------------------
# Guarantees every agent actually does real work on a rotation, which
# _proactive_agent_loop above provably does NOT: measured live, 60 of 70
# agents still had a task count of zero, because that loop asks an LLM to
# INVENT a handful of tasks each cycle and the model kept proposing the same
# obvious few agents. At 4 tasks per 10 minutes, gated behind a 90s
# user-idle check, full coverage needed ~3 hours of uninterrupted idle time
# and so never happened.
#
# This loop is deterministic instead of model-chosen: it takes the
# least-recently-used agents, hands each a real task built from its OWN
# declared domain and specializations, and writes genuine findings to the
# same memory graph the chat pipeline reads from. No LLM call is spent
# deciding what to run, and no agent can be skipped forever.
FLEET_SWEEP_INTERVAL_S = float(os.getenv("FLEET_SWEEP_INTERVAL_S", "120"))  # 2 min
FLEET_SWEEP_BATCH = int(os.getenv("FLEET_SWEEP_BATCH", "5"))
# Agents whose "run something useful now" is meaningless or self-referential.
_FLEET_SWEEP_SKIP = {"task_orchestration", "dispatcher", "planning", "model_training"}


# Real, parameterless, READ-ONLY task types an agent can be asked to run
# autonomously, in preference order. Deliberately an allowlist, not a
# blocklist: agents also expose genuinely mutating types (deploy, encrypt,
# train, run_cycle, control, project_hologram) that must never be fired by a
# background sweep. Everything here either reports the agent's own real
# state or performs a real read-only lookup.
_SWEEP_SAFE_TASK_TYPES = (
    "status", "public_ip", "market_snapshot", "top_movers", "list_registry",
    "list_drafts", "list-indicators", "inspect",
    # New topic-coverage agents' real parameterless read-only task types
    # (forex_intelligence, automotive_specs, football_intelligence,
    # basketball_intelligence) -- market_snapshot above already covers
    # forex_intelligence for free.
    "today_fixtures", "today_games", "list_makes",
    # timezone_scheduling's current_time with no 'place' arg -- a genuine
    # parameterless real check (the server's own local clock), same as
    # public_ip above.
    "current_time",
)


def _agent_supported_task_types(agent: Any) -> set:
    """The task types an agent's own process_task actually dispatches on,
    read from its source. Agents declare these as `task_type == "..."`
    comparisons rather than in any registry, so this is the only honest way
    to know what a given agent can really be asked to do."""
    try:
        import inspect as _inspect

        src = _inspect.getsource(type(agent).process_task)
    except Exception:
        return set()
    return set(re.findall(r'task_type\s*==\s*["\']([a-z_0-9\-]+)["\']', src))


def _fleet_sweep_real_task_for(agent: Any) -> Optional[Dict[str, Any]]:
    """Picks a REAL, safe, parameterless task for this agent, or None if it
    has none. Returning None is the correct outcome for a pure calculator
    (loan amortisation, timezone conversion) that has nothing autonomous to
    do without user-supplied inputs -- far better than inventing inputs or
    dropping to the LLM.

    "status" is deliberately tried LAST, not in its tuple position (index 0
    in _SWEEP_SAFE_TASK_TYPES). Confirmed live: nearly every agent also
    implements a "status" task type alongside its real one (market_snapshot,
    public_ip, inspect, ...), and the original first-match-in-tuple-order
    scan returned "status" for all of them every single sweep -- the more
    specific, more valuable task types later in the tuple were structurally
    unreachable for any agent that also has a status handler, which is
    nearly all of them. This is the real reason fleet sweep mostly produced
    trivial liveness pings instead of genuine domain work."""
    supported = _agent_supported_task_types(agent)
    for candidate in _SWEEP_SAFE_TASK_TYPES:
        if candidate != "status" and candidate in supported:
            return {"type": candidate}
    if "status" in supported:
        return {"type": "status"}
    return None


def _fleet_sweep_task_for(info: Dict[str, Any]) -> str:
    """Builds a real, domain-appropriate task from an agent's own declared
    capabilities -- no LLM needed to decide what a specialist should look
    into, since the agent already describes its own specialization."""
    domain = str(info.get("domain") or info.get("key") or "your field").replace("-", " ")
    specializations = info.get("specializations") or []
    focus = f", focusing on {specializations[0].replace('-', ' ')}" if specializations else ""
    return (
        f"Autonomous check in your domain of {domain}{focus}.\n\n"
        f"CRITICAL -- READ CAREFULLY. You have NOT run any tool, taken any measurement, read any "
        f"sensor, or queried any live system for this request. You are working from your own "
        f"trained knowledge ONLY. Therefore you must NEVER invent a measurement or statistic. Do "
        f"not report a temperature, a decibel level, a percentage, a latency, a price, a count, "
        f"or any other number as though you had just measured it -- you did not, and a fabricated "
        f"figure written into long-term memory becomes a lie the user is later told as fact.\n\n"
        f"Report ONE durable, genuinely-true piece of domain knowledge that would be useful to "
        f"recall later -- a stable principle, threshold, standard, best practice, or well-"
        f"established fact in {domain}. Something that was equally true last week and will be "
        f"true next month. State it plainly in one or two sentences.\n\n"
        f"If you cannot produce something that meets that bar without inventing anything, reply "
        f"with exactly: NOTHING TO REPORT. That is a perfectly good answer and is strongly "
        f"preferred over a plausible-sounding fabrication."
    )


# Phrases that betray a fabricated live measurement in sweep output (see
# _fleet_sweep_task_for). Confirmed live: agents asked for "a real finding"
# invented things like "the ambient noise floor is approximately 18.72
# decibels" and "a 3.2% improvement, median 4.7 seconds" without having
# measured anything at all. Long-term memory must never absorb those.
_FABRICATED_MEASUREMENT_MARKERS = (
    "i've just checked", "i just checked", "i've just measured", "i just measured",
    "i've been running diagnostics", "currently operating", "right now is approximately",
    "current reading", "i've just run", "i just ran", "i've just scanned", "i just scanned",
)


def _looks_fabricated(text: str) -> bool:
    """True if the text claims a live measurement the agent could not have taken."""
    return any(m in text.lower() for m in _FABRICATED_MEASUREMENT_MARKERS)


async def _fleet_sweep_loop() -> None:
    """Rotates real work through the whole agent fleet, least-used first."""
    await asyncio.sleep(90)  # let agent init settle
    while True:
        try:
            quiet_for = _time.time() - _last_real_activity_at
            if agent_service.is_ready() and quiet_for >= PROACTIVE_QUIET_AFTER_ACTIVITY_S:
                roster = [
                    a for a in agent_service.list_agents()
                    if a.get("key") not in _FLEET_SWEEP_SKIP and a.get("status") != "offline"
                ]
                roster.sort(key=lambda a: (a.get("total_tasks", 0) or 0))

                # Only agents that expose a REAL, safe, parameterless task.
                # An agent with none (a pure calculator awaiting user inputs)
                # is skipped outright rather than handed a generic prose
                # prompt -- see _fleet_sweep_real_task_for.
                candidates: List[tuple] = []
                for info in roster:
                    agent = agent_service._agents.get(info.get("key"))
                    if agent is None:
                        continue
                    task = _fleet_sweep_real_task_for(agent)
                    if task is not None:
                        candidates.append((info, task))
                    if len(candidates) >= FLEET_SWEEP_BATCH:
                        break

                async def _sweep_one(info: Dict[str, Any], task: Dict[str, Any]) -> None:
                    key = info.get("key")
                    try:
                        result = await agent_service.run(key, task, timeout=60.0)
                    except Exception as e:
                        logger.debug("Fleet sweep: %s raised: %s", key, e)
                        return
                    if not isinstance(result, dict) or result.get("success") is False:
                        return
                    # Real structured output from a real capability -- record
                    # the actual returned data, not prose about it.
                    payload = {k: v for k, v in result.items() if k not in ("success", "response")}
                    finding = json.dumps(payload, default=str)[:1200] if payload else ""
                    if not finding or finding in ("{}", "null"):
                        return
                    try:
                        memory_manager.graph.add_or_merge_memory(
                            f"[{key}] {task['type']} -> {finding}",
                            MemoryType.INSIGHT,
                            {
                                "source": "fleet_sweep", "agent_key": key,
                                "task_type": task["type"], "verified": True,
                            },
                            importance=0.35,
                            # This branch only ever stores an agent's real
                            # structured capability output (status, list_registry,
                            # public_ip...), never free-text -- so it is a genuine
                            # observation of system state.
                            confidence=0.85, provenance="measured",
                            source=f"agent:{key}.{task['type']}",
                        )
                    except UntrustedMemoryRejected as e:
                        logger.info("Fleet sweep finding from %s not stored: %s", key, e)
                    except Exception:
                        logger.exception("Fleet sweep: failed to record finding from %s", key)

                if candidates:
                    await asyncio.gather(*(_sweep_one(i, t) for i, t in candidates))
                    logger.info(
                        "Fleet sweep: ran real tasks -> %s",
                        ", ".join(f"{i.get('key')}({t['type']})" for i, t in candidates),
                    )
        except Exception:
            logger.exception("Fleet sweep cycle failed")
        await asyncio.sleep(FLEET_SWEEP_INTERVAL_S)


MODEL_TRAINING_INTERVAL_S = float(os.getenv("MODEL_TRAINING_INTERVAL_S", str(6 * 3600)))  # every 6 hours


async def _model_training_loop() -> None:
    """Runs ModelTrainingAgent's full real lifecycle (dataset export from
    actual conversations, MLAgent classifier retraining, and a real
    personalized local Ollama model refresh) on its own schedule --
    heavier and far less frequent than the generic per-agent proactive
    check-in above, since this does substantive real work (actually
    training a model) rather than a quick reflection."""
    await asyncio.sleep(300)  # let real conversation data accumulate before the first run
    while True:
        try:
            quiet_for = _time.time() - _last_real_activity_at
            # Same CPU-contention reasoning as _proactive_agent_loop -- this
            # cycle is heavier (real classifier retraining + an Ollama
            # /api/create call), so it's worth the same quiet-window check
            # even though its own interval is already hours apart.
            if agent_service.is_ready() and quiet_for >= PROACTIVE_QUIET_AFTER_ACTIVITY_S:
                result = await agent_service.run("model_training", {"type": "run_cycle"}, timeout=300.0)
                logger.info("Model training cycle finished: %s", result.get("success") if isinstance(result, dict) else result)
        except Exception:
            logger.exception("Model training cycle failed")
        await asyncio.sleep(MODEL_TRAINING_INTERVAL_S)


async def _pattern_suggestions_loop() -> None:
    """Weekly (default) scan for real recurring topics in the memory graph
    worth suggesting automation for -- see pattern_suggestions.py. Only ever
    surfaces topics it hasn't already suggested, so this can't nag about the
    same recurring thing every week forever."""
    interval = float(os.getenv("PATTERN_SUGGESTIONS_INTERVAL_HOURS", "168")) * 3600.0  # 168h = 1 week
    while True:
        await asyncio.sleep(interval)
        try:
            suggestions = pattern_suggestions.get_new_suggestions(memory_manager.graph)
            for suggestion in suggestions:
                await _send_or_queue(pattern_suggestions.format_suggestion(suggestion))
        except Exception:
            logger.exception("Pattern suggestions loop failed")


async def _self_maintenance_loop() -> None:
    """Runs self_maintenance's dependency-vulnerability check once a day
    (default), notifying (via _send_or_queue, so focus mode still applies)
    only about real, newly-seen vulnerabilities -- never re-alerts on one
    already reported."""
    interval = float(os.getenv("SELF_MAINTENANCE_INTERVAL_HOURS", "24")) * 3600.0
    while True:
        await asyncio.sleep(interval)
        await _pulse_orb("yellow", "Running self-maintenance check")
        try:
            messages = await self_maintenance.run_periodic_check()
            for message in messages:
                await _send_or_queue(message)
        except Exception as e:
            logger.exception("Self-maintenance check failed: %s", e)
        try:
            severity = await _update_dependency_vuln_status()
            await _pulse_orb("green" if severity == "green" else "red", "Self-maintenance check complete")
        except Exception as e:
            logger.exception("Dependency vulnerability status update failed: %s", e)
            await _pulse_orb("red", "Self-maintenance check failed")


async def _self_healing_loop() -> None:
    """Runs self_healing's real resource + primary-LLM-backend checks every
    SELF_HEALING_INTERVAL_SECONDS (default 5 min), notifying Telegram only
    when a check's state actually changes (see self_healing._transitioned)
    -- proactive, but never spammy. Also owns focus_mode's own expiry check,
    since this loop already runs on a real, steady interval."""
    interval = float(os.getenv("SELF_HEALING_INTERVAL_SECONDS", "300"))
    while True:
        await asyncio.sleep(interval)
        await _pulse_orb("yellow", "Running self-healing check")
        try:
            messages = await self_healing.run_check_cycle()
            for message in messages:
                await _send_or_queue(message)
            severity = await _update_system_health_status()
            await _pulse_orb("green" if severity == "green" else "red", "Self-healing check complete")
            expired_queue = focus_mode.check_and_flush_if_expired()
            if expired_queue:
                digest = "Focus mode ended, Sir -- here's what happened while you were heads-down:\n\n" + "\n".join(
                    f"- {m['text']}" for m in expired_queue
                )
                await telegram_notifier.send(digest)
        except Exception as e:
            logger.exception("Self-healing check cycle failed: %s", e)
            await _pulse_orb("red", "Self-healing check failed")


async def _watch_execution_loop() -> None:
    """Checks every active watch_store watch that's due (per its own
    check_interval_minutes) every 60s, and pushes exactly one Telegram alert
    when a real change is actually detected -- see watch_store.check_watch."""
    while True:
        await asyncio.sleep(60)
        try:
            for watch in watch_store.watch_store.due():
                try:
                    result = await watch_store.check_watch(watch)
                    if not result.get("success"):
                        logger.info("Watch %s check failed: %s", watch.id, result.get("error"))
                        watch_store.watch_store.record_check(watch.id, None)
                        continue
                    if result.get("changed") and result.get("alert"):
                        await _send_or_queue(result["alert"])
                    watch_store.watch_store.record_check(
                        watch.id, result.get("new_value"),
                        deactivate=bool(result.get("changed") and watch.one_shot),
                    )
                except Exception:
                    logger.exception("Watch %s check raised", watch.id)
        except Exception as e:
            logger.exception("Watch execution loop failed: %s", e)


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
                await _run_cron_job_with_chain(job)
        except Exception:
            logger.exception("Cron execution loop tick failed")


async def _execute_cron_job(job: "cron_store.CronJob") -> str:
    """The real per-action-type execution for exactly one job -- extracted
    from _cron_execution_loop so a CHAINED job (see _run_cron_job_with_chain)
    can be run immediately, off-schedule, through the exact same real logic
    a normally-due job goes through, rather than a second copy. Returns the
    same summary string mark_run/chaining/webhooks all key off."""
    if job.action_type == "telegram_message":
        text = job.action_payload.get("text", "")
        await _send_or_queue(text)
        return "sent telegram message"
    if job.action_type == "agent_task":
        agent_key = job.action_payload.get("agent_key")
        task_type = job.action_payload.get("task_type", "query")
        payload = job.action_payload.get("payload", {})
        if agent_service.is_ready() and agent_key:
            result = await agent_service.run(agent_key, {"type": task_type, **payload}, timeout=60.0)
            summary = json.dumps(result)[:300]
            if telegram_notifier.status["available"]:
                await telegram_notifier.send(f"Cron job \"{job.name}\" ran:\n\n{summary}")
            return summary
        return "skipped: agent service not ready"
    if job.action_type == "run_skill":
        summary = await _run_cron_skill(job.action_payload, f"scheduled job \"{job.name}\"")
        if telegram_notifier.status["available"]:
            await telegram_notifier.send(f"Cron job \"{job.name}\" ran:\n\n{summary}")
        return summary
    if job.action_type == "terminal_command":
        summary = await _run_cron_terminal_command(job.action_payload, f"Scheduled job \"{job.name}\"")
        if telegram_notifier.status["available"]:
            await telegram_notifier.send(f"Cron job \"{job.name}\" ran:\n\n{summary}")
        return summary
    if job.action_type == "run_script":
        summary = await _run_cron_script(job.action_payload, f"scheduled job \"{job.name}\"")
        if telegram_notifier.status["available"] and not summary.startswith("(silent"):
            await telegram_notifier.send(f"Cron job \"{job.name}\" ran:\n\n{summary}")
        return summary
    if job.action_type == "channel_message":
        return await _run_cron_channel_message(job.action_payload, f"scheduled job \"{job.name}\"")
    if job.action_type == "memory_consolidate":
        return await _run_cron_memory_consolidate(job.action_payload, f"scheduled job \"{job.name}\"")
    if job.action_type == "commitment_checkin":
        return await _run_cron_commitment_checkin(job.action_payload, f"scheduled job \"{job.name}\"")
    if job.action_type == "run_macro":
        macro = macro_store.macro_store.find_by_name(job.action_payload.get("name", ""))
        if macro is None:
            return f"error: no macro named {job.action_payload.get('name')!r}"
        result = await _run_macro(macro)
        return f"ran macro {macro.name!r} ({'ok' if result.get('success') else 'had a failed step'})"
    return f"error: unknown action_type {job.action_type!r}"


async def _run_cron_job_with_chain(job: "cron_store.CronJob", depth: int = 0) -> None:
    """Runs one job for real, records the result, fires webhooks, and then
    -- the actual job-chaining feature -- runs every job in job.chain_to
    IMMEDIATELY (off their own schedule) with this job's real result
    injected into their action_payload[chain_input_key] if set. depth caps
    real chain recursion at 5 hops so a mistaken A->B->A cycle can't loop
    forever."""
    try:
        summary = await _execute_cron_job(job)
        cron_store.mark_run(job.id, summary)
        await _fire_webhooks("cron_job_ran", {"job_id": job.id, "job_name": job.name, "result": summary})
    except Exception as e:
        logger.exception("Cron job %s failed: %s", job.name, e)
        summary = f"error: {e}"
        cron_store.mark_run(job.id, summary)

    if not job.chain_to or summary.startswith("error:") or depth >= 5:
        return
    for chain_id in job.chain_to:
        child = cron_store.get(chain_id)
        if child is None or not child.enabled:
            continue
        if job.chain_input_key:
            child.action_payload = {**child.action_payload, job.chain_input_key: summary}
        await _run_cron_job_with_chain(child, depth=depth + 1)


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

    # Static persona goes in the (cached) system role -- see llm.py's
    # _anthropic_system_blocks; only the per-run instructions stay in the
    # user prompt. Same split as the interactive chat path.
    skill_system = _chat_system_blocks(BASE_SYSTEM_PROMPT, "")
    prompt = (
        f"A {trigger_name} triggered this skill (or skill bundle) -- follow its "
        f"instructions and actually do the work, don't just describe it. If more than one skill is listed, "
        f"follow all of them together as one combined procedure.\n\n"
        f"{skills_block}\n\n"
        f"Additional context for this run: {extra_context or '(none)'}"
    )
    claude = AnthropicLLM()
    # Same full tool composition as the interactive chat path
    # (_generate_response_via_hierarchy) -- via _all_chat_tools(), the single
    # shared source of truth, after this call site was found to have silently
    # fallen out of sync with every tool added to the other one.
    resp = await asyncio.wait_for(
        claude.generate_with_tools(
            prompt, _all_chat_tools(), _execute_file_tool, max_tokens=1024,
            system=skill_system,
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

    # This is reachable from POST /webhooks/inbound (which hands the caller
    # the HMAC secret it then signs with) and from POST /cron/jobs, so an
    # arbitrary script could be run -- and persisted across restarts in
    # cron_jobs.json -- with no prompt at all. Its sibling
    # _run_cron_terminal_command has always gated; this one just never did.
    if not arm_switch.is_armed():
        preview = script if len(script) <= 600 else script[:600] + "\n…"
        if not await _request_approval(
            f"\"{trigger_name}\" wants to run a script:\n\n{preview}", timeout=120.0
        ):
            return "Not approved: running a script requires explicit approval and none was given in time"

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


async def _screen_context_loop() -> None:
    """Real ambient screen awareness -- see screen_context.py. A no-op tick
    (fast-polled, cheap) unless the user has actually opted in via
    POST /screen-context/toggle; while on, captures + describes the real
    screen every ~45s so Nancy has current context without being asked to
    look first."""
    while True:
        try:
            if screen_context.is_enabled():
                await screen_context.capture_now()
        except Exception:
            logger.exception("Screen context loop tick failed")
        await asyncio.sleep(screen_context.next_tick_interval_s())


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
    await browser_tool.shutdown_browser()
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