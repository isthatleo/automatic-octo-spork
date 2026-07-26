"""Real, persisted shared canvas -- a visual scratchpad Nancy can pin things
to during a conversation (a note, a code snippet, a link, an image), distinct
from the chat transcript and distinct from the mission kanban (missions_store.py).
Modeled on OpenClaw's canvas/workboard concept from the Hermes/OpenClaw
research, natively reimplemented: same JSON-file persistence pattern as
missions_store.py/cron_store.py, and real items broadcast live to every
connected tab via the same event_bus -> WebSocket bridge every other
real-time surface in this app already uses (main_new.py's
_broadcast_domain_event) -- no separate real-time layer to build.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

STORE_PATH = Path(__file__).parent / "data" / "canvas.json"
VALID_TYPES = {"note", "link", "code", "image"}


@dataclass
class CanvasItem:
    id: str
    type: str  # "note" | "link" | "code" | "image"
    title: str
    content: str  # note text, URL, code text, or base64 image data respectively
    language: Optional[str] = None  # for type == "code" -- drives syntax highlighting client-side
    pinned: bool = False
    created_at: float = field(default_factory=time.time)

    def to_public_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CanvasStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._items: Dict[str, CanvasItem] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for item in raw:
                ci = CanvasItem(**item)
                self._items[ci.id] = ci
        except Exception:
            logger.exception("Failed to load canvas.json — starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(i) for i in self._items.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list(self) -> List[CanvasItem]:
        # Pinned first, then newest first within each group.
        return sorted(self._items.values(), key=lambda i: (not i.pinned, -i.created_at))

    def get(self, item_id: str) -> Optional[CanvasItem]:
        return self._items.get(item_id)

    def create(self, type_: str, title: str, content: str, language: Optional[str] = None) -> CanvasItem:
        if type_ not in VALID_TYPES:
            raise ValueError(f"type must be one of {sorted(VALID_TYPES)}")
        item = CanvasItem(id=uuid.uuid4().hex[:12], type=type_, title=title, content=content, language=language)
        self._items[item.id] = item
        self._save()
        return item

    def delete(self, item_id: str) -> bool:
        if item_id not in self._items:
            return False
        del self._items[item_id]
        self._save()
        return True

    def set_pinned(self, item_id: str, pinned: bool) -> Optional[CanvasItem]:
        item = self._items.get(item_id)
        if item is None:
            return None
        item.pinned = pinned
        self._save()
        return item


canvas_store = CanvasStore()
