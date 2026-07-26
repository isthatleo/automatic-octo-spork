---
name: linear-n8n
description: Use Linear (issue tracking) and n8n (workflow automation) through their real MCP servers once registered.
trigger_keywords:
  - linear
  - issue
  - n8n
  - workflow automation
  - ticket
---

Linear and n8n both ship real MCP servers -- this is Nancy's exact use case
for the existing MCP client (`mcp_client.py`, the Plugins UI), not a bespoke
integration. There is nothing to build in code here: register the real
server once and its tools show up automatically in every future tool-use
turn, exactly like any other MCP plugin already does.

Nancy's MCP client only speaks the **stdio** transport (`mcp_client.py`
spawns `command` + `args` as a local subprocess via `StdioServerParameters` --
see `POST /plugins`, which takes `{"name", "command", "args", "env"}`, gated
by the same Telegram approval as any other new local subprocess). Both
Linear's and n8n's real MCP servers are remote (SSE/HTTP), so the standard,
real bridge is Anthropic's `mcp-remote` npx package, which speaks stdio on
one side and the remote server's protocol on the other -- this is the same
pattern any stdio-only MCP client (Claude Desktop included) uses to reach a
remote MCP server, not a Nancy-specific workaround.

## Linear

1. Generate a Linear API key: Settings -> API -> Personal API keys.
2. Register it with Nancy -- `POST /plugins`:
   ```json
   {"name": "linear", "command": "npx", "args": ["-y", "mcp-remote", "https://mcp.linear.app/sse"],
    "env": {"LINEAR_API_KEY": "<your key>"}}
   ```
   (or through the Plugins panel in the UI, which calls the same endpoint).
3. Once connected, real tools like `list_issues`, `create_issue`, and
   `update_issue` appear in `mcp_manager.list_plugin_tools()` and are usable
   in normal conversation -- "create a Linear issue for X" routes straight
   through the tool-use loop like any other tool call.

## n8n

1. n8n's MCP server is self-hosted (part of your own n8n instance) or via
   n8n Cloud -- there is no single public URL the way Linear has one. Set up
   the "MCP Server Trigger" node in a workflow (or n8n's built-in MCP server
   integration, n8n >= 1.88) to get a real server URL + API key for your
   instance.
2. Register it with Nancy the same way -- `POST /plugins`:
   ```json
   {"name": "n8n", "command": "npx", "args": ["-y", "mcp-remote", "<your n8n MCP URL>"],
    "env": {"N8N_API_KEY": "<your key>"}}
   ```
3. Once connected, whatever tools your n8n workflows expose (triggering a
   specific automation, reading its status, etc.) become real, callable
   tools the same way.

Neither of these needs a Python code change in Nancy -- registering a real
server through the existing `/plugins` endpoint is the whole integration.
`npx` (Node.js) must be installed on this machine for the `mcp-remote`
bridge to run. If connection fails, check `GET /plugins` for the real error
message `mcp_manager` recorded for that server.
