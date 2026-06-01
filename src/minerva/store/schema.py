"""Schema DDL, connection open, meta helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .. import migrations
from ..sqlite_util import open_sqlite

SCHEMA = """
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
    CHECK ((edition_id IS NULL) <> (translation_id IS NULL))
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text,
    content='chunks',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.rowid, old.text);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.rowid, old.text);
    INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
END;

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
    return open_sqlite(
        path,
        SCHEMA,
        check_same_thread=check_same_thread,
        post_open=migrations.apply,
    )


def reset_db(path: Path) -> None:
    if path.exists():
        path.unlink()


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None
