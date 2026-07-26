---
name: mcp-plugins
description: Explain and manage real MCP (Model Context Protocol) plugin servers -- third-party tool integrations, not a hypothetical feature.
trigger_keywords:
  - mcp
  - plugin
  - plugins
  - third-party tool
  - connect a server
  - integration
  - extend your tools
---

Nancy has a real MCP client (`mcp_client.py`, official `mcp` SDK) that can
connect to actual third-party MCP servers and use their genuine tools --
filesystem access, git, web search, databases, whatever the user configures
-- through the same tool-use loop as `read_file`/`execute_command`.

- List configured servers + live connection status: `GET /plugins`.
- Register a new server: `POST /plugins` with `{"name", "command", "args"}`
  (e.g. `{"name": "filesystem", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\some\\path"]}`).
  This spawns a real local subprocess, so it goes through the same Telegram
  approval gate as `execute_command` -- explain that to the user rather than
  implying it happens instantly.
- Enable/disable: `PATCH /plugins/{id}?enabled=true|false`.
- Remove: `DELETE /plugins/{id}`.

Once connected, a server's tools appear automatically (namespaced
`mcp__<server>__<tool>`) in every tool-use-capable chat turn and cron
`run_skill` job -- no separate step needed to "activate" them for
conversation.

## Answering

- If asked "what plugins do you have," answer from `GET /plugins`'s real
  connected/tool-count data, not a guess.
- If a server shows `connected: false` with an error, surface the real error
  (e.g. "npx not found," a bad package name) rather than a vague "something
  went wrong."
- Don't claim to support a capability that isn't backed by either a native
  tool or a currently-connected MCP server's real tool list.
