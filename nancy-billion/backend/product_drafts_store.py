"""Real, persisted product/marketing drafts from EcommerceResearchAgent.

Same JSON-file persistence pattern as missions_store.py/cron_store.py. A
draft is exactly that -- a draft. Nothing in this module (or the agent that
creates entries here) ever calls a real store's publish API; there is no
Shopify/Etsy integration wired into this codebase, and status only ever
reaches "approved" via a real Telegram approval tap (see main_new.py's
_request_approval), never automatically. Publishing for real is future
work that needs real store credentials the user hasn't provided -- this
store exists so the research/drafting half of that pipeline has somewhere
real to live in the meantime.
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

STORE_PATH = Path(__file__).parent / "data" / "product_drafts.json"

VALID_STATUSES = {"draft", "pending_approval", "approved", "rejected"}


@dataclass
class ProductDraft:
    id: str
    title: str
    description: str
    suggested_price_usd: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    ad_copy: List[str] = field(default_factory=list)
    source_research: str = ""
    status: str = "draft"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_public_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProductDraftsStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path
        self._items: Dict[str, ProductDraft] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for item in raw:
                d = ProductDraft(**item)
                self._items[d.id] = d
        except Exception:
            logger.exception("product_drafts_store: failed to load %s", self.path)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(d) for d in self._items.values()]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list(self, status: Optional[str] = None) -> List[ProductDraft]:
        items = sorted(self._items.values(), key=lambda d: d.created_at, reverse=True)
        if status:
            items = [d for d in items if d.status == status]
        return items

    def get(self, draft_id: str) -> Optional[ProductDraft]:
        return self._items.get(draft_id)

    def create(
        self, title: str, description: str, *,
        suggested_price_usd: Optional[float] = None,
        tags: Optional[List[str]] = None,
        ad_copy: Optional[List[str]] = None,
        source_research: str = "",
    ) -> ProductDraft:
        draft = ProductDraft(
            id=f"draft-{uuid.uuid4().hex[:10]}",
            title=title, description=description,
            suggested_price_usd=suggested_price_usd,
            tags=tags or [], ad_copy=ad_copy or [],
            source_research=source_research,
        )
        self._items[draft.id] = draft
        self._save()
        return draft

    def set_status(self, draft_id: str, status: str) -> Optional[ProductDraft]:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Must be one of {VALID_STATUSES}")
        draft = self._items.get(draft_id)
        if draft is None:
            return None
        draft.status = status
        draft.updated_at = time.time()
        self._save()
        return draft


product_drafts_store = ProductDraftsStore()
