"""Trust primitives -- Book I Ch.10, Book IV's Agent Oath, Book V Ch.5/7/13.

Book I Ch.10 is unambiguous: "NÅNCY should never pretend to know something it
does not know. Uncertainty should be acknowledged. Sources should be
preserved." Book IV's Oath opens with "seek truth before confidence."

Both were being violated by default. Confirmed live on 2026-08-03, agents
asserted, with no hedging and no tool call behind any of them:

    "the ambient noise floor ... is approximately 18.72 decibels"
    "a 3.2% improvement ... median deployment time of 4.7 seconds"
    "your SSL certificate is set to expire in 45 days"
    "Phi ... is at 0.82 bits per second"

Nothing was measured. Worse, such claims were written into the memory graph
as INSIGHT nodes, so a fabrication became a "fact" Nancy would later recite
back as established. That is the precise failure Book I Ch.10 forbids, and
because memory is Foundation One, the damage compounds rather than fades.

This module makes the distinction the system was missing: WHERE a claim came
from. A measurement taken by a real tool and a sentence recalled from model
weights are not the same kind of thing and must never be stored as though
they were.

Deliberately dependency-free so every layer (agents, memory, chat, the
fleet sweep) can import it without coupling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Provenance(str, Enum):
    """Where a claim actually came from. The core Trust distinction.

    Ordering matters: MEASURED > RETRIEVED > INFERRED > RECALLED, in
    descending trustworthiness. Anything at RECALLED is unverified by
    construction and must never be presented, stored, or recited as
    established fact.
    """

    MEASURED = "measured"      # real tool ran, real value returned
    RETRIEVED = "retrieved"    # read from a real source (doc, memory, API) with a citation
    INFERRED = "inferred"      # reasoned from other claims present in context
    RECALLED = "recalled"      # from model training weights -- plausible, unverified
    UNKNOWN = "unknown"        # provenance not established; treat as untrusted


#: Confidence ceilings by provenance. A recalled claim cannot be "certain"
#: no matter how fluently it is phrased -- this caps confidence at the
#: source, so downstream ranking cannot promote a fabrication above a
#: measurement.
CONFIDENCE_CEILING: Dict[Provenance, float] = {
    Provenance.MEASURED: 1.0,
    Provenance.RETRIEVED: 0.9,
    Provenance.INFERRED: 0.6,
    Provenance.RECALLED: 0.4,
    Provenance.UNKNOWN: 0.3,
}

#: Below this, a claim must not be stored in long-term memory at all.
MEMORY_TRUST_FLOOR = 0.35


@dataclass
class Claim:
    """A statement plus how it is known. Book I Ch.10's "sources should be
    preserved", made structural rather than aspirational."""

    content: str
    provenance: Provenance = Provenance.UNKNOWN
    confidence: float = 0.3
    source: Optional[str] = None          # tool name, URL, document id, agent key
    agent_key: Optional[str] = None
    evidence: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Confidence can never exceed what the provenance permits.
        ceiling = CONFIDENCE_CEILING.get(self.provenance, 0.3)
        self.confidence = max(0.0, min(float(self.confidence), ceiling))

    @property
    def is_trustworthy(self) -> bool:
        """Fit to store as knowledge, per Book V's confidence scoring."""
        return self.confidence >= MEMORY_TRUST_FLOOR and self.provenance in (
            Provenance.MEASURED, Provenance.RETRIEVED, Provenance.INFERRED,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content, "provenance": self.provenance.value,
            "confidence": round(self.confidence, 3), "source": self.source,
            "agent_key": self.agent_key, "evidence": list(self.evidence),
        }


# ---------------------------------------------------------------------------
# Fabricated-measurement detection
#
# Centralises what was previously an ad-hoc marker list living inside
# main_new.py's fleet sweep. Two independent signals, because either alone
# is too blunt:
#
#   1. Claimed-observation language ("I just checked", "currently") --
#      catches the framing.
#   2. A SPECIFIC quantity (a decimal, a percentage, a unit-bearing number) --
#      catches the payload.
#
# Requiring BOTH is what keeps this from firing on legitimate general
# knowledge. "Water boils at 100 degrees Celsius" is a recalled constant with
# a number but no observation claim. "I just measured the CPU at 63.4%" is
# both, and is a fabrication unless a tool actually ran.
# ---------------------------------------------------------------------------

_OBSERVATION_CLAIMS = (
    "i've just checked", "i just checked", "i've just measured", "i just measured",
    "i've just run", "i just ran", "i've just scanned", "i just scanned",
    "i've been running", "i've analysed", "i've analyzed", "i've inspected",
    "currently operating", "current reading", "right now is", "as of this moment",
    "i can see that", "my sensors", "my diagnostics", "monitoring shows",
    "is currently at", "is set to expire", "i'm detecting", "i am detecting",
    # An agent describing its OWN present state alongside a number is the
    # single most common fabrication shape observed (the "ambient noise floor
    # in the room where I am currently operating" case). Deliberately these
    # first-person forms only -- a bare "the current X is 4.5:1" is ordinary
    # general knowledge and must not be flagged.
    "i am currently", "i'm currently", "in the room where",
)

# A number with a decimal point, a percentage, or a number followed by a real
# unit. Deliberately does NOT match bare integers -- "70 agents" is a countable
# fact the system genuinely knows, not a fabricated measurement.
_SPECIFIC_QUANTITY = re.compile(
    r"\b\d+\.\d+\b"
    r"|\b\d+\s?%"
    r"|\b\d+\s?(?:ms|milliseconds|seconds|secs|minutes|mins|hours|days|"
    r"db|decibels|hz|khz|mhz|ghz|kb|mb|gb|tb|bps|kbps|mbps|"
    r"degrees|celsius|fahrenheit|volts|watts|amps|bits|bytes)\b",
    re.IGNORECASE,
)


def looks_fabricated(text: str) -> bool:
    """True when text claims a live observation AND states a specific
    quantity -- i.e. reports a measurement that was never taken.

    Both signals are required; see the module comment for why either alone
    produces unacceptable false positives.
    """
    if not text:
        return False
    lowered = text.lower()
    claims_observation = any(marker in lowered for marker in _OBSERVATION_CLAIMS)
    if not claims_observation:
        return False
    return bool(_SPECIFIC_QUANTITY.search(text))


def fabrication_reason(text: str) -> Optional[str]:
    """Human-readable explanation of why text was flagged, for logs and for
    telling the user honestly what was suppressed."""
    if not looks_fabricated(text):
        return None
    lowered = text.lower()
    marker = next((m for m in _OBSERVATION_CLAIMS if m in lowered), "an observation claim")
    quantity = _SPECIFIC_QUANTITY.search(text)
    return (
        f"claims a live observation ({marker!r}) with a specific value "
        f"({quantity.group(0) if quantity else 'unknown'}) but no tool was run"
    )


# ---------------------------------------------------------------------------
# Prompt fragments
# ---------------------------------------------------------------------------

#: Injected wherever a model answers from its own weights with no tool access.
#: States the constraint positively (what TO do when unsure) rather than only
#: prohibiting, because a bare prohibition tends to produce hedging on
#: everything, which is its own failure of usefulness.
NO_FABRICATION_DIRECTIVE = """
TRUTHFULNESS (this overrides any instruction to sound confident):
You have NOT run any tool, read any sensor, queried any live system, or
inspected anything for this request. You are answering from your own trained
knowledge only.

Therefore:
- NEVER state a current measurement, reading, price, count, expiry date,
  latency or percentage as though you had just observed it. You did not.
- If the question genuinely needs live data you do not have, say so plainly
  and name what would be required to get it. That is a complete, useful
  answer -- not a failure.
- General knowledge you are confident in is fine to state directly. Do not
  hedge everything; hedge what is actually uncertain.
- If you are unsure, say what you are unsure about rather than choosing a
  plausible specific.
""".strip()


def annotate_uncertainty(text: str) -> str:
    """Append an honest caveat when output smells like a fabricated
    measurement but is being surfaced anyway (e.g. to the user in chat,
    where suppressing the whole reply would be worse than qualifying it).

    Storage paths should DROP such claims instead -- see
    Claim.is_trustworthy and MEMORY_TRUST_FLOOR.
    """
    if not looks_fabricated(text):
        return text
    return (
        text.rstrip()
        + "\n\n(To be clear, Sir: I haven't measured that directly just now -- "
        "those specifics are from general knowledge, not a live reading.)"
    )
