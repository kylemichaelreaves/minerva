"""Shared DDL fragments for ``chunks_fts`` triggers and ``chunks_full``."""

from __future__ import annotations

import sqlite3

CHUNKS_FTS_TOKENIZE = "tokenize='unicode61 remove_diacritics 2'"

CHUNKS_FTS_NORM_CREATE = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts_norm USING fts5("
    "text_norm, content='chunks', content_rowid='rowid', "
    f"{CHUNKS_FTS_TOKENIZE})"
)

_CHUNKS_AI_BODY = (
    "    INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);\n"
    "    INSERT INTO chunks_fts_norm(rowid, text_norm) "
    "VALUES (new.rowid, new.text_norm);"
)

_CHUNKS_AD_BODY = (
    "    INSERT INTO chunks_fts(chunks_fts, rowid, text) "
    "VALUES('delete', old.rowid, old.text);\n"
    "    INSERT INTO chunks_fts_norm(chunks_fts_norm, rowid, text_norm)\n"
    "        VALUES('delete', old.rowid, old.text_norm);"
)

_CHUNKS_AU_BODY = (
    "    INSERT INTO chunks_fts(chunks_fts, rowid, text) "
    "VALUES('delete', old.rowid, old.text);\n"
    "    INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);\n"
    "    INSERT INTO chunks_fts_norm(chunks_fts_norm, rowid, text_norm)\n"
    "        VALUES('delete', old.rowid, old.text_norm);\n"
    "    INSERT INTO chunks_fts_norm(rowid, text_norm) "
    "VALUES (new.rowid, new.text_norm);"
)


def chunks_fts_trigger_drops() -> tuple[str, ...]:
    return (
        "DROP TRIGGER IF EXISTS chunks_ai",
        "DROP TRIGGER IF EXISTS chunks_ad",
        "DROP TRIGGER IF EXISTS chunks_au",
    )


def chunks_fts_trigger_creates(*, if_not_exists: bool = False) -> tuple[str, ...]:
    kw = "IF NOT EXISTS " if if_not_exists else ""
    return (
        f"CREATE TRIGGER {kw}chunks_ai AFTER INSERT ON chunks BEGIN\n"
        f"{_CHUNKS_AI_BODY}\nEND;",
        f"CREATE TRIGGER {kw}chunks_ad AFTER DELETE ON chunks BEGIN\n"
        f"{_CHUNKS_AD_BODY}\nEND;",
        f"CREATE TRIGGER {kw}chunks_au AFTER UPDATE ON chunks BEGIN\n"
        f"{_CHUNKS_AU_BODY}\nEND;",
    )


CHUNKS_FULL_VIEW_SQL = """
CREATE VIEW chunks_full AS
SELECT
    c.chunk_id,
    c.lang,
    c.section,
    c.book,
    c.page,
    c.speaker,
    c.source_file,
    c.text,
    c.ord,
    c.block_type,
    c.edition_id,
    c.translation_id,
    w.id      AS work_id,
    w.author  AS author,
    w.title   AS work,
    LOWER(w.author) AS corpus,
    COALESCE(e.name, t.translator_name) AS translator,
    COALESCE(e.year, t.year)            AS edition_year,
    CASE WHEN c.edition_id IS NOT NULL THEN 1 ELSE 0 END AS is_original
FROM chunks c
LEFT JOIN editions     e ON e.id = c.edition_id
LEFT JOIN translations t ON t.id = c.translation_id
JOIN works w ON w.id = COALESCE(e.work_id, t.work_id)
"""


def recreate_chunks_full_view(conn: sqlite3.Connection) -> None:
    conn.execute("DROP VIEW IF EXISTS chunks_full")
    conn.execute(CHUNKS_FULL_VIEW_SQL.strip())
