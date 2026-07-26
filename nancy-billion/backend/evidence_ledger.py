"""Real verification-evidence ledger -- ported from Hermes' verification_evidence.py.
A passive, append-only SQLite record of real command/tool executions Nancy
actually ran (terminal commands, file writes/deletes/moves), classified by
kind and outcome, with 30-day retention -- an anti-hallucination "proof"
record: if Nancy claims she ran tests or wrote a file, this ledger can
confirm whether that action genuinely executed, rather than trusting the
LLM's own retelling.

Stores a hash of output, not the full text -- this is a lightweight
existence/outcome record, not a second copy of every command's full stdout
(which could be large and is already available in each tool's own
immediate response to the caller).
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "evidence_ledger.sqlite3"
RETENTION_DAYS = 30


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            action TEXT NOT NULL,
            success INTEGER NOT NULL,
            exit_code INTEGER,
            output_hash TEXT,
            output_len INTEGER,
            timestamp REAL NOT NULL
        )"""
    )
    conn.commit()
    return conn


def record_evidence(kind: str, action: str, success: bool, exit_code: Optional[int] = None, output: Optional[str] = None) -> None:
    """kind: e.g. "terminal_command", "write_file", "delete_file", "move_file".
    action: a short human-readable description (the command, or the path
    affected). Never raises -- a ledger write failing should never break the
    real action it's recording."""
    output_hash = hashlib.sha256(output.encode("utf-8", errors="replace")).hexdigest() if output else None
    output_len = len(output) if output else 0
    try:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO evidence (kind, action, success, exit_code, output_hash, output_len, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (kind, action[:500], int(success), exit_code, output_hash, output_len, time.time()),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.warning("evidence_ledger: failed to record evidence: %s", e)


def query_evidence(limit: int = 50, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = _get_conn()
    try:
        if kind:
            rows = conn.execute(
                "SELECT id, kind, action, success, exit_code, output_hash, output_len, timestamp FROM evidence WHERE kind = ? ORDER BY id DESC LIMIT ?",
                (kind, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, kind, action, success, exit_code, output_hash, output_len, timestamp FROM evidence ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        conn.close()
    return [
        {"id": r[0], "kind": r[1], "action": r[2], "success": bool(r[3]), "exit_code": r[4], "output_hash": r[5], "output_len": r[6], "timestamp": r[7]}
        for r in rows
    ]


def purge_old(days: int = RETENTION_DAYS) -> int:
    cutoff = time.time() - (days * 86400)
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM evidence WHERE timestamp < ?", (cutoff,))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()
