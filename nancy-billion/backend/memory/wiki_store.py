"""Real Memory Wiki -- ported from OpenClaw's memory-wiki extension.
Compiles durable knowledge into real Markdown pages (Obsidian-compatible:
plain YAML-frontmatter + Markdown files, no proprietary format) with
structured claim/evidence/provenance/contradiction metadata, rather than
flat memory-graph nodes. Deliberately scoped to the real, verifiable core of
the OpenClaw feature -- durable, structured, file-backed knowledge pages --
without the generative "memory palace" entity/concept clustering, which is
open-ended NLP work rather than a fixed, testable deliverable.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.frontmatter import parse_frontmatter_file, render_frontmatter

logger = logging.getLogger(__name__)

WIKI_DIR = Path(__file__).parent.parent / "data" / "memory_wiki"


@dataclass
class WikiPage:
    slug: str
    title: str
    claim: str
    evidence: List[str] = field(default_factory=list)
    provenance: str = "conversation"
    contradiction_of: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    body: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slug": self.slug, "title": self.title, "claim": self.claim, "evidence": self.evidence,
            "provenance": self.provenance, "contradiction_of": self.contradiction_of,
            "created_at": self.created_at, "body": self.body,
        }


def _slugify(title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
    return base or uuid.uuid4().hex[:8]


def _path_for(slug: str) -> Path:
    return WIKI_DIR / f"{slug}.md"


def create_page(title: str, claim: str, evidence: Optional[List[str]] = None, provenance: str = "conversation", contradiction_of: Optional[str] = None, body: str = "") -> WikiPage:
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slugify(title)
    path = _path_for(slug)
    if path.exists():
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"
        path = _path_for(slug)

    page = WikiPage(slug=slug, title=title, claim=claim, evidence=evidence or [], provenance=provenance, contradiction_of=contradiction_of, body=body)
    metadata = {"title": page.title, "claim": page.claim, "evidence": page.evidence, "provenance": page.provenance, "contradiction_of": page.contradiction_of, "created_at": page.created_at}
    path.write_text(render_frontmatter(metadata, page.body), encoding="utf-8")
    logger.info("wiki_store: created page %s", slug)
    return page


def _load_page(path: Path) -> Optional[WikiPage]:
    parsed = parse_frontmatter_file(path)
    if parsed is None:
        return None
    meta, body = parsed
    return WikiPage(
        slug=path.stem, title=str(meta.get("title", path.stem)), claim=str(meta.get("claim", "")),
        evidence=list(meta.get("evidence") or []), provenance=str(meta.get("provenance", "conversation")),
        contradiction_of=meta.get("contradiction_of"), created_at=float(meta.get("created_at", 0.0) or 0.0), body=body,
    )


def list_pages() -> List[WikiPage]:
    if not WIKI_DIR.exists():
        return []
    pages = [p for p in (_load_page(f) for f in sorted(WIKI_DIR.glob("*.md"))) if p is not None]
    pages.sort(key=lambda p: p.created_at, reverse=True)
    return pages


def get_page(slug: str) -> Optional[WikiPage]:
    path = _path_for(slug)
    if not path.exists():
        return None
    return _load_page(path)


def find_contradictions() -> List[Dict[str, Any]]:
    """Real pairs of pages that explicitly reference each other via
    contradiction_of -- surfaces genuine, author-asserted contradictions
    rather than attempting automatic claim-conflict detection."""
    pages_by_slug = {p.slug: p for p in list_pages()}
    pairs = []
    seen = set()
    for page in pages_by_slug.values():
        if page.contradiction_of and page.contradiction_of in pages_by_slug:
            key = tuple(sorted([page.slug, page.contradiction_of]))
            if key not in seen:
                seen.add(key)
                pairs.append({"a": pages_by_slug[key[0]].to_dict(), "b": pages_by_slug[key[1]].to_dict()})
    return pairs
