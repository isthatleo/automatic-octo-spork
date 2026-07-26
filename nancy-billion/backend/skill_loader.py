"""Real, invokable skill library -- markdown procedures the agent actually
follows, not just metadata labels (see skills_store.py's own docstring: that
store creates "a real, saved, listable record of an intended capability," it
never reprograms behavior). Modeled on the Hermes/OpenClaw SKILL.md
convention: a folder per skill under skills/, a SKILL.md with YAML
frontmatter (name, description, trigger_keywords) up top and free-form
Markdown instructions below.

Skills are matched by simple keyword overlap against trigger_keywords (same
lightweight approach agents/agent_service.py's _auto_route already uses for
agent routing) and their body text is injected into the chat prompt so the
model actually follows the procedure when it's relevant.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent / "skills"
# Archived skills live one level deeper (skills/_archived/<name>/SKILL.md),
# which load_skills()'s *single-level* `skills_dir.glob("*/SKILL.md")` scan
# never reaches -- moving a skill's folder here is enough to stop it being
# matched/loaded, no separate exclusion list to keep in sync.
ARCHIVE_DIR = SKILLS_DIR / "_archived"
USAGE_STORE_PATH = Path(__file__).parent / "data" / "skill_usage.json"


@dataclass
class Skill:
    name: str
    description: str
    trigger_keywords: List[str]
    instructions: str
    path: Path


def _parse_skill_md(path: Path) -> Skill | None:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("Could not read skill file %s: %s", path, e)
        return None

    if not text.startswith("---"):
        logger.warning("Skill file %s has no YAML frontmatter, skipping", path)
        return None

    parts = text.split("---", 2)
    if len(parts) < 3:
        logger.warning("Skill file %s has malformed frontmatter, skipping", path)
        return None

    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        logger.warning("Skill file %s has invalid YAML frontmatter: %s", path, e)
        return None

    name = str(meta.get("name") or path.parent.name)
    description = str(meta.get("description", ""))
    keywords = meta.get("trigger_keywords") or []
    if isinstance(keywords, str):
        keywords = [keywords]
    instructions = parts[2].strip()

    return Skill(
        name=name,
        description=description,
        trigger_keywords=[str(k).lower() for k in keywords],
        instructions=instructions,
        path=path,
    )


def load_skills(skills_dir: Path = SKILLS_DIR) -> Dict[str, Skill]:
    skills: Dict[str, Skill] = {}
    if not skills_dir.exists():
        return skills
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        skill = _parse_skill_md(skill_md)
        if skill:
            skills[skill.name] = skill
    logger.info("Loaded %d skill(s) from %s: %s", len(skills), skills_dir, ", ".join(skills))
    return skills


# Loaded once at import time -- skills are static files, no need to re-scan
# disk on every chat turn. Restart the backend to pick up new/edited skills.
_SKILLS = load_skills()


# ---------------------------------------------------------------------------
# Usage tracking + lifecycle (archive/restore) -- real telemetry on which
# skills actually get matched into a live prompt, and a manual curation tool
# for retiring ones that never do, instead of a skill library that only ever
# grows with no visibility into what's actually being used. Deliberately
# manual, not auto-archiving on a timer: silently hiding a skill the user
# still wants available just because it's rarely triggered would be a worse
# surprise than a stale-but-present one, so this surfaces the data and lets
# a human (or an explicit agent action) decide.
# ---------------------------------------------------------------------------
def _load_usage() -> Dict[str, Dict[str, object]]:
    if not USAGE_STORE_PATH.exists():
        return {}
    try:
        return json.loads(USAGE_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to load skill_usage.json — starting empty")
        return {}


def _save_usage(usage: Dict[str, Dict[str, object]]) -> None:
    USAGE_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    USAGE_STORE_PATH.write_text(json.dumps(usage, indent=2), encoding="utf-8")


_USAGE = _load_usage()


def record_skill_match(name: str) -> None:
    entry = _USAGE.setdefault(name, {"match_count": 0, "last_matched_at": None})
    entry["match_count"] = int(entry.get("match_count", 0)) + 1
    entry["last_matched_at"] = time.time()
    _save_usage(_USAGE)


def list_skills() -> List[Skill]:
    return list(_SKILLS.values())


def list_skills_with_stats() -> List[Dict[str, object]]:
    out = []
    for skill in _SKILLS.values():
        usage = _USAGE.get(skill.name, {})
        out.append({
            "name": skill.name,
            "description": skill.description,
            "trigger_keywords": skill.trigger_keywords,
            "match_count": usage.get("match_count", 0),
            "last_matched_at": usage.get("last_matched_at"),
        })
    return out


def list_archived_skills() -> List[str]:
    if not ARCHIVE_DIR.exists():
        return []
    return sorted(p.parent.name for p in ARCHIVE_DIR.glob("*/SKILL.md"))


def archive_skill(name: str) -> bool:
    """Moves a skill's real folder to skills/_archived/ -- it stops being
    loaded/matched immediately (in-memory dict + on-disk both updated), but
    nothing is deleted, so restore_skill() can bring it straight back."""
    skill = _SKILLS.get(name)
    if skill is None:
        return False
    src_dir = skill.path.parent
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    dst_dir = ARCHIVE_DIR / src_dir.name
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    shutil.move(str(src_dir), str(dst_dir))
    del _SKILLS[name]
    return True


def restore_skill(name: str) -> bool:
    src_dir = ARCHIVE_DIR / name
    skill_md = src_dir / "SKILL.md"
    if not skill_md.exists():
        return False
    dst_dir = SKILLS_DIR / name
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    shutil.move(str(src_dir), str(dst_dir))
    restored = _parse_skill_md(dst_dir / "SKILL.md")
    if restored:
        _SKILLS[restored.name] = restored
    return True


def get_skill(name: str) -> Skill | None:
    return _SKILLS.get(name)


def match_skills(user_text: str, limit: int = 2) -> List[Skill]:
    """Keyword-overlap match, same spirit as agent_service._auto_route --
    cheap, deterministic, no extra LLM round trip just to decide which
    skill(s) might apply."""
    text_lower = user_text.lower()
    scored = []
    for skill in _SKILLS.values():
        hits = sum(1 for kw in skill.trigger_keywords if kw in text_lower)
        if hits:
            scored.append((hits, skill))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    matched = [skill for _, skill in scored[:limit]]
    for skill in matched:
        record_skill_match(skill.name)
    return matched


def build_skill_prompt_block(user_text: str) -> str:
    """Formatted block to inject into the chat prompt, or "" if nothing
    matched -- callers should just concatenate this in, same as
    _live_system_context()'s pattern in main_new.py."""
    matched = match_skills(user_text)
    if not matched:
        return ""
    parts = ["Relevant skill(s) for this request:"]
    for skill in matched:
        parts.append(f"\n### Skill: {skill.name}\n{skill.instructions}")
    return "\n".join(parts)
