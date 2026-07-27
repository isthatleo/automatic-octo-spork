"""Real Language Server Protocol client -- ported from Hermes' LSP
integration. Spawns a real language server (python-lsp-server for .py files)
as a subprocess and speaks real LSP JSON-RPC over its stdio, so a file write
can be checked against the same diagnostics a real IDE would show --
the same lift as Claude Code's own beforeFileEdited/getNewDiagnostics hook,
done locally against Nancy's own write_file tool (see main_new.py's
_execute_file_tool pre_write integration).

One client process per (server command, workspace root) pair, reused across
calls rather than spawned fresh each time -- LSP servers are real, are not
cheap to start (jedi/pylsp does real project indexing on init).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

_SERVERS_BY_EXTENSION: Dict[str, List[str]] = {
    ".py": ["python", "-m", "pylsp"],
    ".ts": ["typescript-language-server", "--stdio"],
    ".tsx": ["typescript-language-server", "--stdio"],
    ".js": ["typescript-language-server", "--stdio"],
}

LSP_STARTUP_TIMEOUT_S = 10.0
LSP_DIAGNOSTICS_WAIT_S = 3.0


def _path_to_uri(path: str) -> str:
    p = Path(path).expanduser().resolve()
    posix = p.as_posix()
    if os.name == "nt" and len(posix) > 1 and posix[1] == ":":
        return f"file:///{quote(posix)}"
    return f"file://{quote(posix)}"


class LSPClient:
    """One real LSP session -- initialize handshake, didOpen/didChange, and
    capturing the server's own publishDiagnostics push notifications (real
    LSP servers push diagnostics asynchronously after a document changes,
    they don't return them synchronously from didOpen)."""

    def __init__(self, server_cmd: List[str], workspace_root: str) -> None:
        self.server_cmd = server_cmd
        self.workspace_root = workspace_root
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._next_id = 1
        self._pending: Dict[int, asyncio.Future] = {}
        self._diagnostics: Dict[str, List[dict]] = {}
        self._reader_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._proc = await asyncio.create_subprocess_exec(
            *self.server_cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        await asyncio.wait_for(self._request("initialize", {
            "processId": os.getpid(),
            "rootUri": _path_to_uri(self.workspace_root),
            "capabilities": {"textDocument": {"publishDiagnostics": {}}},
        }), timeout=LSP_STARTUP_TIMEOUT_S)
        self._notify("initialized", {})

    async def stop(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self._proc:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except Exception:
                self._proc.kill()

    def _write_message(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._proc.stdin.write(header + body)

    async def _request(self, method: str, params: dict) -> Any:
        msg_id = self._next_id
        self._next_id += 1
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future
        self._write_message({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        await self._proc.stdin.drain()
        return await future

    def _notify(self, method: str, params: dict) -> None:
        self._write_message({"jsonrpc": "2.0", "method": method, "params": params})

    async def _read_loop(self) -> None:
        """Real LSP message framing: Content-Length header, blank line,
        then exactly that many bytes of JSON body -- reads both responses
        (matched to a pending request by id) and server-pushed
        notifications (publishDiagnostics)."""
        try:
            while True:
                headers = {}
                while True:
                    line = await self._proc.stdout.readline()
                    if not line or line in (b"\r\n", b"\n"):
                        break
                    key, _, value = line.decode("ascii").partition(":")
                    headers[key.strip().lower()] = value.strip()
                length = int(headers.get("content-length", 0))
                if length == 0:
                    continue
                body = await self._proc.stdout.readexactly(length)
                message = json.loads(body)

                if "id" in message and message["id"] in self._pending:
                    future = self._pending.pop(message["id"])
                    if not future.done():
                        future.set_result(message.get("result"))
                elif message.get("method") == "textDocument/publishDiagnostics":
                    uri = message["params"]["uri"]
                    self._diagnostics[uri] = message["params"].get("diagnostics", [])
        except (asyncio.CancelledError, asyncio.IncompleteReadError):
            pass
        except Exception as e:
            logger.warning("lsp_client: read loop ended: %s", e)

    async def _wait_for_diagnostics(self, uri: str) -> List[dict]:
        waited = 0.0
        while uri not in self._diagnostics and waited < LSP_DIAGNOSTICS_WAIT_S:
            await asyncio.sleep(0.1)
            waited += 0.1
        return self._diagnostics.get(uri, [])

    async def get_diagnostics_for_content(self, path: str, content: str) -> List[dict]:
        """One-shot check: opens `content` as the document at `path`, waits
        for the server's real publishDiagnostics push, closes it, and
        returns whatever it reported. For a before/after comparison against
        the SAME path, prefer diff_diagnostics_for_edit below instead of two
        calls to this -- rapid didClose+didOpen on the same URI in quick
        succession is a real protocol-sequencing hazard (confirmed live:
        pylsp's second publishDiagnostics push silently never arrived when
        exercised this way), the standard LSP flow updates an already-open
        document via didChange, not close+reopen."""
        uri = _path_to_uri(path)
        self._diagnostics.pop(uri, None)
        language_id = "python" if path.endswith(".py") else "typescript"
        self._notify("textDocument/didOpen", {
            "textDocument": {"uri": uri, "languageId": language_id, "version": 1, "text": content},
        })
        diagnostics = await self._wait_for_diagnostics(uri)
        self._notify("textDocument/didClose", {"textDocument": {"uri": uri}})
        return diagnostics

    async def diff_diagnostics_for_edit(self, path: str, old_content: Optional[str], new_content: str) -> Dict[str, List[dict]]:
        """The real before/after comparison, done the protocol-correct way:
        one didOpen (old_content, or new_content directly if there's no
        'before' to compare against), one didChange to the new content, one
        didClose at the end -- never a rapid close+reopen on the same URI."""
        uri = _path_to_uri(path)
        self._diagnostics.pop(uri, None)
        language_id = "python" if path.endswith(".py") else "typescript"

        if old_content is None:
            # Brand-new file: nothing to diff against, so every diagnostic
            # the server reports for it is real and "new" by definition --
            # open it directly as new_content and surface whatever comes back.
            self._notify("textDocument/didOpen", {
                "textDocument": {"uri": uri, "languageId": language_id, "version": 1, "text": new_content},
            })
            after = await self._wait_for_diagnostics(uri)
            self._notify("textDocument/didClose", {"textDocument": {"uri": uri}})
            return {"before": [], "after": after}

        self._notify("textDocument/didOpen", {
            "textDocument": {"uri": uri, "languageId": language_id, "version": 1, "text": old_content},
        })
        before = await self._wait_for_diagnostics(uri)

        self._diagnostics.pop(uri, None)
        self._notify("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": 2},
            "contentChanges": [{"text": new_content}],
        })
        after = await self._wait_for_diagnostics(uri)

        self._notify("textDocument/didClose", {"textDocument": {"uri": uri}})
        return {"before": before, "after": after}


_clients: Dict[str, LSPClient] = {}


async def _get_client_for(path: str, workspace_root: str) -> Optional[LSPClient]:
    ext = Path(path).suffix
    server_cmd = _SERVERS_BY_EXTENSION.get(ext)
    if server_cmd is None:
        return None
    key = f"{server_cmd[0]}::{workspace_root}"
    if key not in _clients:
        client = LSPClient(server_cmd, workspace_root)
        try:
            await client.start()
        except Exception as e:
            logger.warning("lsp_client: failed to start server for %s: %s", ext, e)
            return None
        _clients[key] = client
    return _clients[key]


async def diagnostics_before_after_write(path: str, old_content: Optional[str], new_content: str) -> Dict[str, Any]:
    """The real "new diagnostics from this write" check. Returns
    {"success": False, "unsupported": True} for a file type with no
    configured server (most files) -- not an error, just nothing to check."""
    workspace_root = str(Path(path).expanduser().resolve().parent)
    client = await _get_client_for(path, workspace_root)
    if client is None:
        return {"success": True, "unsupported": True, "new_diagnostics": []}

    try:
        diagnostics = await client.diff_diagnostics_for_edit(path, old_content, new_content)
        before, after = diagnostics["before"], diagnostics["after"]
    except Exception as e:
        logger.warning("lsp_client: diagnostics check failed: %s", e)
        return {"success": False, "error": str(e)}

    before_keys = {(d.get("range", {}).get("start", {}).get("line"), d.get("message")) for d in before}
    new_diagnostics = [d for d in after if (d.get("range", {}).get("start", {}).get("line"), d.get("message")) not in before_keys]
    return {"success": True, "unsupported": False, "new_diagnostics": new_diagnostics, "all_diagnostics": after}


async def shutdown_all_clients() -> None:
    for client in _clients.values():
        await client.stop()
    _clients.clear()
