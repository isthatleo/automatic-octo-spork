"""Conformance tests for the Knowledge Engine -- Book II Phase IV, Book V Ch.7.

Deliberately dependency-light like test_trust_conformance.py: no network, no
LLM call, no model load. knowledge/graph.py's operations are all
deterministic (entity resolution, merging, persistence), so they're tested
directly; knowledge/extraction.py's grounding filter (quote_is_grounded) is
pure string logic and is tested the same way -- the LLM call itself
(structured_llm_call) is out of scope here, same reasoning
test_trust_conformance.py gives for staying network-free.

Run:  python -m pytest backend/tests/ -q
  or: python backend/tests/test_knowledge_graph.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge.extraction import quote_is_grounded  # noqa: E402
from knowledge.graph import EntityType, KnowledgeGraph, RelationType  # noqa: E402


def _fresh_graph() -> KnowledgeGraph:
    return KnowledgeGraph(storage_path=os.path.join(tempfile.mkdtemp(), "kg.json"))


def test_new_entity_is_created_with_grounded_evidence() -> None:
    graph = _fresh_graph()
    node = graph.add_entity(
        "Anthropic", EntityType.ORGANIZATION,
        evidence_quote="Anthropic released Claude.", source="test",
        confidence=0.8, provenance="retrieved",
    )
    assert node.name == "Anthropic"
    assert node.type == EntityType.ORGANIZATION
    assert len(node.evidence) == 1
    assert node.evidence[0].quote == "Anthropic released Claude."


def test_exact_name_match_merges_instead_of_duplicating() -> None:
    graph = _fresh_graph()
    first = graph.add_entity("Anthropic", EntityType.ORGANIZATION, evidence_quote="Anthropic shipped Claude.", confidence=0.6, provenance="retrieved")
    second = graph.add_entity("Anthropic", EntityType.ORGANIZATION, evidence_quote="Anthropic is based in SF.", confidence=0.6, provenance="retrieved")
    assert first.id == second.id
    assert len(graph.nodes) == 1
    assert len(second.evidence) == 2


def test_case_insensitive_match_merges_and_records_alias() -> None:
    graph = _fresh_graph()
    graph.add_entity("OANDA", EntityType.ORGANIZATION, evidence_quote="OANDA provides FX rates.", confidence=0.6, provenance="retrieved")
    merged = graph.add_entity("Oanda", EntityType.ORGANIZATION, evidence_quote="Oanda is a broker.", confidence=0.6, provenance="retrieved")
    assert len(graph.nodes) == 1
    assert "Oanda" in merged.aliases


def test_different_types_do_not_merge() -> None:
    graph = _fresh_graph()
    graph.add_entity("Roxan", EntityType.PROJECT, evidence_quote="Roxan is a project.", confidence=0.6, provenance="retrieved")
    graph.add_entity("Roxan", EntityType.PERSON, evidence_quote="Roxan is a person.", confidence=0.6, provenance="retrieved")
    assert len(graph.nodes) == 2


def test_unrelated_names_do_not_fuzzy_merge() -> None:
    graph = _fresh_graph()
    graph.add_entity("Claude", EntityType.TECHNOLOGY, confidence=0.6, provenance="retrieved")
    graph.add_entity("Gemini", EntityType.TECHNOLOGY, confidence=0.6, provenance="retrieved")
    assert len(graph.nodes) == 2


def test_confidence_never_exceeds_provenance_ceiling() -> None:
    graph = _fresh_graph()
    node = graph.add_entity("X Corp", EntityType.ORGANIZATION, confidence=1.0, provenance="retrieved")
    assert node.confidence <= 0.9  # trust.CONFIDENCE_CEILING[RETRIEVED]


def test_relationship_creates_both_endpoints_and_edge() -> None:
    graph = _fresh_graph()
    edge = graph.add_relationship(
        "Nancy", EntityType.PROJECT, "Anthropic", EntityType.ORGANIZATION, RelationType.BUILT_WITH,
        evidence_quote="Nancy is built with Claude from Anthropic.", confidence=0.7, provenance="retrieved",
    )
    assert len(graph.nodes) == 2
    assert edge.source_id in graph.nodes and edge.target_id in graph.nodes
    summary = graph.entity_summary("Nancy")
    assert summary is not None
    assert len(summary["relationships"]) == 1
    assert summary["relationships"][0]["other_entity"] == "Anthropic"
    assert summary["relationships"][0]["direction"] == "outgoing"


def test_duplicate_relationship_merges_evidence_not_duplicates_edge() -> None:
    graph = _fresh_graph()
    graph.add_relationship("A", EntityType.PROJECT, "B", EntityType.TECHNOLOGY, RelationType.USES, evidence_quote="A uses B.", confidence=0.6, provenance="retrieved")
    graph.add_relationship("A", EntityType.PROJECT, "B", EntityType.TECHNOLOGY, RelationType.USES, evidence_quote="A really uses B a lot.", confidence=0.6, provenance="retrieved")
    assert len(graph.edges) == 1
    edge = next(iter(graph.edges.values()))
    assert len(edge.evidence) == 2


def test_search_matches_name_and_evidence() -> None:
    graph = _fresh_graph()
    graph.add_entity("Frankfurter API", EntityType.TECHNOLOGY, evidence_quote="We use the Frankfurter API for ECB reference rates.", confidence=0.6, provenance="retrieved")
    assert any(n.name == "Frankfurter API" for n in graph.search("frankfurter"))
    assert any(n.name == "Frankfurter API" for n in graph.search("ECB reference rates"))
    assert graph.search("nonexistent thing entirely") == []


def test_persistence_round_trips_entities_and_relationships() -> None:
    path = os.path.join(tempfile.mkdtemp(), "kg.json")
    graph = KnowledgeGraph(storage_path=path)
    graph.add_relationship("A", EntityType.PROJECT, "B", EntityType.TECHNOLOGY, RelationType.USES, evidence_quote="A uses B.", confidence=0.6, provenance="retrieved")

    reloaded = KnowledgeGraph(storage_path=path)
    assert len(reloaded.nodes) == 2
    assert len(reloaded.edges) == 1
    a = reloaded.get_entity("A")
    assert a is not None and len(a.evidence) == 1 and a.evidence[0].quote == "A uses B."
    edge = next(iter(reloaded.edges.values()))
    assert edge.evidence[0].quote == "A uses B."


def test_quote_is_grounded_requires_verbatim_substring() -> None:
    text = "Nancy is built with Claude from Anthropic, released in 2026."
    assert quote_is_grounded(text, "built with Claude from Anthropic")
    assert quote_is_grounded(text, "  built   with claude FROM anthropic  ")  # whitespace/case insensitive
    assert not quote_is_grounded(text, "Nancy is built with GPT-4")  # not actually in the text
    assert not quote_is_grounded(text, "")
    assert not quote_is_grounded("", "anything")


def _run() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - test harness reports, never raises
            failed += 1
            print(f"  FAIL  {test.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
