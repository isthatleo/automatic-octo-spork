"""Real file system access for Nancy's chat tool-use (see main_new.py's
Claude tool-calling loop, FILE_TOOLS/_execute_file_tool).

Per explicit user choice this session: unrestricted path access -- no folder
sandbox -- but every write/delete/move is gated behind Telegram approval
before it executes (see _execute_file_tool). These functions themselves are
pure file I/O with no gating logic; the safety check happens one layer up so
this module stays simple and directly testable.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict

MAX_READ_BYTES = 200_000  # cap how much file content gets pulled into a prompt


def read_file(path: str) -> Dict[str, Any]:
    p = Path(path).expanduser()
    if not p.exists():
        return {"success": False, "error": f"No such file: {path}"}
    if not p.is_file():
        return {"success": False, "error": f"Not a file: {path}"}
    try:
        data = p.read_bytes()
    except Exception as e:
        return {"success": False, "error": str(e)}
    truncated = len(data) > MAX_READ_BYTES
    text = data[:MAX_READ_BYTES].decode("utf-8", errors="replace")
    return {"success": True, "path": str(p), "content": text, "truncated": truncated, "size_bytes": len(data)}


def list_directory(path: str) -> Dict[str, Any]:
    p = Path(path).expanduser()
    if not p.exists():
        return {"success": False, "error": f"No such directory: {path}"}
    if not p.is_dir():
        return {"success": False, "error": f"Not a directory: {path}"}
    try:
        entries = []
        for child in sorted(p.iterdir()):
            entries.append({
                "name": child.name,
                "is_dir": child.is_dir(),
                "size_bytes": child.stat().st_size if child.is_file() else None,
            })
        return {"success": True, "path": str(p), "entries": entries}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_file(path: str, content: str) -> Dict[str, Any]:
    p = Path(path).expanduser()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(p), "bytes_written": len(content.encode("utf-8"))}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_file(path: str) -> Dict[str, Any]:
    p = Path(path).expanduser()
    if not p.exists():
        return {"success": False, "error": f"No such path: {path}"}
    try:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return {"success": True, "path": str(p)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def move_file(src: str, dst: str) -> Dict[str, Any]:
    src_p = Path(src).expanduser()
    dst_p = Path(dst).expanduser()
    if not src_p.exists():
        return {"success": False, "error": f"No such path: {src}"}
    try:
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_p), str(dst_p))
        return {"success": True, "from": str(src_p), "to": str(dst_p)}
    except Exception as e:
        return {"success": False, "error": str(e)}
