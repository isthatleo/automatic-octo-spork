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
from typing import Any, Dict, List, Optional

from workspace_uri import resolve_oc_path

MAX_READ_BYTES = 200_000  # per-call cap, regardless of offset/limit -- keeps
# one call from blowing the model's context even when it deliberately asks
# for a huge slice

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


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
MAX_IMAGE_BYTES = 15_000_000  # generous -- vision models cap around here anyway


def read_file(path: str, offset: int = 0, limit: Optional[int] = None) -> Dict[str, Any]:
    """Read a file's text, optionally from a given 1-indexed line `offset`
    and capped at `limit` lines -- the same offset/limit idiom as Claude
    Code's own Read tool. Without this, a file over MAX_READ_BYTES (this
    project's own main_new.py is one -- 214KB against a 200KB cap) was
    silently cut off with no way to ever see the rest of it. `has_more`/
    `end_line` tell the caller exactly how to page to the next chunk.

    An image path returns real base64 image data instead of decoded text --
    same thing Claude Code's own Read tool does for a screenshot/diagram
    file. main_new.py's read_file dispatch promotes this to the reserved
    `_image_base64` result key so the model actually SEES it, the same
    mechanism take_screenshot/browser_screenshot already use."""
    p = Path(resolve_oc_path(path)).expanduser()
    if not p.exists():
        return {"success": False, "error": f"No such file: {path}"}
    if not p.is_file():
        return {"success": False, "error": f"Not a file: {path}"}

    if p.suffix.lower() in IMAGE_EXTENSIONS:
        try:
            size = p.stat().st_size
            if size > MAX_IMAGE_BYTES:
                return {"success": False, "error": f"Image too large ({size} bytes, cap {MAX_IMAGE_BYTES})"}
            import base64
            data = p.read_bytes()
            return {"success": True, "path": str(p), "is_image": True, "image_base64": base64.b64encode(data).decode("ascii"), "size_bytes": size}
        except Exception as e:
            return {"success": False, "error": str(e)}

    try:
        raw = p.read_bytes()
    except Exception as e:
        return {"success": False, "error": str(e)}

    full_text = raw.decode("utf-8", errors="replace")
    lines = full_text.splitlines()
    total_lines = len(lines)
    start = max(0, offset)
    selected = lines[start:start + limit] if limit is not None else lines[start:]

    # Hard byte-size safety net even within the requested slice, clipped on
    # a line boundary so the result is always valid readable text rather
    # than a mid-line cut.
    truncated = False
    kept: List[str] = []
    size = 0
    for line in selected:
        line_size = len(line.encode("utf-8")) + 1
        if size + line_size > MAX_READ_BYTES:
            truncated = True
            break
        kept.append(line)
        size += line_size

    end_line = start + len(kept)
    return {
        "success": True,
        "path": str(p),
        "content": "\n".join(kept),
        "total_lines": total_lines,
        "start_line": start,
        "end_line": end_line,
        "has_more": end_line < total_lines,
        "truncated": truncated,
        "size_bytes": len(raw),
    }


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


def multi_edit_file(path: str, edits: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Apply several find-and-replace edits to one file in a single atomic
    operation -- the same job Claude Code's own MultiEdit tool does. Edits are
    applied in order against an in-memory copy, each one seeing the previous
    edit's result, exactly like calling edit_file repeatedly; the difference
    is atomicity -- if any edit in the middle fails (old_string not found, or
    not unique without replace_all), nothing is written to disk at all,
    instead of leaving the file half-changed."""
    p = Path(resolve_oc_path(path)).expanduser()
    if not p.exists():
        return {"success": False, "error": f"No such file: {path}"}
    if not p.is_file():
        return {"success": False, "error": f"Not a file: {path}"}
    if not edits:
        return {"success": False, "error": "edits must be a non-empty list."}
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"success": False, "error": str(e)}

    old_content = content
    for i, edit in enumerate(edits):
        old_string = edit.get("old_string", "")
        new_string = edit.get("new_string", "")
        replace_all = edit.get("replace_all", False)
        if old_string == "":
            return {"success": False, "error": f"Edit #{i + 1}: old_string must not be empty."}
        count = content.count(old_string)
        if count == 0:
            return {"success": False, "error": f"Edit #{i + 1}: old_string was not found (must match exactly, including whitespace)."}
        if count > 1 and not replace_all:
            return {"success": False, "error": f"Edit #{i + 1}: old_string is not unique ({count} matches) -- pass more surrounding context, or set replace_all."}
        content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)

    try:
        p.write_text(content, encoding="utf-8")
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"success": True, "path": str(p), "edits_applied": len(edits), "old_content": old_content, "new_content": content}


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


def check_python_syntax(path: str) -> Optional[str]:
    """Real syntax check via the builtin compile() -- the exact same
    AST-parse-level check `python -m py_compile` does, just in-process (no
    subprocess, no server). This is what Claude Code's own edit loop
    effectively gets for free from language tooling; without it, a Python
    write/edit that introduced a syntax error just silently succeeded and
    the model never found out unless the human noticed and said something.
    Returns an error string, or None if the file parses cleanly. Only wired
    up for .py -- see main_new.py's _execute_file_tool."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        compile(source, path, "exec")
        return None
    except SyntaxError as e:
        return f"{e.msg} (line {e.lineno}, col {e.offset})"
    except Exception as e:
        return str(e)


def glob_files(pattern: str, path: str = ".") -> Dict[str, Any]:
    """Find files by NAME pattern (e.g. '**/*.py', '*.tsx') under a
    directory, most-recently-modified first -- the same job Claude Code's
    own Glob tool does. Complements search_files, which searches file
    CONTENT: this is for "what files are there" rather than "where does X
    appear."""
    root = Path(resolve_oc_path(path)).expanduser()
    if not root.exists():
        return {"success": False, "error": f"No such path: {path}"}
    if not root.is_dir():
        return {"success": False, "error": f"Not a directory: {path}"}
    try:
        candidates = list(root.glob(pattern))
    except Exception as e:
        return {"success": False, "error": f"Invalid glob pattern: {e}"}

    dated: List[tuple] = []
    for p in candidates:
        if not p.is_file():
            continue
        rel_parts = p.relative_to(root).parts[:-1]
        if any(part in _SEARCH_SKIP_DIRS or part.startswith(".") for part in rel_parts):
            continue
        try:
            dated.append((p.stat().st_mtime, str(p)))
        except OSError:
            continue

    dated.sort(key=lambda t: t[0], reverse=True)
    truncated = len(dated) > MAX_SEARCH_RESULTS
    matches = [path_str for _, path_str in dated[:MAX_SEARCH_RESULTS]]
    return {"success": True, "pattern": pattern, "matches": matches, "count": len(matches), "truncated": truncated}


def create_directory(path: str) -> Dict[str, Any]:
    """Real "New Folder" -- mkdir -p semantics (no error if it already
    exists, parents created as needed), same as write_file's own directory
    creation but callable on its own for the editor panel's New Folder
    action, which has no file content to imply a path from."""
    p = Path(resolve_oc_path(path)).expanduser()
    try:
        p.mkdir(parents=True, exist_ok=True)
        return {"success": True, "path": str(p)}
    except Exception as e:
        return {"success": False, "error": str(e)}


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
