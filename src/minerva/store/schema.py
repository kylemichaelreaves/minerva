"""Schema DDL, connection open, meta helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .. import migrations
from ..sqlite_util import open_sqlite, register_text_hash
from .ddl import CHUNKS_FTS_NORM_CREATE, chunks_fts_trigger_creates

_CHUNKS_FTS_TRIGGERS = "\n\n".join(chunks_fts_trigger_creates(if_not_exists=True)) + "\n\n"

SCHEMA = f"""
-- Bootstrap shape for a brand-new database. The 0003 migration may
-- rebuild `chunks` into a different shape (FKs to editions /
-- translations); subsequent migrations may further evolve it. This
-- constant intentionally only defines the columns that survive across
-- migrations PLUS the FTS virtual table and triggers — the legacy
-- typed columns that 0003 drops (`corpus`, `author`, `work`,
-- `translator`, `edition_year`) used to live here too but were
-- removed because their CREATE INDEX statements collided with the
-- post-0003 state when `open_db` ran twice.
--
-- For fresh DBs: SCHEMA creates chunks in the post-0003 shape;
-- migrations 0001/0002/0003 then no-op or trivially apply. For
-- existing DBs: SCHEMA's `IF NOT EXISTS` clauses are inert and the
-- recorded migration log skips already-applied versions.

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id        TEXT PRIMARY KEY,
    edition_id      INTEGER REFERENCES editions(id) ON DELETE CASCADE,
    translation_id  INTEGER REFERENCES translations(id) ON DELETE CASCADE,
    lang            TEXT NOT NULL,
    section         TEXT,
    book            TEXT,
    page            TEXT,
    speaker         TEXT,
    source_file     TEXT NOT NULL,
    text            TEXT NOT NULL,
    ord             INTEGER NOT NULL,
    -- Orthographically canonicalized copy of `text` (see
    -- minerva.orthography.canonicalize) feeding the `chunks_fts_norm`
    -- recall index. Computed in Python at insert time; the triggers
    -- below only mirror it into the FTS shadow. Migration 0021 adds
    -- this column + index to pre-existing databases.
    text_norm       TEXT,
    -- Structural role within the work: NULL (≡ body) / 'remark' /
    -- 'addition' / 'note' / 'blockquote'. Migration 0022 adds this to
    -- pre-existing databases and recreates the chunks_full view to
    -- surface it. See docs/block-structure-remediation-plan.md.
    block_type      TEXT,
    CHECK ((edition_id IS NULL) <> (translation_id IS NULL))
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content='chunks',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

-- Normalized recall index over the canonicalized text. Same external-
-- content + trigger pattern as chunks_fts; matched with a canonicalized
-- query and fused with the exact index in retrieve._bm25_search.
{CHUNKS_FTS_NORM_CREATE};

{_CHUNKS_FTS_TRIGGERS}

CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id  TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    model     TEXT NOT NULL,
    dim       INTEGER NOT NULL,
    vector    BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def open_db(path: Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    conn = open_sqlite(
        path,
        SCHEMA,
        check_same_thread=check_same_thread,
        post_open=migrations.apply,
    )
    # Registered once per connection, here rather than at each call site
    # in store/embeddings.py: re-registering mid-stream collides with an
    # open cursor on the same connection (`cmd_embed` interleaves reading
    # `iter_chunks_without_embeddings`'s cursor with writing through
    # `upsert_embeddings` on every batch) and raises "Error creating
    # function".
    register_text_hash(conn)
    return conn


def reset_db(path: Path) -> None:
    # Unlink the WAL/SHM siblings along with the main file. Leaving a
    # stale -wal behind means the next open of a freshly-created DB at
    # this path would attempt WAL recovery against the wrong database —
    # a documented SQLite corruption vector.
    for p in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        if p.exists():
            p.unlink()


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None
