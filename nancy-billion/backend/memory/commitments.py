"""Real commitment/promise extraction -- ported from OpenClaw's commitments
extension. After a chat turn that plausibly contains a promise or follow-up
("I'll send that tomorrow", "remind me to call the dentist"), a real LLM
call (via llm_task.structured_llm_call, Batch 1) extracts it into a
persisted CommitmentStore; a daily heartbeat resurfaces anything overdue via
Telegram, so Nancy can proactively follow up instead of only reacting when
asked.

Cheap regex pre-filter before the LLM call is deliberate -- calling an LLM
on every single chat turn just to check "was there a commitment in that?"
would add real latency/cost to every message, the same tradeoff already
made for _WANTS_TOOLS_RE gating Claude's tool-use loop in main_new.py. Only
turns that plausibly contain a commitment pay for the extraction call.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent.parent / "data" / "commitments.json"

_PROMISE_HINT_RE = re.compile(
    r"\b(i'll|i will|remind me|let's check|i promise|don't forget|make sure (i|to)|"
    r"follow up|next time|going to (send|do|check|call|email|finish)|"
    r"by (tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|next week|end of day))\b",
    re.IGNORECASE,
)

_COMMITMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "commitments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "the commitment/promise, restated plainly"},
                    "category": {"type": "string", "enum": ["event_check_in", "deadline_check", "care_check_in", "open_loop"]},
                    "sensitivity": {"type": "string", "enum": ["routine", "personal", "care"]},
                    "due_hint": {"type": "string", "description": "a relative or plain-language due time if mentioned, else empty string"},
                },
                "required": ["text", "category", "sensitivity"],
            },
        }
    },
    "required": ["commitments"],
}


@dataclass
class Commitment:
    id: str
    text: str
    category: str
    sensitivity: str
    due_hint: str = ""
    created_at: float = field(default_factory=time.time)
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "text": self.text, "category": self.category, "sensitivity": self.sensitivity, "due_hint": self.due_hint, "created_at": self.created_at, "resolved": self.resolved}


def _load() -> List[Dict[str, Any]]:
    if not STORE_PATH.exists():
        return []
    try:
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(items: List[Dict[str, Any]]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(items, indent=2), encoding="utf-8")


def add_commitment(text: str, category: str, sensitivity: str, due_hint: str = "") -> Commitment:
    items = _load()
    # Dedup: skip if a very similar unresolved commitment already exists,
    # so a topic repeated across turns doesn't spam duplicate entries.
    for existing in items:
        if not existing.get("resolved") and existing.get("text", "").strip().lower() == text.strip().lower():
            return Commitment(**existing)
    commitment = Commitment(id=uuid.uuid4().hex[:12], text=text, category=category, sensitivity=sensitivity, due_hint=due_hint)
    items.append(commitment.to_dict())
    _save(items)
    return commitment


def list_commitments(include_resolved: bool = False) -> List[Commitment]:
    items = _load()
    return [Commitment(**i) for i in items if include_resolved or not i.get("resolved")]


def resolve_commitment(commitment_id: str) -> bool:
    items = _load()
    for item in items:
        if item["id"] == commitment_id:
            item["resolved"] = True
            _save(items)
            return True
    return False


def might_contain_commitment(text: str) -> bool:
    return bool(_PROMISE_HINT_RE.search(text))


async def extract_commitments(user_text: str, assistant_text: str) -> List[Commitment]:
    """Real LLM-backed extraction, gated behind might_contain_commitment()
    at the call site (see main_new.py) so this never runs on ordinary chat.
    Returns an empty list (never raises) on any extraction failure."""
    from llm_task import structured_llm_call

    prompt = (
        "Extract any real commitments, promises, or follow-ups from this exchange -- things the "
        "user said they'd do, or asked to be reminded/followed up about. If there are none, return "
        f"an empty list.\n\nUser: {user_text}\nAssistant: {assistant_text}"
    )
    result = await structured_llm_call(prompt, _COMMITMENT_SCHEMA, max_tokens=300)
    if not result.get("success"):
        logger.info("commitments: extraction failed, skipping: %s", result.get("error"))
        return []

    out = []
    for item in result["data"].get("commitments", []):
        try:
            out.append(add_commitment(item["text"], item["category"], item["sensitivity"], item.get("due_hint", "")))
        except Exception as e:
            logger.warning("commitments: failed to add extracted commitment %r: %s", item, e)
    return out


def format_overdue_reminder() -> Optional[str]:
    """Formats a real Telegram-ready reminder message for unresolved
    commitments -- returns None (not an empty string) when there's nothing
    to report, so the caller can distinguish "checked, nothing due" from
    "here's an empty message"."""
    open_items = list_commitments(include_resolved=False)
    if not open_items:
        return None
    lines = ["Here's what's still open:"]
    for c in open_items[:10]:
        due = f" ({c.due_hint})" if c.due_hint else ""
        lines.append(f"- {c.text}{due}")
    return "\n".join(lines)
