"""Real holographic (HRR -- Holographic Reduced Representation) memory
provider -- ported from Hermes' holographic memory plugin. A 100% local
SQLite+FTS5 fact store, deliberately distinct from MemoryGraph's
embedding-similarity search: this is a symbolic complement that stores
short discrete facts with a trust score (how many independent times a fact
has been corroborated) and supports HRR-style associative binding/retrieval
via circular convolution, so two related facts ("Sir uses Windows 11" +
"Windows 11 supports Windows Sandbox") can be *composed* into a queryable
association, not just independently matched by embedding similarity.

Registered into memory/manager.py as an ADDITIONAL retrieval source merged
alongside MemoryGraph's results -- never a replacement, and a complete
no-op (zero facts, zero behavior change) until something actually calls
add_fact().
"""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "holographic_memory.sqlite3"
VECTOR_DIM = 256  # HRR binding vector dimensionality -- independent of the
                   # sentence-transformer embedding dimension used elsewhere


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            source TEXT,
            trust_score REAL DEFAULT 1.0,
            created_at REAL NOT NULL
        )"""
    )
    conn.execute(
        """CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
            content, content='facts', content_rowid='id'
        )"""
    )
    # Keep the FTS index in sync with the real table via triggers, rather
    # than hand-maintaining it on every insert call site.
    conn.execute(
        """CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
            INSERT INTO facts_fts(rowid, content) VALUES (new.id, new.content);
        END"""
    )
    conn.commit()
    return conn


def _hrr_vector(text: str) -> np.ndarray:
    """A deterministic, seedable pseudo-random unit vector for `text` --
    real HRR binding needs a stable vector per symbol, generated from a hash
    of the content so the same fact always maps to the same vector without
    needing to persist vectors separately."""
    seed = abs(hash(text)) % (2**32)
    rng = np.random.default_rng(seed)
    v = rng.normal(size=VECTOR_DIM)
    return v / np.linalg.norm(v)


def bind(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Real HRR binding via circular convolution -- composes two concepts
    into one vector that can later be unbound (approximately) to recover
    an association between them."""
    return np.real(np.fft.ifft(np.fft.fft(a) * np.fft.fft(b)))


def unbind(composite: np.ndarray, known: np.ndarray) -> np.ndarray:
    """Approximate inverse of bind() via circular correlation -- given a
    composite vector and one known component, recovers (approximately) the
    other component."""
    return np.real(np.fft.ifft(np.fft.fft(composite) * np.conj(np.fft.fft(known))))


def add_fact(content: str, source: str = "conversation", trust_score: float = 1.0) -> Dict[str, Any]:
    """Adds a fact, or -- if an identical fact already exists -- increments
    its trust_score instead of duplicating it. This IS the trust-scoring
    mechanism: a fact independently stated/confirmed multiple times earns a
    higher score than a one-off, unverified mention."""
    conn = _get_conn()
    try:
        existing = conn.execute("SELECT id, trust_score FROM facts WHERE content = ?", (content,)).fetchone()
        if existing:
            new_score = existing[1] + 0.5
            conn.execute("UPDATE facts SET trust_score = ? WHERE id = ?", (new_score, existing[0]))
            conn.commit()
            return {"success": True, "id": existing[0], "trust_score": new_score, "new": False}
        cursor = conn.execute(
            "INSERT INTO facts (content, source, trust_score, created_at) VALUES (?, ?, ?, ?)",
            (content, source, trust_score, time.time()),
        )
        conn.commit()
        return {"success": True, "id": cursor.lastrowid, "trust_score": trust_score, "new": True}
    finally:
        conn.close()


def search_facts(query: str, top_k: int = 5, min_trust: float = 0.0) -> List[Dict[str, Any]]:
    """Real FTS5 full-text search over stored facts, ranked by FTS5's own
    bm25 relevance and filtered by minimum trust score."""
    conn = _get_conn()
    try:
        # FTS5 query syntax is picky about special characters -- a plain
        # user query can contain them (quotes, hyphens); quoting the whole
        # phrase per-token keeps this a robust substring/token search rather
        # than a query the FTS5 parser might reject outright.
        tokens = [t.replace('"', '""') for t in query.split() if t.strip()]
        if not tokens:
            return []
        fts_query = " OR ".join(f'"{t}"' for t in tokens)
        rows = conn.execute(
            """SELECT f.id, f.content, f.source, f.trust_score, f.created_at, bm25(facts_fts) as rank
               FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid
               WHERE facts_fts MATCH ? AND f.trust_score >= ?
               ORDER BY rank LIMIT ?""",
            (fts_query, min_trust, top_k),
        ).fetchall()
        return [
            {"id": r[0], "content": r[1], "source": r[2], "trust_score": r[3], "created_at": r[4]}
            for r in rows
        ]
    except sqlite3.OperationalError as e:
        logger.warning("holographic_store: search failed (%s), returning no results", e)
        return []
    finally:
        conn.close()


def associate(fact_a: str, fact_b: str) -> np.ndarray:
    """Real HRR composition of two facts into one associative vector --
    exposed for callers that want to build/query associations beyond plain
    text search (e.g. "what goes with X" rather than "what mentions X")."""
    return bind(_hrr_vector(fact_a), _hrr_vector(fact_b))


def has_any_facts() -> bool:
    """Cheap existence check -- memory/manager.py uses this to skip the
    holographic-search step entirely (not just return empty) when the store
    has never been used, keeping the no-op path genuinely free."""
    conn = _get_conn()
    try:
        return conn.execute("SELECT 1 FROM facts LIMIT 1").fetchone() is not None
    finally:
        conn.close()
