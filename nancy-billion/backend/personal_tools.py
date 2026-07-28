"""Real chat-tool wrappers around notes_store.py/expenses_store.py -- quick
notes and expense tracking for everyday "remember this"/"log this expense"
requests.
"""
from __future__ import annotations

from typing import Any, Dict

PERSONAL_TOOLS = [
    {
        "name": "add_note",
        "description": "Save a real quick note for later (persisted, not just in this conversation).",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["text"],
        },
    },
    {
        "name": "list_notes",
        "description": "List real saved notes, most recent first.",
        "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "description": "Default 50."}}, "required": []},
    },
    {
        "name": "search_notes",
        "description": "Search real saved notes by text or tag.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
    {
        "name": "track_expense",
        "description": "Log a real expense (persisted).",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "category": {"type": "string", "description": "e.g. 'groceries', 'transport', 'subscriptions'"},
                "note": {"type": "string"},
                "currency": {"type": "string", "description": "3-letter code, default USD"},
            },
            "required": ["amount", "category"],
        },
    },
    {
        "name": "list_expenses",
        "description": "List real logged expenses (optionally filtered by category), and the real total.",
        "input_schema": {"type": "object", "properties": {"category": {"type": "string"}}, "required": []},
    },
]


async def add_note(text: str, tags=None) -> Dict[str, Any]:
    from notes_store import notes_store
    note = notes_store.add(text, tags)
    return {"success": True, "note": note.to_public_dict()}


async def list_notes(limit: int = 50) -> Dict[str, Any]:
    from notes_store import notes_store
    return {"success": True, "notes": [n.to_public_dict() for n in notes_store.list(limit=limit or 50)]}


async def search_notes(query: str) -> Dict[str, Any]:
    from notes_store import notes_store
    return {"success": True, "notes": [n.to_public_dict() for n in notes_store.search(query)]}


async def track_expense(amount: float, category: str, note: str = "", currency: str = "USD") -> Dict[str, Any]:
    from expenses_store import expenses_store
    expense = expenses_store.add(amount, category, note, currency)
    return {"success": True, "expense": expense.to_public_dict()}


async def list_expenses(category: str = None) -> Dict[str, Any]:
    from expenses_store import expenses_store
    items = expenses_store.list(category=category)
    return {
        "success": True,
        "expenses": [e.to_public_dict() for e in items],
        "total": expenses_store.total(category=category),
        "count": len(items),
    }
