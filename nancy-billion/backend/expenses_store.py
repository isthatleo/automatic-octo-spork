"""Real, persisted expense log -- for "log this expense"/"how much have I
spent on X" style requests. Same JSON-file persistence pattern as
canvas_store.py/notes_store.py.
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

STORE_PATH = Path(__file__).parent / "data" / "expenses.json"


@dataclass
class Expense:
    id: str
    amount: float
    category: str
    note: str = ""
    currency: str = "USD"
    created_at: float = field(default_factory=time.time)

    def to_public_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ExpensesStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._expenses: Dict[str, Expense] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for item in raw:
                e = Expense(**item)
                self._expenses[e.id] = e
        except Exception:
            logger.exception("Failed to load expenses.json — starting empty")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(e) for e in self._expenses.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def add(self, amount: float, category: str, note: str = "", currency: str = "USD") -> Expense:
        expense = Expense(id=uuid.uuid4().hex[:12], amount=amount, category=category, note=note, currency=currency)
        self._expenses[expense.id] = expense
        self._save()
        return expense

    def list(self, category: Optional[str] = None, limit: int = 100) -> List[Expense]:
        items = sorted(self._expenses.values(), key=lambda e: -e.created_at)
        if category:
            items = [e for e in items if e.category.lower() == category.lower()]
        return items[:limit]

    def total(self, category: Optional[str] = None) -> float:
        return round(sum(e.amount for e in self.list(category=category, limit=len(self._expenses))), 2)


expenses_store = ExpensesStore()
