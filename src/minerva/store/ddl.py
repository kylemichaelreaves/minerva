"""Shared DDL fragments for ``chunks_fts`` triggers, ``chunks_full`` and the
KWIC indexes on ``chunk_lemmas``."""

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
        f"CREATE TRIGGER {kw}chunks_ai AFTER INSERT ON chunks BEGIN\n{_CHUNKS_AI_BODY}\nEND;",
        f"CREATE TRIGGER {kw}chunks_ad AFTER DELETE ON chunks BEGIN\n{_CHUNKS_AD_BODY}\nEND;",
        f"CREATE TRIGGER {kw}chunks_au AFTER UPDATE ON chunks BEGIN\n{_CHUNKS_AU_BODY}\nEND;",
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
    -- Denormalised from `works.id` onto `chunks` by migration 0030, and
    -- read from `chunks` rather than `works` deliberately: `w.id` is
    -- equal to it (the join below is an equality on exactly that), but
    -- only `c.work_id` is a real column the planner can index. Reading
    -- it here is what lets `idx_chunks_work_lang_ord` serve every
    -- caller that filters on `work_id` — see #339.
    c.work_id AS work_id,
    w.author  AS author,
    w.title   AS work,
    LOWER(w.author) AS corpus,
    COALESCE(e.name, t.translator_name) AS translator,
    COALESCE(e.year, t.year)            AS edition_year,
    CASE WHEN c.edition_id IS NOT NULL THEN 1 ELSE 0 END AS is_original
FROM chunks c
LEFT JOIN editions     e ON e.id = c.edition_id
LEFT JOIN translations t ON t.id = c.translation_id
JOIN works w ON w.id = c.work_id
"""


def recreate_chunks_full_view(conn: sqlite3.Connection) -> None:
    conn.execute("DROP VIEW IF EXISTS chunks_full")
    conn.execute(CHUNKS_FULL_VIEW_SQL.strip())


# The two indexes the KWIC endpoint answers from (migration 0036, #649). Here
# rather than in the migration because the `--reset` restore drops and
# rebuilds them around its bulk copy, and the two definitions must not drift.
#
# `chunk_lemmas_by_locator` serves the page: one seek per work the page
# touches, walked in paragraph order and stopped after that work's share of
# `limit`. `work_id` leads `chunk_ord` because `ord` restarts in every work:
# ordered the other way round, as #649 shipped it, the index interleaved every
# work's opening paragraphs, and so did page 1 (#656, migration 0038).
#
# `chunk_lemmas_by_facet` serves the aggregate: every column the breakdowns
# group on, so the pass is an index-only scan. The `work_id` column without
# this index measured only 25-45% of the win (`der` 1,231 -> 778 ms, against
# 63 ms with it). It also serves a page whose filter is rare (#657): the
# matches are found in it by `pos`, and only they are read and sorted.
_KWIC_INDEXES = (
    ("chunk_lemmas_by_locator", "lemma_fold, lang_resolved, work_id, chunk_ord, surface_start"),
    ("chunk_lemmas_by_facet", "lemma_fold, lang_resolved, pos, surface_form, feats, work_id"),
)


def chunk_lemmas_kwic_index_drops() -> tuple[str, ...]:
    return tuple(f"DROP INDEX IF EXISTS {name}" for name, _cols in _KWIC_INDEXES)


def chunk_lemmas_kwic_index_creates() -> tuple[str, ...]:
    return tuple(
        f"CREATE INDEX IF NOT EXISTS {name} ON chunk_lemmas({cols})" for name, cols in _KWIC_INDEXES
    )
