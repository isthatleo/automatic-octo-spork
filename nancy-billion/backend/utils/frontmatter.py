"""Shared YAML-frontmatter + Markdown-body parsing -- generalized out of
skill_loader.py's `_parse_skill_md` so any other feature using the same
"---\\nYAML\\n---\\nMarkdown body" convention (memory/wiki_store.py's memory
wiki pages, backend/config_migration.py's config files) can reuse the exact
same, already-battle-tested parsing logic instead of a second copy.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


def parse_frontmatter(text: str) -> Optional[Tuple[Dict[str, Any], str]]:
    """Returns (metadata_dict, body_text), or None if `text` has no valid
    '---\\nYAML\\n---' frontmatter block at all. An empty/malformed YAML
    block is NOT the same as "no frontmatter" -- callers get an empty dict
    plus the intended body rather than a hard failure, matching
    skill_loader.py's original "warn and skip" tolerance for a bad file
    without special-casing it further up the call chain."""
    if not text.startswith("---"):
        return None

    parts = text.split("---", 2)
    if len(parts) < 3:
        logger.warning("frontmatter: malformed block (missing closing '---')")
        return None

    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        logger.warning("frontmatter: invalid YAML: %s", e)
        meta = {}

    if not isinstance(meta, dict):
        meta = {}

    return meta, parts[2].strip()


def parse_frontmatter_file(path: Path) -> Optional[Tuple[Dict[str, Any], str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("frontmatter: could not read %s: %s", path, e)
        return None
    return parse_frontmatter(text)


def render_frontmatter(metadata: Dict[str, Any], body: str) -> str:
    """Inverse of parse_frontmatter -- writes a real '---\\nYAML\\n---\\nbody'
    file, used by anything that generates these files (memory wiki pages)."""
    yaml_block = yaml.safe_dump(metadata, default_flow_style=False, sort_keys=False).strip()
    return f"---\n{yaml_block}\n---\n\n{body.strip()}\n"
