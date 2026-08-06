"""Knowledge Graph -- Book V Ch.7 (node/relationship types), Ch.13 (knowledge
evolution: nothing is ever silently overwritten, only merged with evidence
appended), Book II Phase IV (extraction/dedup/entity resolution/confidence
scoring).

memory/wiki_store.py already made the honest call that generative
"entity/concept clustering" was open-ended NLP work, not a fixed, testable
deliverable, and scoped itself to structured claim/evidence/provenance pages
instead. This module makes the entity/relationship version of that same
deliverable fixed and testable: every node and edge here is required to carry
at least one piece of literal evidence text, and knowledge/extraction.py
enforces that any LLM-proposed entity/relationship is rejected unless its
`evidence_quote` is an actual, verbatim substring of the source text (see
that module's `quote_is_grounded`). Nothing in this file calls an LLM --
graph operations are deterministic and unit-testable on their own.

Entity resolution deliberately uses difflib's SequenceMatcher (stdlib, no
model to load) rather than the sentence-transformers embeddings memory/graph.py
uses for content similarity: it catches near-duplicate spelling ("OANDA" vs
"Oanda", a trailing "Inc."/"the") without needing the embedding model
warmed up, at the cost of not catching true synonyms ("AI" / "Artificial
Intelligence") -- that would require real synonym knowledge, not string
similarity, and is out of scope for this pass.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class EntityType(str, Enum):
    """Deliberately scoped to the types real text can ground a mention of
    directly (Book V Ch.7 lists more -- Goals, Tasks, Ideas, Agents,
    Countries, Frameworks -- left for a future pass rather than added
    speculatively now)."""

    PERSON = "person"
    ORGANIZATION = "organization"
    PROJECT = "project"
    TECHNOLOGY = "technology"
    CONCEPT = "concept"
    DOCUMENT = "document"


class RelationType(str, Enum):
    """The exact ten relationship types Book V Ch.7 names."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DEPENDS_ON = "depends_on"
    INSPIRED_BY = "inspired_by"
    CREATED_BY = "created_by"
    USES = "uses"
    BUILT_WITH = "built_with"
    EXTENDS = "extends"
    DERIVED_FROM = "derived_from"
    RELATED_TO = "related_to"


@dataclass
class Evidence:
    """One grounded mention backing a node or edge -- the literal quote, not
    a paraphrase, plus where it came from. Book I Ch.10's "sources should be
    preserved," applied to knowledge the same way trust.py applies it to
    memory."""

    quote: str
    source: Optional[str] = None
    at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {"quote": self.quote, "source": self.source, "at": self.at}


@dataclass
class KnowledgeNode:
    id: str
    name: str
    type: EntityType
    aliases: List[str] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    confidence: float = 0.3
    provenance: str = "unknown"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self) -> None:
        # Same trust-ceiling discipline as memory/graph.py's MemoryNode --
        # a knowledge claim cannot be stored more confidently than its
        # provenance permits.
        self.confidence = _ceiling_capped(self.confidence, self.provenance)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value if isinstance(self.type, EntityType) else self.type,
            "aliases": list(self.aliases),
            "evidence": [e.to_dict() for e in self.evidence],
            "confidence": round(self.confidence, 3),
            "provenance": self.provenance,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class KnowledgeEdge:
    id: str
    source_id: str
    target_id: str
    relation: RelationType
    evidence: List[Evidence] = field(default_factory=list)
    confidence: float = 0.3
    provenance: str = "unknown"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self) -> None:
        self.confidence = _ceiling_capped(self.confidence, self.provenance)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation.value if isinstance(self.relation, RelationType) else self.relation,
            "evidence": [e.to_dict() for e in self.evidence],
            "confidence": round(self.confidence, 3),
            "provenance": self.provenance,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


#: Below this, two entity names of the same type are considered "not the
#: same entity" -- kept high (vs. memory/graph.py's 0.65 content-similarity
#: threshold) because names are short: a low threshold on short strings
#: produces false merges constantly ("Anthropic" / "Anthropic Claude" would
#: already be borderline at a looser bar).
NAME_MERGE_SIMILARITY_THRESHOLD = 0.90


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _ceiling_capped(confidence: float, provenance: str) -> float:
    """Shared by node/edge __post_init__ and by merge-time confidence
    updates, so a confidence bump on an existing node can never sneak past
    its provenance's ceiling the way a raw `max()` would."""
    try:
        from trust import CONFIDENCE_CEILING, Provenance

        ceiling = CONFIDENCE_CEILING.get(Provenance(provenance), 0.3)
    except Exception:
        ceiling = 0.3
    return max(0.0, min(float(confidence), ceiling))


class KnowledgeGraph:
    """Persisted entity/relationship graph. Mirrors memory/graph.py's
    save discipline (write to a per-call tmp file, verify it parses, only
    then os.replace() into place) for the same reason: a truncated write
    must never silently replace a good file."""

    def __init__(self, storage_path: str = "data/knowledge_graph.json"):
        self.storage_path = storage_path
        self.nodes: Dict[str, KnowledgeNode] = {}
        self.edges: Dict[str, KnowledgeEdge] = {}
        self._load_from_disk()
        logger.info(
            "KnowledgeGraph initialized with %d entities, %d relationships",
            len(self.nodes), len(self.edges),
        )

    # ------------------------------------------------------------------
    # Entity resolution + writes
    # ------------------------------------------------------------------

    def _resolve_entity(self, name: str, entity_type: EntityType) -> Optional[KnowledgeNode]:
        target = _normalize_name(name)
        best: Optional[KnowledgeNode] = None
        best_score = 0.0
        for node in self.nodes.values():
            if node.type != entity_type:
                continue
            candidates = [node.name] + node.aliases
            for candidate in candidates:
                if _normalize_name(candidate) == target:
                    return node  # exact match (name or known alias) wins outright
            score = max(
                difflib.SequenceMatcher(None, target, _normalize_name(c)).ratio()
                for c in candidates
            )
            if score > best_score:
                best_score = score
                best = node
        if best is not None and best_score >= NAME_MERGE_SIMILARITY_THRESHOLD:
            return best
        return None

    def add_entity(
        self,
        name: str,
        entity_type: EntityType | str,
        evidence_quote: Optional[str] = None,
        source: Optional[str] = None,
        confidence: float = 0.5,
        provenance: str = "unknown",
    ) -> KnowledgeNode:
        """Resolve `name` against existing entities of the same type
        (exact/alias match, then near-duplicate spelling); merge evidence
        into the match if found, else create a new node. Never raises --
        an entity with no evidence at all is still stored (confidence
        simply stays low), since callers outside knowledge/extraction.py
        (a REST caller building a graph by hand, a future different
        extractor) may not always have a quote to attach."""
        if not name or not name.strip():
            raise ValueError("entity name must be non-empty")
        entity_type = EntityType(entity_type) if not isinstance(entity_type, EntityType) else entity_type
        name = name.strip()

        existing = self._resolve_entity(name, entity_type)
        now = datetime.now().isoformat()
        if existing is not None:
            if name != existing.name and name not in existing.aliases:
                existing.aliases.append(name)
            if evidence_quote:
                existing.evidence.append(Evidence(quote=evidence_quote, source=source))
            # A repeated, independently-grounded mention is real signal --
            # let confidence rise, but never past what THIS mention's own
            # provenance would permit on its own.
            existing.confidence = max(existing.confidence, _ceiling_capped(confidence, provenance))
            existing.updated_at = now
            self._save_to_disk()
            return existing

        node_id = f"kn_{hashlib.md5(f'{_normalize_name(name)}::{entity_type.value}'.encode()).hexdigest()[:10]}"
        node = KnowledgeNode(
            id=node_id,
            name=name,
            type=entity_type,
            evidence=[Evidence(quote=evidence_quote, source=source)] if evidence_quote else [],
            confidence=confidence,
            provenance=provenance,
        )
        self.nodes[node_id] = node
        self._save_to_disk()
        return node

    def add_relationship(
        self,
        source_name: str,
        source_type: EntityType | str,
        target_name: str,
        target_type: EntityType | str,
        relation: RelationType | str,
        evidence_quote: Optional[str] = None,
        source: Optional[str] = None,
        confidence: float = 0.5,
        provenance: str = "unknown",
    ) -> KnowledgeEdge:
        """Resolves (or creates) both endpoint entities first -- a
        relationship always implies its endpoints exist -- then creates or
        merges the edge between them. Dedupes on the (source_id, target_id,
        relation) triple, same "consolidate, don't duplicate" idiom as
        memory/graph.py's add_or_merge_memory."""
        relation = RelationType(relation) if not isinstance(relation, RelationType) else relation

        source_node = self.add_entity(source_name, source_type, evidence_quote, source, confidence, provenance)
        target_node = self.add_entity(target_name, target_type, evidence_quote, source, confidence, provenance)

        for edge in self.edges.values():
            if edge.source_id == source_node.id and edge.target_id == target_node.id and edge.relation == relation:
                if evidence_quote:
                    edge.evidence.append(Evidence(quote=evidence_quote, source=source))
                edge.confidence = max(edge.confidence, _ceiling_capped(confidence, provenance))
                edge.updated_at = datetime.now().isoformat()
                self._save_to_disk()
                return edge

        edge_id = f"kge_{uuid.uuid4().hex[:10]}"
        edge = KnowledgeEdge(
            id=edge_id,
            source_id=source_node.id,
            target_id=target_node.id,
            relation=relation,
            evidence=[Evidence(quote=evidence_quote, source=source)] if evidence_quote else [],
            confidence=confidence,
            provenance=provenance,
        )
        self.edges[edge_id] = edge
        self._save_to_disk()
        return edge

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_entity(self, name: str, entity_type: Optional[EntityType | str] = None) -> Optional[KnowledgeNode]:
        target = _normalize_name(name)
        for node in self.nodes.values():
            if entity_type is not None and node.type != EntityType(entity_type):
                continue
            if _normalize_name(node.name) == target or any(_normalize_name(a) == target for a in node.aliases):
                return node
        return None

    def relationships_for(self, node_id: str) -> List[KnowledgeEdge]:
        return [e for e in self.edges.values() if e.source_id == node_id or e.target_id == node_id]

    def list_entities(self, entity_type: Optional[EntityType | str] = None) -> List[KnowledgeNode]:
        if entity_type is None:
            return list(self.nodes.values())
        entity_type = EntityType(entity_type)
        return [n for n in self.nodes.values() if n.type == entity_type]

    def search(self, query: str, top_k: int = 10) -> List[KnowledgeNode]:
        """Deterministic substring search over names/aliases/evidence text --
        no embedding model required, unlike memory search. Ranks exact
        name/alias matches first, then evidence-text hits."""
        q = _normalize_name(query)
        if not q:
            return []
        name_hits, evidence_hits = [], []
        for node in self.nodes.values():
            names = [node.name] + node.aliases
            if any(q in _normalize_name(n) for n in names):
                name_hits.append(node)
            elif any(q in ev.quote.lower() for ev in node.evidence):
                evidence_hits.append(node)
        return (name_hits + evidence_hits)[:top_k]

    def entity_summary(self, name: str) -> Optional[Dict[str, Any]]:
        node = self.get_entity(name)
        if node is None:
            return None
        edges = self.relationships_for(node.id)
        return {
            "entity": node.to_dict(),
            "relationships": [
                {
                    **edge.to_dict(),
                    "other_entity": (
                        self.nodes[edge.target_id].name if edge.source_id == node.id and edge.target_id in self.nodes
                        else self.nodes[edge.source_id].name if edge.target_id == node.id and edge.source_id in self.nodes
                        else None
                    ),
                    "direction": "outgoing" if edge.source_id == node.id else "incoming",
                }
                for edge in edges
            ],
        }

    def stats(self) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        for node in self.nodes.values():
            key = node.type.value if isinstance(node.type, EntityType) else node.type
            by_type[key] = by_type.get(key, 0) + 1
        return {"entities": len(self.nodes), "relationships": len(self.edges), "entities_by_type": by_type}

    # ------------------------------------------------------------------
    # Persistence -- same tmp-write-verify-replace discipline as
    # memory/graph.py._save_to_disk, for the same OneDrive-truncation reason.
    # ------------------------------------------------------------------

    def _save_to_disk(self) -> None:
        tmp_path = f"{self.storage_path}.{uuid.uuid4().hex}.tmp"
        try:
            data = {
                "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
                "edges": {eid: e.to_dict() for eid, e in self.edges.items()},
            }
            os.makedirs(os.path.dirname(self.storage_path) or ".", exist_ok=True)
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2)
            with open(tmp_path, "r") as f:
                json.load(f)  # verify before replacing
            os.replace(tmp_path, self.storage_path)
        except Exception as e:
            logger.error("Failed to save knowledge graph, previous file left untouched: %s", e)
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def _load_from_disk(self) -> None:
        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)

            for nid, nd in data.get("nodes", {}).items():
                self.nodes[nid] = KnowledgeNode(
                    id=nd["id"],
                    name=nd["name"],
                    type=EntityType(nd["type"]),
                    aliases=nd.get("aliases", []),
                    evidence=[Evidence(**e) for e in nd.get("evidence", [])],
                    confidence=nd.get("confidence", 0.3),
                    provenance=nd.get("provenance", "unknown"),
                    created_at=nd.get("created_at"),
                    updated_at=nd.get("updated_at"),
                )
            for eid, ed in data.get("edges", {}).items():
                self.edges[eid] = KnowledgeEdge(
                    id=ed["id"],
                    source_id=ed["source_id"],
                    target_id=ed["target_id"],
                    relation=RelationType(ed["relation"]),
                    evidence=[Evidence(**e) for e in ed.get("evidence", [])],
                    confidence=ed.get("confidence", 0.3),
                    provenance=ed.get("provenance", "unknown"),
                    created_at=ed.get("created_at"),
                    updated_at=ed.get("updated_at"),
                )
        except FileNotFoundError:
            logger.info("No existing knowledge graph found, starting fresh")
        except Exception as e:
            logger.error("Failed to load knowledge graph: %s", e)
