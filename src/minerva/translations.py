"""Persistent translation cache.

Lives in its own SQLite file (``data/translations.sqlite``) for the same
reason ``conversations.py`` does: the corpus index gets blown away on
``minerva index --reset`` and user-derived data must survive re-ingests.

Cache key is ``(source_text, target_lang)`` with a UNIQUE constraint so
duplicate inserts are idempotent under the ``INSERT OR IGNORE`` pattern.
A re-translation of the same passage skips the LLM call.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS translations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_text     TEXT NOT NULL,
    target_lang     TEXT NOT NULL,
    translated_text TEXT NOT NULL,
    literal_text    TEXT,
    model           TEXT NOT NULL,
    created_at      REAL NOT NULL,
    UNIQUE(source_text, target_lang)
);

CREATE INDEX IF NOT EXISTS translations_by_lookup
    ON translations(source_text, target_lang);
"""

# Languages the API accepts. Kept small on purpose — adding entries
# without testing the LLM prompt against them would be a quiet way to
# ship bad translations into the cache.
SUPPORTED_LANGS = frozenset({"eng", "fra", "deu"})


def open_db(path: Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    from .sqlite_util import open_sqlite

    conn = open_sqlite(
        path, SCHEMA, foreign_keys=False, check_same_thread=check_same_thread
    )
    # Idempotent migration: the original schema didn't carry
    # `literal_text`, so existing caches need the column backfilled.
    # NULL means "no literal version cached" — `lookup` treats it as a
    # partial miss and the handler re-fetches both translations from
    # the LLM so the cache progressively populates.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(translations)")}
    if "literal_text" not in cols:
        conn.execute("ALTER TABLE translations ADD COLUMN literal_text TEXT")
        conn.commit()
    return conn


def lookup(
    conn: sqlite3.Connection, *, source_text: str, target_lang: str
) -> dict[str, Any] | None:
    """Return the cached translation row, or ``None`` on a miss.

    A row whose ``literal_text`` is NULL is treated as a partial miss
    — the caller should re-fetch from the LLM so the cache populates
    both fields. (Pre-migration rows live in this state until they're
    looked up next.)
    """

    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT translated_text, literal_text, model, created_at "
        "FROM translations WHERE source_text=? AND target_lang=?",
        (source_text, target_lang),
    ).fetchone()
    if row is None:
        return None
    if row["literal_text"] is None:
        return None
    return {
        "translated_text": row["translated_text"],
        "literal_text": row["literal_text"],
        "model": row["model"],
        "created_at": row["created_at"],
    }


def insert(
    conn: sqlite3.Connection,
    *,
    source_text: str,
    target_lang: str,
    translated_text: str,
    literal_text: str,
    model: str,
    now: float | None = None,
) -> bool:
    """Insert (or overwrite) a translation. Returns ``True`` if a new
    row was added, ``False`` if (source_text, target_lang) already
    existed. ``INSERT OR REPLACE`` is used so a pre-migration row with
    NULL ``literal_text`` is upgraded on the next translation pass.
    """

    ts = time.time() if now is None else now
    cur = conn.execute(
        "INSERT OR REPLACE INTO translations"
        "(source_text, target_lang, translated_text, literal_text, model, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (source_text, target_lang, translated_text, literal_text, model, ts),
    )
    conn.commit()
    return cur.rowcount > 0


def delete_all(conn: sqlite3.Connection) -> int:
    """Wipe the cache (admin convenience). Returns deleted row count."""

    cur = conn.execute("DELETE FROM translations")
    conn.commit()
    return cur.rowcount


def count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
