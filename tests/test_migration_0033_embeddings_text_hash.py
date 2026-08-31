"""Migration 0033 gives `embeddings` a `text_hash` column (#285).

`tei._make_chunk_id` hashes only `text[:120]`, so a chunk edited past
that point keeps its `chunk_id` and an existing `embeddings` row for it
looks current under a bare `(chunk_id, model)` check. This backfills the
column from the chunk's current text, same shape as migration 0027's
`chunk_lemma_state` backfill.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
from conftest import make_chunk

from minerva import migrations, store
from minerva.sqlite_util import text_hash


def _db_at_0032(tmp_path: Path) -> Path:
    """A database carrying an `embeddings` row but not yet migration
    0033 — the state every existing index is in before this upgrade."""

    path = tmp_path / "pre-0033.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(json.dumps(make_chunk(chunk_id="a", lang="eng", text="alpha beta")))
    conn = store.open_db(path)
    store.insert_chunks(conn, jsonl)

    # Rewind past 0033 and drop the column it adds, so re-running the
    # runner replays it over data that predates it. `= 33`, not `>= 33`,
    # for the same reason 0027's test rewinds exactly one version: every
    # later migration has already run against a schema that has this
    # column, and unrecording one of those would replay it into a
    # collision (#27's test file has the fuller explanation).
    conn.execute(
        "INSERT INTO embeddings(chunk_id, model, dim, vector) VALUES (?, ?, ?, ?)",
        ("a", "m1", 4, np.ones((4,), dtype=np.float32).tobytes()),
    )
    conn.execute("ALTER TABLE embeddings DROP COLUMN text_hash")
    conn.execute("DELETE FROM schema_migrations WHERE version = 33")
    conn.commit()
    conn.close()
    return path


def test_backfill_hashes_existing_rows_from_current_text(tmp_path: Path):
    path = _db_at_0032(tmp_path)

    conn = store.open_db(path)  # applies 0033
    try:
        stored = conn.execute("SELECT text_hash FROM embeddings WHERE chunk_id = 'a'").fetchone()[0]
    finally:
        conn.close()

    assert stored == text_hash("alpha beta")


def test_backfill_is_re_entrant(tmp_path: Path):
    """A migration that raises is rolled back and retried on the next
    `open_db`, so 0033 must tolerate a partially-committed prior
    attempt rather than collide on `ALTER TABLE ... ADD COLUMN`."""

    path = _db_at_0032(tmp_path)
    conn = store.open_db(path)
    conn.execute("DELETE FROM schema_migrations WHERE version = 33")
    conn.commit()
    conn.close()

    conn = store.open_db(path)  # replays 0033 over its own output
    try:
        n = conn.execute("SELECT COUNT(*) FROM embeddings WHERE text_hash IS NOT NULL").fetchone()[
            0
        ]
        assert migrations.current_version(conn) >= 33
    finally:
        conn.close()
    assert n == 1


def test_fresh_database_gets_the_column(tmp_path: Path):
    conn: sqlite3.Connection = store.open_db(tmp_path / "fresh.sqlite")
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(embeddings)")}
    finally:
        conn.close()
    assert "text_hash" in cols
