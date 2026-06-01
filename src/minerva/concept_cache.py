"""Persistent cache for ``agent.concept_expand`` results.

Lives in its own SQLite file (``data/concept_cache.sqlite``) for the
same reason ``translations.py`` does — user-derived / LLM-derived data
must survive corpus re-ingests and process restarts.

Cache key is ``(query_norm, corpus, target_lang)``. ``query_norm`` is
the raw query lowercased, whitespace-collapsed, and stripped of
leading/trailing punctuation so trivially-equivalent phrasings share
an entry ("Who are the failures according to Nietzsche?" and "who are
the failures according to nietzsche" both normalize identically).

Value is a JSON array of target-language terms plus metadata
(model name, timestamp, hit_count). The hit counter increments on
every lookup that returns a row — surfaces "high-traffic concepts"
for inspection without an extra observability layer.

Invariants:

* Stable expansions for the same input — the first LLM result wins.
  The model might emit slightly different terms on a re-call; both
  are valid, but a stable answer reads better to the user and saves
  the LLM cost forever. Wipe via ``delete_all`` to refresh.

* No TTL. Concept→term mappings don't go stale. If we change the
  ``concept_expand`` prompt in a way that should invalidate prior
  cache rows, bump ``CACHE_VERSION`` and the lookup will treat all
  earlier rows as misses.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

# Bump when the concept_expand prompt or output contract changes in a
# way that should invalidate previously cached expansions. Lookups
# filter on this column so old rows become silent misses without
# requiring an explicit migration.
CACHE_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS concept_expansions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    query_norm  TEXT NOT NULL,
    corpus      TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    terms_json  TEXT NOT NULL,
    model       TEXT NOT NULL,
    cache_ver   INTEGER NOT NULL,
    hit_count   INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL,
    UNIQUE(query_norm, corpus, target_lang, cache_ver)
);

CREATE INDEX IF NOT EXISTS concept_expansions_by_lookup
    ON concept_expansions(query_norm, corpus, target_lang, cache_ver);
"""

_WHITESPACE_RE = re.compile(r"\s+")
_LEAD_TRAIL_PUNCT_RE = re.compile(r"^[\s\W_]+|[\s\W_]+$", re.UNICODE)


def normalize_query(query: str) -> str:
    """Canonical form used as the cache key. Lowercases, collapses
    interior whitespace, strips leading/trailing punctuation. Does
    NOT drop stopwords or stem — the concept content of a query is
    sensitive to those.
    """

    out = _WHITESPACE_RE.sub(" ", query.lower()).strip()
    out = _LEAD_TRAIL_PUNCT_RE.sub("", out)
    return out


def open_db(path: Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    from .sqlite_util import open_sqlite

    return open_sqlite(path, SCHEMA, foreign_keys=False, check_same_thread=check_same_thread)


def lookup(
    conn: sqlite3.Connection,
    *,
    query: str,
    corpus: str,
    target_lang: str,
) -> list[str] | None:
    """Return the cached terms list, or ``None`` on a miss.

    Side effect: increments ``hit_count`` on a hit. The cache exists
    to avoid the LLM call, so we tolerate one cheap UPDATE on every
    lookup that succeeds.
    """

    key = normalize_query(query)
    if not key:
        return None
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, terms_json FROM concept_expansions "
        "WHERE query_norm=? AND corpus=? AND target_lang=? AND cache_ver=?",
        (key, corpus, target_lang, CACHE_VERSION),
    ).fetchone()
    if row is None:
        return None
    try:
        terms = json.loads(row["terms_json"])
    except json.JSONDecodeError:
        return None
    if not isinstance(terms, list):
        return None
    conn.execute(
        "UPDATE concept_expansions SET hit_count = hit_count + 1 WHERE id = ?",
        (row["id"],),
    )
    conn.commit()
    return [t for t in terms if isinstance(t, str)]


def insert(
    conn: sqlite3.Connection,
    *,
    query: str,
    corpus: str,
    target_lang: str,
    terms: list[str],
    model: str,
    now: float | None = None,
) -> bool:
    """Store an expansion. Returns ``True`` if a new row was added,
    ``False`` if (query_norm, corpus, target_lang, cache_ver) already
    existed (in which case the prior result wins — see module docstring).
    """

    key = normalize_query(query)
    if not key:
        return False
    ts = time.time() if now is None else now
    cur = conn.execute(
        "INSERT OR IGNORE INTO concept_expansions"
        "(query_norm, corpus, target_lang, terms_json, model, cache_ver, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (key, corpus, target_lang, json.dumps(terms, ensure_ascii=False), model, CACHE_VERSION, ts),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_all(conn: sqlite3.Connection) -> int:
    """Wipe the cache. Useful when the prompt has changed or to
    force fresh expansions. Returns deleted row count."""

    cur = conn.execute("DELETE FROM concept_expansions")
    conn.commit()
    return cur.rowcount


def count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM concept_expansions WHERE cache_ver=?",
        (CACHE_VERSION,),
    ).fetchone()[0]


def stats_top(
    conn: sqlite3.Connection, *, limit: int = 20
) -> list[dict[str, Any]]:
    """Inspect the highest-traffic concept entries. Lightweight admin
    helper; not used in hot paths."""

    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT query_norm, corpus, target_lang, terms_json, hit_count "
        "FROM concept_expansions WHERE cache_ver=? "
        "ORDER BY hit_count DESC, created_at ASC LIMIT ?",
        (CACHE_VERSION, limit),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            terms = json.loads(r["terms_json"])
        except json.JSONDecodeError:
            terms = []
        out.append(
            {
                "query_norm": r["query_norm"],
                "corpus": r["corpus"],
                "target_lang": r["target_lang"],
                "terms": terms,
                "hit_count": r["hit_count"],
            }
        )
    return out
