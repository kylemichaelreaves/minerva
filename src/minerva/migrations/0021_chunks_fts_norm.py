"""0021_chunks_fts_norm.py — normalized orthographic recall index.

Adds a ``chunks.text_norm`` column (an orthographically canonicalized
copy of ``text`` — see ``minerva.orthography.canonicalize``) and a
``chunks_fts_norm`` FTS5 index over it, matched with a canonicalized
query and fused with the exact ``chunks_fts`` in ``retrieve._bm25_search``.

Motivation: the FTS tokenizer (``unicode61 remove_diacritics 2``) folds
case + umlauts on both index and query, but not letter sequences like
``th``↔``t``. So a search for Nietzsche's historical *Mißrathenen*
missed our modernized *Mißratenen*. Canonicalizing both sides to one
form bridges it — symmetrically, so a modern query also finds a
historical index (e.g. Luther 1545). See
``docs/orthography-normalization-plan.md``.

Idempotent: a fresh DB already has the column, table, and updated
triggers from ``store/schema.py``; this migration only upgrades
pre-existing databases.

Trigger ordering: the existing INSERT/DELETE/UPDATE triggers are
dropped BEFORE the backfill ``UPDATE`` so it doesn't fire 375k pointless
``chunks_fts`` delete+reinsert cycles (the verbatim ``text`` is
unchanged); they're recreated afterward to maintain BOTH FTS shadows
going forward.

Known limitation: a direct ``UPDATE chunks SET text = …`` that does not
recompute ``text_norm`` leaves the normalized index stale for that row
until the next ``minerva index`` rebuild. The ingest path
(``store.insert_chunks``) always recomputes it, so this only affects
ad-hoc SQL cleanups — which should recompute ``text_norm`` or reindex.
"""

from __future__ import annotations

import sqlite3

from minerva import orthography

_CREATE_FTS_NORM = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts_norm USING fts5("
    "text_norm, content='chunks', content_rowid='rowid', "
    "tokenize='unicode61 remove_diacritics 2')"
)

# Each statement runs via a separate conn.execute — NOT executescript,
# whose implicit COMMIT would break the migration runner's per-version
# transaction (see migrations/__init__.apply).
_TRIGGER_STATEMENTS = (
    "DROP TRIGGER IF EXISTS chunks_ai",
    "DROP TRIGGER IF EXISTS chunks_ad",
    "DROP TRIGGER IF EXISTS chunks_au",
    """CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
        INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
        INSERT INTO chunks_fts_norm(rowid, text_norm) VALUES (new.rowid, new.text_norm);
    END""",
    """CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
        INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.rowid, old.text);
        INSERT INTO chunks_fts_norm(chunks_fts_norm, rowid, text_norm)
            VALUES('delete', old.rowid, old.text_norm);
    END""",
    """CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
        INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.rowid, old.text);
        INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
        INSERT INTO chunks_fts_norm(chunks_fts_norm, rowid, text_norm)
            VALUES('delete', old.rowid, old.text_norm);
        INSERT INTO chunks_fts_norm(rowid, text_norm) VALUES (new.rowid, new.text_norm);
    END""",
)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def apply(conn: sqlite3.Connection) -> None:
    # 1. Column (guarded — schema.py already adds it on fresh DBs).
    if not _has_column(conn, "chunks", "text_norm"):
        conn.execute("ALTER TABLE chunks ADD COLUMN text_norm TEXT")

    # 2. Drop existing triggers so the backfill UPDATE below doesn't
    #    churn the FTS shadows for every row.
    conn.execute("DROP TRIGGER IF EXISTS chunks_ai")
    conn.execute("DROP TRIGGER IF EXISTS chunks_ad")
    conn.execute("DROP TRIGGER IF EXISTS chunks_au")

    # 3. Backfill text_norm via the Python canonicalizer registered as a
    #    SQLite function, so the fold runs in one set-based UPDATE.
    conn.create_function(
        "mn_canonicalize",
        2,
        lambda text, lang: orthography.canonicalize(text or "", lang),
        deterministic=True,
    )
    conn.execute("UPDATE chunks SET text_norm = mn_canonicalize(text, lang)")

    # 4. Create + populate the normalized FTS from the column.
    conn.execute(_CREATE_FTS_NORM)
    conn.execute("INSERT INTO chunks_fts_norm(chunks_fts_norm) VALUES('rebuild')")

    # 5. Recreate triggers maintaining BOTH FTS shadows.
    for stmt in _TRIGGER_STATEMENTS:
        conn.execute(stmt)
