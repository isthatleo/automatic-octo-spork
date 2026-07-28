"""Real "scene macro" storage -- a named, ordered sequence of already-
existing tool calls (e.g. "movie mode" = dim the lights via Home Assistant +
open the media app + enable focus mode), triggerable by name in one command.
Deliberately just CRUD here: execution (main_new.py's _run_macro) replays
each step through the exact same _execute_file_tool dispatcher every other
tool call goes through, so a step's own safety gating (approval, arm_switch,
voice match) still applies exactly as if it had been called directly --
this store never bypasses that.
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

STORE_PATH = Path(__file__).parent / "data" / "macros.json"


@dataclass
class Macro:
    id: str
    name: str
    steps: List[Dict[str, Any]]  # [{"tool": str, "args": {...}}, ...], run in order
    created_at: float = field(default_factory=time.time)

    def to_public_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MacroStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._macros: Dict[str, Macro] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for m in raw:
                macro = Macro(**m)
                self._macros[macro.id] = macro
        except Exception:
            logger.exception("Failed to load macros.json -- starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(m) for m in self._macros.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list(self) -> List[Macro]:
        return sorted(self._macros.values(), key=lambda m: m.name.lower())

    def get(self, macro_id: str) -> Optional[Macro]:
        return self._macros.get(macro_id)

    def find_by_name(self, name: str) -> Optional[Macro]:
        lname = name.strip().lower()
        for m in self._macros.values():
            if m.name.strip().lower() == lname:
                return m
        return None

    def create(self, name: str, steps: List[Dict[str, Any]]) -> Macro:
        if not name.strip():
            raise ValueError("Macro name must not be empty.")
        if not steps:
            raise ValueError("A macro needs at least one step.")
        for step in steps:
            if "tool" not in step:
                raise ValueError("Every step needs a 'tool' name.")
        macro = Macro(id=uuid.uuid4().hex[:12], name=name.strip(), steps=steps)
        self._macros[macro.id] = macro
        self._save()
        return macro

    def delete(self, macro_id: str) -> bool:
        if macro_id not in self._macros:
            return False
        del self._macros[macro_id]
        self._save()
        return True


macro_store = MacroStore()
