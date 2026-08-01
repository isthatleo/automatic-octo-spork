"""
Database Admin Agent for Nancy/Billion.
Real SQLite introspection of Nancy's OWN known databases (conversation log,
memory-adjacent stores) -- restricted to a small allowlist under backend/data/
rather than an arbitrary path, since this reads real on-disk data. Real
table/row counts and a real PRAGMA integrity_check, never fabricated stats.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict

from .base_specialized_agent import SpecializedAgent

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_ALLOWED_DBS = {
    "conversation_log": DATA_DIR / "conversation_log.sqlite",
}


class DatabaseAdminAgent(SpecializedAgent):
    def __init__(self, settings):
        super().__init__(settings, "Database Admin Agent", "database-admin")
        self.capabilities.update({
            "description": "Real SQLite introspection (table/row counts, integrity check) of Nancy's own known databases",
            "confidence": 0.8,
            "specializations": ["sqlite-introspection", "integrity-check"],
            "tools": ["sqlite3"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "status")
        if task_type == "inspect":
            return self._inspect(task_data.get("db_name", "conversation_log"))
        if task_type == "status":
            return {"success": True, "status": "ready", "known_databases": list(_ALLOWED_DBS)}
        return await self._general(task_data)

    def _inspect(self, db_name: str) -> Dict[str, Any]:
        path = _ALLOWED_DBS.get(db_name)
        if path is None:
            return {"success": False, "error": f"Unknown database '{db_name}'. Known: {list(_ALLOWED_DBS)}"}
        if not path.exists():
            return {"success": False, "error": f"Database file does not exist yet: {path}"}
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
            try:
                tables = [r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'"
                ).fetchall()]
                table_stats = {}
                for t in tables:
                    try:
                        (count,) = conn.execute(f"SELECT count(*) FROM \"{t}\"").fetchone()
                        table_stats[t] = count
                    except sqlite3.Error as e:
                        table_stats[t] = f"error: {e}"
                (integrity,) = conn.execute("PRAGMA integrity_check").fetchone()
            finally:
                conn.close()
            return {
                "success": True, "database": db_name, "file_size_bytes": path.stat().st_size,
                "tables": table_stats, "integrity_check": integrity,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _general(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        answer = await self._llm_answer(task_data.get("query") or task_data.get("text", ""))
        return {"success": True, "response": answer or (
            "I do real SQLite introspection of Nancy's own known databases -- table/row counts and a real integrity check."
        )}
