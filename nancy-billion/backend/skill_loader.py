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

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

import yaml

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent / "skills"


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


def list_skills() -> List[Skill]:
    return list(_SKILLS.values())


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
    return [skill for _, skill in scored[:limit]]


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
