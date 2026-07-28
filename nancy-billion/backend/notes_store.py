"""Real, persisted quick notes -- for "remember this"/"note that" style
requests, distinct from the canvas (a visual pin-board) and from
memory/graph.py (semantic long-term memory extraction). This is just a
plain flat list a user can add to, list, and search -- same JSON-file
persistence pattern as canvas_store.py/missions_store.py.
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

STORE_PATH = Path(__file__).parent / "data" / "notes.json"


@dataclass
class Note:
    id: str
    text: str
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_public_dict(self) -> Dict[str, Any]:
        return asdict(self)


class NotesStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._notes: Dict[str, Note] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for item in raw:
                n = Note(**item)
                self._notes[n.id] = n
        except Exception:
            logger.exception("Failed to load notes.json — starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(n) for n in self._notes.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def add(self, text: str, tags: Optional[List[str]] = None) -> Note:
        note = Note(id=uuid.uuid4().hex[:12], text=text, tags=tags or [])
        self._notes[note.id] = note
        self._save()
        return note

    def list(self, limit: int = 50) -> List[Note]:
        return sorted(self._notes.values(), key=lambda n: -n.created_at)[:limit]

    def search(self, query: str) -> List[Note]:
        q = query.lower()
        return [n for n in self.list(limit=len(self._notes)) if q in n.text.lower() or any(q in t.lower() for t in n.tags)]

    def delete(self, note_id: str) -> bool:
        if note_id not in self._notes:
            return False
        del self._notes[note_id]
        self._save()
        return True


notes_store = NotesStore()
