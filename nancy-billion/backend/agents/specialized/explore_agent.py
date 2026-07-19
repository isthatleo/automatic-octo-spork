"""
Explore Agent for Nancy/Billion Backend

Real, read-only file/code search -- walks an actual directory tree on disk
and returns genuine matching files and line snippets (a real grep, not a
scripted response). Mirrors Claude Code's own "Explore" subagent: fast,
read-only, locates files/symbols/patterns.

Read access is intentionally unrestricted (same choice already made for
file_access.py's read_file/list_directory, gated at the write layer, not
the read layer) but this agent adds its own sane exclusions (VCS/dependency
directories, binary files, oversized files) so a search doesn't waste time
walking node_modules or hang on a multi-GB file.
"""
from __future__ import annotations

import fnmatch
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)

_EXCLUDED_DIRS = {
    "node_modules", ".git", "__pycache__", ".next", "venv", ".venv",
    "dist", "build", ".pytest_cache", ".mypy_cache", "site-packages",
}
_MAX_FILE_BYTES = 2_000_000  # skip anything bigger -- almost certainly not source
_MAX_FILES_SCANNED = 20_000  # hard cap so a bad root can't hang the request
_MAX_MATCHES = 200


class ExploreAgent(SpecializedAgent):
    """Real read-only file/code search over an actual directory tree."""

    def __init__(self, settings):
        super().__init__(settings, "Explore Agent", "explore")
        self.capabilities.update({
            "description": "Fast, read-only file and code search across a real directory tree -- locate files by name pattern or content",
            "confidence": 0.9,
            "specializations": [
                "file-search",
                "content-search",
                "codebase-navigation",
            ],
            "tools": ["filesystem-read"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "search")
        if task_type in ("search", "grep", "query"):
            return await self._search(task_data)
        if task_type in ("find-files", "glob"):
            return await self._find_files(task_data)
        return {"success": False, "error": f"Unknown task type '{task_type}' for explore agent"}

    def _iter_files(self, root: Path, name_glob: str | None):
        scanned = 0
        for path in root.rglob("*"):
            if scanned >= _MAX_FILES_SCANNED:
                break
            if path.is_dir():
                continue
            if any(part in _EXCLUDED_DIRS for part in path.parts):
                continue
            if name_glob and not fnmatch.fnmatch(path.name, name_glob):
                continue
            scanned += 1
            yield path

    async def _find_files(self, params: Dict[str, Any]) -> Dict[str, Any]:
        root_str = params.get("root") or params.get("path") or "."
        pattern = params.get("pattern") or params.get("glob") or "*"
        root = Path(root_str).expanduser()
        if not root.exists() or not root.is_dir():
            return {"success": False, "error": f"'{root_str}' is not a real, existing directory"}

        matches = [str(p) for p in self._iter_files(root, pattern)][:_MAX_MATCHES]
        return {
            "success": True,
            "task_type": "find-files",
            "root": str(root),
            "pattern": pattern,
            "match_count": len(matches),
            "matches": matches,
        }

    async def _search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        root_str = params.get("root") or params.get("path") or "."
        query = params.get("query") or params.get("pattern") or ""
        name_glob = params.get("file_glob")
        use_regex = bool(params.get("regex", False))
        if not query:
            return {"success": False, "error": "A 'query' (text or regex to search for) is required"}

        root = Path(root_str).expanduser()
        if not root.exists() or not root.is_dir():
            return {"success": False, "error": f"'{root_str}' is not a real, existing directory"}

        try:
            matcher = re.compile(query) if use_regex else None
        except re.error as e:
            return {"success": False, "error": f"Invalid regex: {e}"}

        results: List[Dict[str, Any]] = []
        files_with_matches = 0
        for path in self._iter_files(root, name_glob):
            if len(results) >= _MAX_MATCHES:
                break
            try:
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            file_hit = False
            for lineno, line in enumerate(text.splitlines(), start=1):
                hit = matcher.search(line) if matcher else (query in line)
                if hit:
                    file_hit = True
                    results.append({
                        "file": str(path),
                        "line": lineno,
                        "text": line.strip()[:300],
                    })
                    if len(results) >= _MAX_MATCHES:
                        break
            if file_hit:
                files_with_matches += 1

        return {
            "success": True,
            "task_type": "search",
            "root": str(root),
            "query": query,
            "regex": use_regex,
            "files_with_matches": files_with_matches,
            "match_count": len(results),
            "truncated": len(results) >= _MAX_MATCHES,
            "matches": results,
        }
