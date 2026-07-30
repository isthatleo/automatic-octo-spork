"""Verbatim conversation log with real SQLite FTS5 full-text search.

Complements the semantic memory graph (memory/graph.py): the graph answers
"what do I know about X" by meaning, this answers "what exactly did we say
about X, and when" by literal text -- borrowed from Hermes Agent's
full-text session search (FTS5), which the upgrade audit flagged as the
recall mode Billion was missing. Every real chat turn is appended at the
same chokepoint that populates the memory graph (see main_new.py's
_generate_response_via_hierarchy and the streaming path), so anything the
user or Billion actually said is findable verbatim later.

Storage: data/conversation_log.sqlite, an FTS5 virtual table (porter
stemming, so "deployed"/"deploying" match "deploy") plus rowid-aligned
metadata columns. FTS5 ships in Python's bundled SQLite on every platform
this project targets; if it's somehow unavailable, this module degrades to
honest no-ops (logged once) rather than breaking chat.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "conversation_log.sqlite"

_lock = threading.Lock()
_fts_available: bool | None = None


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> bool:
    """Create the FTS5 table if needed. Returns False (and remembers it) if
    this SQLite build genuinely lacks FTS5."""
    global _fts_available
    if _fts_available is False:
        return False
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS turns USING fts5("
            "content, role UNINDEXED, channel UNINDEXED, ts UNINDEXED, "
            "tokenize='porter unicode61')"
        )
        _fts_available = True
        return True
    except sqlite3.OperationalError as e:
        if _fts_available is None:
            logger.warning("SQLite FTS5 unavailable (%s) -- verbatim conversation search disabled", e)
        _fts_available = False
        return False


def log_turn(role: str, content: str, channel: str = "chat") -> None:
    """Append one real turn. Never raises -- a logging failure must never
    break the chat turn it was recording."""
    content = (content or "").strip()
    if not content:
        return
    try:
        with _lock, _connect() as conn:
            if not _ensure_schema(conn):
                return
            conn.execute(
                "INSERT INTO turns (content, role, channel, ts) VALUES (?, ?, ?, ?)",
                (content[:8000], role, channel, time.time()),
            )
    except Exception:
        logger.exception("conversation_log.log_turn failed (turn not recorded)")


def search(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Full-text search over every logged turn, newest-relevant first.
    Returns [{role, channel, ts, snippet, content}] -- snippet has the
    matched terms marked with [ and ]."""
    query = (query or "").strip()
    if not query:
        return []
    limit = max(1, min(int(limit), 30))
    try:
        with _lock, _connect() as conn:
            if not _ensure_schema(conn):
                return []
            # Quote each term to keep user text from being parsed as FTS5
            # query syntax (a stray '-' or '"' would otherwise error).
            terms = " ".join(f'"{t}"' for t in query.replace('"', " ").split())
            rows = conn.execute(
                "SELECT role, channel, ts, snippet(turns, 0, '[', ']', ' … ', 12), content "
                "FROM turns WHERE turns MATCH ? ORDER BY bm25(turns) LIMIT ?",
                (terms, limit),
            ).fetchall()
        return [
            {
                "role": r[0],
                "channel": r[1],
                "ts": r[2],
                "snippet": r[3],
                "content": r[4][:2000],
            }
            for r in rows
        ]
    except Exception:
        logger.exception("conversation_log.search failed")
        return []


def stats() -> Dict[str, Any]:
    try:
        with _lock, _connect() as conn:
            if not _ensure_schema(conn):
                return {"available": False, "turns": 0}
            (count,) = conn.execute("SELECT count(*) FROM turns").fetchone()
        return {"available": True, "turns": int(count)}
    except Exception:
        return {"available": False, "turns": 0}
