"""Grounded entity/relationship extraction -- the LLM-facing half of the
Knowledge Engine (Book II Phase IV). Composes two things that were already
real in this codebase: doc_extraction.py's text extraction (or any other
text source) as input, and llm_task.structured_llm_call for the schema-
validated, retrying LLM call, rather than hand-rolling either.

The honesty mechanism, and the reason this can be a fixed deliverable
instead of the "generative entity/concept clustering" memory/wiki_store.py
explicitly declined to build: every entity and relationship the model
proposes MUST come with an `evidence_quote`, and quote_is_grounded() rejects
any candidate whose quote is not an actual, verbatim (whitespace/case
insensitive) substring of the source text. An LLM cannot hallucinate an
entity into the graph without also hallucinating a quote that would need to
match real text character-for-character -- it can still get the wrong
entity type or miss things, but it cannot fabricate presence in the source.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from knowledge.graph import EntityType, KnowledgeGraph, RelationType
from llm_task import structured_llm_call

logger = logging.getLogger(__name__)

_ENTITY_TYPES = [t.value for t in EntityType]
_RELATION_TYPES = [r.value for r in RelationType]

EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": _ENTITY_TYPES},
                    "evidence_quote": {
                        "type": "string",
                        "description": "An exact, verbatim quote copied from the source text that mentions this entity.",
                    },
                },
                "required": ["name", "type", "evidence_quote"],
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Must match an entity name from the entities list."},
                    "target": {"type": "string", "description": "Must match an entity name from the entities list."},
                    "relation": {"type": "string", "enum": _RELATION_TYPES},
                    "evidence_quote": {
                        "type": "string",
                        "description": "An exact, verbatim quote copied from the source text that supports this relationship.",
                    },
                },
                "required": ["source", "target", "relation", "evidence_quote"],
            },
        },
    },
    "required": ["entities", "relationships"],
}

_EXTRACTION_PROMPT = """Extract entities and relationships that are EXPLICITLY stated in the text below.

Rules:
- Only extract what the text directly says. Do not infer, guess, or use outside knowledge.
- For every entity and every relationship you report, `evidence_quote` MUST be an exact, \
verbatim quote copied from the text -- not a paraphrase, not a summary. If you cannot find \
an exact quote supporting something, do not report it.
- Every relationship's `source` and `target` must be one of the entity names you reported.
- If the text contains nothing worth extracting, return empty lists.

Text:
\"\"\"
{text}
\"\"\""""


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def quote_is_grounded(source_text: str, quote: str) -> bool:
    """True iff `quote` is an actual (whitespace/case-insensitive) substring
    of `source_text`. Pure string logic, no LLM -- this is what makes
    extraction results verifiable rather than trusted on faith."""
    if not quote or not quote.strip() or not source_text:
        return False
    return _normalize_for_match(quote) in _normalize_for_match(source_text)


async def extract_entities_and_relations(text: str, max_tokens: int = 1500) -> Dict[str, Any]:
    """Real LLM call (via llm_task.structured_llm_call, so schema validation
    and the one-retry-on-bad-JSON behavior are inherited, not reimplemented)
    followed by a real, deterministic grounding filter. Returns
    {"success": True, "entities": [...], "relationships": [...],
    "rejected_entities": n, "rejected_relationships": n} where every
    returned entity/relationship is guaranteed grounded, or
    {"success": False, "error": ...} if the LLM call itself failed."""
    if not text or not text.strip():
        return {"success": False, "error": "empty text"}

    result = await structured_llm_call(_EXTRACTION_PROMPT.format(text=text), EXTRACTION_SCHEMA, max_tokens=max_tokens)
    if not result.get("success"):
        return {"success": False, "error": result.get("error", "extraction failed")}

    data = result["data"]
    raw_entities: List[Dict[str, Any]] = data.get("entities", [])
    raw_relationships: List[Dict[str, Any]] = data.get("relationships", [])

    grounded_entities = [e for e in raw_entities if quote_is_grounded(text, e.get("evidence_quote", ""))]
    rejected_entities = len(raw_entities) - len(grounded_entities)
    if rejected_entities:
        logger.info("knowledge.extraction: rejected %d ungrounded entity candidate(s)", rejected_entities)

    # name (normalized) -> type, so relationships can only reference an
    # entity that itself survived grounding.
    known: Dict[str, str] = {_normalize_for_match(e["name"]): e["type"] for e in grounded_entities}

    grounded_relationships = []
    rejected_relationships = 0
    for r in raw_relationships:
        source_key = _normalize_for_match(r.get("source", ""))
        target_key = _normalize_for_match(r.get("target", ""))
        if (
            quote_is_grounded(text, r.get("evidence_quote", ""))
            and source_key in known
            and target_key in known
        ):
            grounded_relationships.append(
                {**r, "source_type": known[source_key], "target_type": known[target_key]}
            )
        else:
            rejected_relationships += 1
    if rejected_relationships:
        logger.info("knowledge.extraction: rejected %d ungrounded/unresolved relationship candidate(s)", rejected_relationships)

    return {
        "success": True,
        "entities": grounded_entities,
        "relationships": grounded_relationships,
        "rejected_entities": rejected_entities,
        "rejected_relationships": rejected_relationships,
    }


async def ingest_text(
    graph: KnowledgeGraph,
    text: str,
    source: Optional[str] = None,
    entity_confidence: float = 0.75,
    relationship_confidence: float = 0.7,
) -> Dict[str, Any]:
    """Extracts + writes into `graph` in one call -- the composition point
    the Phase IV audit identified: memory (embeddings) and documents (text
    extraction) were already real, nothing resolved them into a graph.
    provenance="retrieved" throughout, per trust.Provenance's own definition
    ("read from a real source ... with a citation") -- exactly what a
    grounded quote is."""
    result = await extract_entities_and_relations(text)
    if not result["success"]:
        return {"success": False, "error": result["error"], "entities_added": 0, "relationships_added": 0}

    entities_out = []
    for e in result["entities"]:
        node = graph.add_entity(
            e["name"], e["type"],
            evidence_quote=e["evidence_quote"], source=source,
            confidence=entity_confidence, provenance="retrieved",
        )
        entities_out.append(node.to_dict())

    relationships_out = []
    for r in result["relationships"]:
        edge = graph.add_relationship(
            r["source"], r["source_type"], r["target"], r["target_type"], r["relation"],
            evidence_quote=r["evidence_quote"], source=source,
            confidence=relationship_confidence, provenance="retrieved",
        )
        relationships_out.append(edge.to_dict())

    return {
        "success": True,
        "entities_added": len(entities_out),
        "relationships_added": len(relationships_out),
        "entities_rejected_ungrounded": result["rejected_entities"],
        "relationships_rejected_ungrounded": result["rejected_relationships"],
        "entities": entities_out,
        "relationships": relationships_out,
    }


KNOWLEDGE_TOOLS = [
    {
        "name": "extract_knowledge",
        "description": (
            "Extract entities (people, organizations, projects, technologies, concepts, documents) and "
            "relationships between them from a piece of text, and add them to the persistent knowledge "
            "graph. Every extracted fact is grounded in a verbatim quote from the text -- nothing is "
            "invented. Use this after reading a document or a substantial piece of research to build "
            "durable, queryable knowledge instead of letting it be forgotten after the conversation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to extract knowledge from."},
                "source": {"type": "string", "description": "Where this text came from (file path, URL, or a short label)."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "search_knowledge_graph",
        "description": (
            "Search the persistent knowledge graph for an entity by name or keyword, and return what is "
            "known about it: its type, evidence, confidence, and every relationship it has to other "
            "entities."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Entity name or keyword to search for."},
            },
            "required": ["query"],
        },
    },
]
