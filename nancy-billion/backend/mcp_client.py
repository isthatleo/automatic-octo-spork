"""Real MCP (Model Context Protocol) client -- lets Nancy connect to actual
third-party MCP servers (filesystem, git, search, whatever the user
configures) and use their genuine tools through Claude's existing tool-use
loop. This is the "MCP-style plugin system" from the Phase 2 deferred scope,
built on the official `mcp` Python SDK (real JSON-RPC framing, capability
negotiation, session lifecycle) instead of a hand-rolled approximation --
same principle as croniter for cron and sentence-transformers for embeddings.

Stdio transport only (a server is a real local subprocess: `command` + `args`,
e.g. `npx -y @modelcontextprotocol/server-filesystem C:\\some\\path`) -- this
is how the overwhelming majority of MCP servers are actually distributed and
configured (the same shape Claude Desktop's own config file uses), and
covering one transport for real beats half-covering two.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import AsyncExitStack
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "mcp_servers.json"
CONNECT_TIMEOUT_S = 20.0
CALL_TIMEOUT_S = 60.0


@dataclass
class PluginServerConfig:
    id: str
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True

    def to_public_dict(self) -> Dict[str, Any]:
        """asdict() alone would put real env var *values* (tokens, API keys
        passed at server-creation time) straight into the /plugins response
        -- every other credential surface in this app (Keys, Config
        capabilities) is careful to only ever report whether something is
        set, never the value itself. This keeps that same guarantee: key
        names survive (so the UI can show which env vars a server has),
        values don't."""
        data = asdict(self)
        data["env"] = {k: "set" for k in self.env}
        return data


class PluginStore:
    """JSON-file-backed server config list -- same persistence pattern as
    cron_store.py/missions_store.py. Registering a server here does NOT
    connect it (see MCPPluginManager below) -- this is just the durable
    "what servers exist" record."""

    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._servers: Dict[str, PluginServerConfig] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for item in raw:
                cfg = PluginServerConfig(**item)
                self._servers[cfg.id] = cfg
        except Exception:
            logger.exception("Failed to load mcp_servers.json — starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(s) for s in self._servers.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list(self) -> List[PluginServerConfig]:
        return sorted(self._servers.values(), key=lambda s: s.name)

    def get(self, server_id: str) -> Optional[PluginServerConfig]:
        return self._servers.get(server_id)

    def create(self, name: str, command: str, args: List[str], env: Dict[str, str]) -> PluginServerConfig:
        cfg = PluginServerConfig(id=uuid.uuid4().hex[:12], name=name, command=command, args=args or [], env=env or {})
        self._servers[cfg.id] = cfg
        self._save()
        return cfg

    def delete(self, server_id: str) -> bool:
        if server_id not in self._servers:
            return False
        del self._servers[server_id]
        self._save()
        return True

    def set_enabled(self, server_id: str, enabled: bool) -> Optional[PluginServerConfig]:
        cfg = self._servers.get(server_id)
        if cfg is None:
            return None
        cfg.enabled = enabled
        self._save()
        return cfg


plugin_store = PluginStore()


@dataclass
class _LiveServer:
    config: PluginServerConfig
    session: Optional[ClientSession] = None
    tools: List[Any] = field(default_factory=list)  # list[mcp.types.Tool]
    connected: bool = False
    error: Optional[str] = None


def _safe_ns(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name.lower())


class MCPPluginManager:
    """Owns real, long-lived subprocess connections to every enabled plugin
    server -- one AsyncExitStack per server so a stdio subprocess + its
    ClientSession stay alive across many tool calls (spawning a fresh
    process per call would be slow and against the MCP session model, which
    expects exactly one initialize() handshake per connection lifetime)."""

    def __init__(self, store: PluginStore = plugin_store):
        self.store = store
        self._live: Dict[str, _LiveServer] = {}
        self._stacks: Dict[str, AsyncExitStack] = {}

    async def connect_all(self) -> None:
        for cfg in self.store.list():
            if cfg.enabled:
                await self.connect(cfg.id)

    async def connect(self, server_id: str) -> _LiveServer:
        cfg = self.store.get(server_id)
        if cfg is None:
            raise ValueError(f"Unknown plugin server '{server_id}'")
        await self.disconnect(server_id)  # idempotent -- clean slate before (re)connecting

        live = _LiveServer(config=cfg)
        self._live[server_id] = live
        stack = AsyncExitStack()
        self._stacks[server_id] = stack

        async def _do_connect():
            params = StdioServerParameters(command=cfg.command, args=cfg.args, env=cfg.env or None)
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            tools_result = await session.list_tools()
            return session, list(tools_result.tools)

        try:
            session, tools = await asyncio.wait_for(_do_connect(), timeout=CONNECT_TIMEOUT_S)
            live.session = session
            live.tools = tools
            live.connected = True
            logger.info("Connected MCP plugin server '%s' (%d tools)", cfg.name, len(live.tools))
        except Exception as e:
            live.connected = False
            live.error = str(e)
            logger.warning("Failed to connect MCP plugin server '%s': %s", cfg.name, e)
            try:
                await stack.aclose()
            except Exception:
                pass
            self._stacks.pop(server_id, None)
        return live

    async def disconnect(self, server_id: str) -> None:
        stack = self._stacks.pop(server_id, None)
        if stack is not None:
            try:
                await stack.aclose()
            except Exception:
                logger.exception("Error closing MCP plugin server '%s'", server_id)
        self._live.pop(server_id, None)

    async def disconnect_all(self) -> None:
        for server_id in list(self._stacks.keys()):
            await self.disconnect(server_id)

    def list_status(self) -> List[Dict[str, Any]]:
        out = []
        for cfg in self.store.list():
            live = self._live.get(cfg.id)
            out.append({
                **cfg.to_public_dict(),
                "connected": bool(live and live.connected),
                "error": live.error if live else None,
                "tools": [t.name for t in live.tools] if live else [],
            })
        return out

    def list_plugin_tools(self) -> List[Dict[str, Any]]:
        """Claude tool-use schema shaped list, namespaced
        mcp__<server>__<tool> so _execute_file_tool can route a call back to
        the right live session with no name collision between servers."""
        out = []
        for live in self._live.values():
            if not live.connected:
                continue
            safe_name = _safe_ns(live.config.name)
            for tool in live.tools:
                out.append({
                    "name": f"mcp__{safe_name}__{tool.name}",
                    "description": (tool.description or f"{tool.name} (from MCP plugin server '{live.config.name}')")[:1024],
                    "input_schema": tool.inputSchema or {"type": "object", "properties": {}},
                })
        return out

    def is_plugin_tool(self, tool_name: str) -> bool:
        return tool_name.startswith("mcp__")

    async def call_tool(self, qualified_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        parts = qualified_name.split("__", 2)
        if len(parts) != 3 or parts[0] != "mcp":
            return {"success": False, "error": f"Malformed plugin tool name '{qualified_name}'"}
        _, safe_name, tool_name = parts
        live = next((l for l in self._live.values() if _safe_ns(l.config.name) == safe_name and l.connected), None)
        if live is None or live.session is None:
            return {"success": False, "error": f"Plugin server for '{qualified_name}' is not connected"}
        try:
            result = await asyncio.wait_for(live.session.call_tool(tool_name, arguments), timeout=CALL_TIMEOUT_S)
        except Exception as e:
            return {"success": False, "error": f"Plugin tool call failed: {e}"}
        text_parts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
        output = "\n".join(text_parts) if text_parts else json.dumps([c.model_dump() for c in result.content], default=str)
        return {"success": not result.isError, "output": output[:4000]}


mcp_manager = MCPPluginManager()
