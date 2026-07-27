"""Real config/memory/skill migration importers -- ported from OpenClaw's
migrate-claude/migrate-hermes extensions. A plan/apply split throughout:
`plan_*` functions read a source and report what WOULD be imported without
touching Nancy's real state; `apply_*` functions actually perform the
import (real memory nodes added, real skill files written) -- so a user
can review before committing to an import from an unfamiliar source file.

Starts with the two formats genuinely straightforward to support without
guessing at another agent's undocumented internal schema: a generic JSON
memory-export (a list of records with a "content" field, whatever else is
attached carried through as metadata) and Markdown skill files using the
same frontmatter convention skill_loader.py and memory/wiki_store.py
already parse (utils/frontmatter.py).
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List

from utils.frontmatter import parse_frontmatter_file

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent / "skills"


def plan_memory_import(json_path: str) -> Dict[str, Any]:
    """Real, read-only preview -- parses the export and reports how many
    records were found and a sample, without touching MemoryGraph at all."""
    path = Path(json_path).expanduser()
    if not path.is_file():
        return {"success": False, "error": f"no such file: {json_path}"}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"success": False, "error": f"invalid JSON: {e}"}

    records = _normalize_memory_records(data)
    if records is None:
        return {"success": False, "error": "unrecognized memory-export shape -- expected a list of {content, ...} objects or a list of strings"}

    return {"success": True, "record_count": len(records), "sample": records[:3]}


def _normalize_memory_records(data: Any) -> List[Dict[str, Any]] | None:
    if not isinstance(data, list):
        return None
    records = []
    for item in data:
        if isinstance(item, str):
            records.append({"content": item, "metadata": {}})
        elif isinstance(item, dict) and "content" in item:
            records.append({
                "content": str(item["content"]),
                "importance": float(item.get("importance", 0.5)),
                "metadata": {k: v for k, v in item.items() if k not in ("content", "importance")},
            })
        else:
            return None
    return records


async def apply_memory_import(json_path: str, graph: Any) -> Dict[str, Any]:
    """Actually imports every record into the given MemoryGraph-shaped
    `graph` (memory_manager.graph) as a real FACT memory -- source records
    don't carry Nancy's own MemoryType taxonomy, so everything lands as
    FACT with the original data preserved in metadata (honest: this is an
    import, not a re-classification)."""
    from memory.graph import MemoryType

    plan = plan_memory_import(json_path)
    if not plan["success"]:
        return plan

    path = Path(json_path).expanduser()
    data = json.loads(path.read_text(encoding="utf-8"))
    records = _normalize_memory_records(data)

    imported = 0
    for record in records:
        graph.add_memory(
            record["content"], MemoryType.FACT,
            metadata={**record.get("metadata", {}), "imported_from": str(path)},
            importance=record.get("importance", 0.5),
        )
        imported += 1

    return {"success": True, "imported_count": imported}


def plan_skill_import(source_dir: str) -> Dict[str, Any]:
    """Real, read-only scan of a directory for Markdown skill files (any
    *.md with valid frontmatter, not just files literally named SKILL.md --
    a migrated skill from another agent may not follow that exact
    filename)."""
    source = Path(source_dir).expanduser()
    if not source.is_dir():
        return {"success": False, "error": f"no such directory: {source_dir}"}

    found = []
    for md_file in source.rglob("*.md"):
        parsed = parse_frontmatter_file(md_file)
        if parsed is None:
            continue
        meta, _ = parsed
        found.append({"path": str(md_file), "name": meta.get("name", md_file.stem), "description": meta.get("description", "")})

    return {"success": True, "found_count": len(found), "skills": found}


def apply_skill_import(source_dir: str, skill_names: List[str] | None = None) -> Dict[str, Any]:
    """Copies selected skills (or all found, if skill_names is None) into
    Nancy's real skills/ directory as skills/<name>/SKILL.md -- reuses the
    exact directory-per-skill convention skill_loader.py already expects,
    so an imported skill is immediately loadable on next restart, no
    separate registration step."""
    plan = plan_skill_import(source_dir)
    if not plan["success"]:
        return plan

    imported = []
    for entry in plan["skills"]:
        if skill_names is not None and entry["name"] not in skill_names:
            continue
        dest_dir = SKILLS_DIR / entry["name"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(entry["path"], dest_dir / "SKILL.md")
        imported.append(entry["name"])

    return {"success": True, "imported_skills": imported, "note": "restart the backend to load newly imported skills"}
