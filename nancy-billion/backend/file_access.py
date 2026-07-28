"""Real file system access for Nancy's chat tool-use (see main_new.py's
Claude tool-calling loop, FILE_TOOLS/_execute_file_tool).

Per explicit user choice this session: unrestricted path access -- no folder
sandbox -- but every write/delete/move is gated behind Telegram approval
before it executes (see _execute_file_tool). These functions themselves are
pure file I/O with no gating logic; the safety check happens one layer up so
this module stays simple and directly testable.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List

from workspace_uri import resolve_oc_path

MAX_READ_BYTES = 200_000  # cap how much file content gets pulled into a prompt

# Directories a real codebase search should never descend into -- matches
# what a human (or Claude Code's own Grep) would skip: generated/vendored
# trees that are huge, irrelevant to source understanding, and would blow
# past MAX_SEARCH_RESULTS with noise before a real hit is ever found.
_SEARCH_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".turbo", "target", ".mypy_cache", ".pytest_cache",
}
MAX_SEARCH_RESULTS = 100
MAX_SEARCH_FILE_BYTES = 2_000_000  # skip scanning anything bigger (almost certainly not source)


def read_file(path: str) -> Dict[str, Any]:
    p = Path(resolve_oc_path(path)).expanduser()
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
    p = Path(resolve_oc_path(path)).expanduser()
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
    p = Path(resolve_oc_path(path)).expanduser()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(p), "bytes_written": len(content.encode("utf-8"))}
    except Exception as e:
        return {"success": False, "error": str(e)}


def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> Dict[str, Any]:
    """Surgical find-and-replace within an existing file -- the same
    old_string/new_string idiom as Claude Code's own Edit tool, rather than
    forcing every change through a full-file overwrite (write_file). Safer
    for large files and for changes the model can precisely locate: no risk
    of accidentally dropping unrelated content that a regenerated whole file
    would carry. old_string must appear exactly once unless replace_all is
    set, mirroring Edit's own uniqueness guarantee."""
    p = Path(resolve_oc_path(path)).expanduser()
    if not p.exists():
        return {"success": False, "error": f"No such file: {path}"}
    if not p.is_file():
        return {"success": False, "error": f"Not a file: {path}"}
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"success": False, "error": str(e)}

    if old_string == "":
        return {"success": False, "error": "old_string must not be empty."}
    count = content.count(old_string)
    if count == 0:
        return {"success": False, "error": "old_string was not found in the file (must match exactly, including whitespace)."}
    if count > 1 and not replace_all:
        return {"success": False, "error": f"old_string is not unique ({count} matches) -- pass more surrounding context, or set replace_all."}

    new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
    try:
        p.write_text(new_content, encoding="utf-8")
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"success": True, "path": str(p), "replacements_made": count if replace_all else 1, "old_content": content, "new_content": new_content}


def search_files(pattern: str, path: str = ".", glob: str = "", case_sensitive: bool = False) -> Dict[str, Any]:
    """Regex search for `pattern` across every file under `path` (optionally
    filtered by a filename glob, e.g. "*.py") -- the same job Claude Code's
    own Grep tool does. Without this, understanding an existing codebase
    meant read_file-ing files one at a time on a guess; a real coding agent
    needs to actually find where something is defined/used first."""
    root = Path(resolve_oc_path(path)).expanduser()
    if not root.exists():
        return {"success": False, "error": f"No such path: {path}"}
    try:
        regex = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
    except re.error as e:
        return {"success": False, "error": f"Invalid regex: {e}"}

    files_to_scan: List[Path] = [root] if root.is_file() else []
    if root.is_dir():
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SEARCH_SKIP_DIRS and not d.startswith(".")]
            for fname in filenames:
                if glob and not Path(fname).match(glob):
                    continue
                files_to_scan.append(Path(dirpath) / fname)

    matches: List[Dict[str, Any]] = []
    files_matched = set()
    truncated = False
    for f in files_to_scan:
        if len(matches) >= MAX_SEARCH_RESULTS:
            truncated = True
            break
        try:
            if f.stat().st_size > MAX_SEARCH_FILE_BYTES:
                continue
            text = f.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable -- skip rather than error the whole search
        for i, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append({"file": str(f), "line": i, "text": line.strip()[:300]})
                files_matched.add(str(f))
                if len(matches) >= MAX_SEARCH_RESULTS:
                    truncated = True
                    break

    return {
        "success": True, "pattern": pattern, "matches": matches,
        "files_matched": len(files_matched), "total_matches": len(matches), "truncated": truncated,
    }


def delete_file(path: str) -> Dict[str, Any]:
    p = Path(resolve_oc_path(path)).expanduser()
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
    src_p = Path(resolve_oc_path(src)).expanduser()
    dst_p = Path(resolve_oc_path(dst)).expanduser()
    if not src_p.exists():
        return {"success": False, "error": f"No such path: {src}"}
    try:
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_p), str(dst_p))
        return {"success": True, "from": str(src_p), "to": str(dst_p)}
    except Exception as e:
        return {"success": False, "error": str(e)}
