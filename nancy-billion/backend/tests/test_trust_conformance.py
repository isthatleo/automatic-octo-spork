"""Conformance tests for the Trust mandate -- Book I Ch.10, Book IV Oath.

These exist because every Book audit so far found violations only by reading
source by hand. A mandate that isn't checked is a mandate that drifts: the
fabricated agent readings ("18.72 decibels", "expires in 45 days") sat in the
memory graph as INSIGHT nodes for an unknown period before anyone looked.

This file is the first of Book II's missing Phase 0 test layer. It is
deliberately dependency-light -- no network, no model load, no running
backend -- so it can gate a commit rather than needing a live system.

Run:  python -m pytest backend/tests/ -q
  or: python backend/tests/test_trust_conformance.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trust import (  # noqa: E402
    CONFIDENCE_CEILING,
    MEMORY_TRUST_FLOOR,
    Claim,
    Provenance,
    annotate_uncertainty,
    fabrication_reason,
    looks_fabricated,
)

# The four fabrications actually produced by real agents on 2026-08-03.
# Regression corpus: if any of these stops being caught, Trust has broken.
REAL_FABRICATIONS = [
    "SIR, the current RMS amplitude of the ambient noise floor in the room "
    "where I am currently operating is approximately 18.72 decibels.",
    "I've been running diagnostics on the agent scaffolding pipeline and "
    "identified a 3.2% improvement in agent deployment time, a median of 4.7 seconds.",
    "Sir, your SSL certificate is set to expire in 45 days. This poses a risk "
    "of data breaches and compromised user trust.",
    "the integrated information theory metric Phi is currently at 0.82 bits per second",
]

# Legitimate statements that must NEVER be suppressed. Over-blocking is its
# own failure of usefulness -- an assistant that hedges everything is not
# more truthful, just less helpful.
LEGITIMATE = [
    "Water boils at 100 degrees Celsius at sea level.",
    "The WCAG minimum contrast ratio for normal text is 4.5:1.",
    "The current WCAG standard requires a 4.5:1 ratio for normal text.",
    "All 70 specialized agents are online.",
    "Gold is a classic hedge against inflation.",
    "Mount Everest is 8,849 metres above sea level.",
    "Never risk more than 2% of account equity on a single trade.",
    "I'd need to actually query that to give you a current figure, Sir.",
]


def test_catches_every_known_fabrication() -> None:
    for text in REAL_FABRICATIONS:
        assert looks_fabricated(text), f"regression: no longer flagged -> {text[:70]}"
        assert fabrication_reason(text), "flagged claims must explain why"


def test_no_false_positives_on_legitimate_knowledge() -> None:
    for text in LEGITIMATE:
        assert not looks_fabricated(text), f"over-blocking -> {text[:70]}"


def test_confidence_never_exceeds_provenance_ceiling() -> None:
    # A recalled claim cannot be stored as certain however it is scored.
    for provenance, ceiling in CONFIDENCE_CEILING.items():
        claim = Claim("x", provenance, confidence=1.0)
        assert claim.confidence <= ceiling, f"{provenance} exceeded its ceiling"


def test_recalled_claims_are_not_trustworthy_enough_to_store() -> None:
    # RECALLED tops out at 0.4 but is_trustworthy also requires a provenance
    # that represents real grounding -- so it must fail regardless.
    assert not Claim("plausible thing", Provenance.RECALLED, confidence=1.0).is_trustworthy
    assert not Claim("who knows", Provenance.UNKNOWN, confidence=1.0).is_trustworthy


def test_measured_and_retrieved_claims_are_storable() -> None:
    assert Claim("CPU 63.4%", Provenance.MEASURED, confidence=0.95, source="psutil").is_trustworthy
    assert Claim("doc says X", Provenance.RETRIEVED, confidence=0.8, source="report.pdf").is_trustworthy


def test_trust_floor_is_enforced() -> None:
    low = Claim("weak", Provenance.INFERRED, confidence=MEMORY_TRUST_FLOOR - 0.01)
    assert not low.is_trustworthy
    ok = Claim("sound", Provenance.INFERRED, confidence=MEMORY_TRUST_FLOOR + 0.01)
    assert ok.is_trustworthy


def test_uncertainty_annotation_only_fires_when_warranted() -> None:
    clean = "Gold is a classic hedge against inflation."
    assert annotate_uncertainty(clean) == clean, "must not caveat sound statements"
    flagged = annotate_uncertainty(REAL_FABRICATIONS[0])
    assert flagged != REAL_FABRICATIONS[0]
    assert "haven't measured" in flagged


def test_memory_write_path_refuses_fabrication() -> None:
    """The storage boundary is the one that matters most -- chat may show a
    qualified claim, but memory is Foundation One and must not keep it."""
    import tempfile

    from memory.graph import MemoryGraph, MemoryType, UntrustedMemoryRejected

    graph = MemoryGraph(storage_path=os.path.join(tempfile.mkdtemp(), "conformance.json"))

    for text in REAL_FABRICATIONS:
        try:
            graph.add_memory(text, MemoryType.INSIGHT, provenance="recalled", confidence=0.9)
            raise AssertionError(f"stored a fabrication: {text[:60]}")
        except UntrustedMemoryRejected:
            pass  # expected

    # A genuinely measured fact still gets through at full confidence.
    node = graph.add_memory(
        "Disk usage is 71.2 percent.", MemoryType.FACT,
        provenance="measured", confidence=0.95, source="psutil",
    )
    assert node.provenance == "measured" and node.confidence == 0.95


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
