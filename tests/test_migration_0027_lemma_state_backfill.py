"""Migration 0027 must seed ``chunk_lemma_state`` from ``chunk_lemmas``.

The skip predicate in ``terms lemmatize`` moved from "has lemma rows" to
"has an attempt marker at this text" (#263). On an existing index that
swap is only safe because the migration backfills: 26M ``chunk_lemmas``
rows over ~430k chunks would otherwise face an empty state table and
re-lemmatize the entire corpus on the next incremental pass — hours of
work, silently.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from conftest import make_chunk

from minerva import migrations, store
from minerva.cli.index_cmd import cmd_index
from minerva.sqlite_util import text_hash


def _db_at_0026(tmp_path: Path) -> Path:
    """A database carrying chunk_lemmas but not yet migration 0027 —
    i.e. the state every existing index is in before this upgrade."""

    path = tmp_path / "pre-0027.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(chunk_id="has-lemmas", lang="grc", text="alpha beta"),
                make_chunk(chunk_id="barren", lang="grc", text="1234 5678"),
            ]
        )
    )
    assert cmd_index(argparse.Namespace(db=path, input=jsonl, reset=False)) == 0

    conn = store.open_db(path)
    conn.executemany(
        "INSERT INTO chunk_lemmas "
        "(chunk_id, token_index, surface_form, surface_start, surface_end, lemma) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("has-lemmas", 0, "alpha", 0, 5, "alpha"),
            ("has-lemmas", 1, "beta", 6, 10, "beta"),
        ],
    )
    # Rewind past 0027 and drop the table it creates, so re-running the
    # runner replays it over data that predates it.
    #
    # `= 27`, not `>= 27`: the rewind has to unrecord exactly the
    # migration this file replays. Every *later* migration has already
    # been applied to this DB, and unrecording one replays it against a
    # schema that already carries it — 0028's `ALTER TABLE
    # refs_scan_state ADD COLUMN` fails with "duplicate column name",
    # which is a rewind bug, not a migration bug.
    conn.execute("DROP TABLE IF EXISTS chunk_lemma_state")
    conn.execute("DELETE FROM schema_migrations WHERE version = 27")
    conn.commit()
    conn.close()
    return path


def test_backfill_marks_chunks_that_already_have_lemmas(tmp_path: Path):
    path = _db_at_0026(tmp_path)

    conn = store.open_db(path)  # applies 0027
    try:
        rows = dict(
            conn.execute(
                "SELECT chunk_id, token_count FROM chunk_lemma_state"
            ).fetchall()
        )
        stored_hash = conn.execute(
            "SELECT text_hash FROM chunk_lemma_state WHERE chunk_id = 'has-lemmas'"
        ).fetchone()[0]
    finally:
        conn.close()

    # Seeded with the count it actually produced. The barren chunk left
    # no trace to seed from — by definition — so it gets one final pass.
    assert rows == {"has-lemmas": 2}
    assert stored_hash == text_hash("alpha beta")


def test_backfill_is_re_entrant(tmp_path: Path):
    """A migration that raises is rolled back and retried on the next
    ``open_db``, so 0027 must tolerate a partially-committed prior
    attempt rather than collide on the primary key."""

    path = _db_at_0026(tmp_path)
    conn = store.open_db(path)
    # `= 27` for the same reason as in `_db_at_0026`: unrecording a later
    # migration replays it against a schema that already has it.
    conn.execute("DELETE FROM schema_migrations WHERE version = 27")
    conn.commit()
    conn.close()

    conn = store.open_db(path)  # replays 0027 over its own output
    try:
        n = conn.execute("SELECT COUNT(*) FROM chunk_lemma_state").fetchone()[0]
    finally:
        conn.close()
    assert n == 1


def test_cascade_reaps_state_when_its_chunk_is_deleted(tmp_path: Path):
    """The FK is what distinguishes this table from ``refs_scan_state``,
    whose lack of one is #264. Pin it."""

    path = _db_at_0026(tmp_path)
    conn = store.open_db(path)
    try:
        assert migrations.current_version(conn) >= 27
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM chunks WHERE chunk_id = 'has-lemmas'")
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM chunk_lemma_state").fetchone()[0]
    finally:
        conn.close()
    assert n == 0


def test_fresh_database_gets_the_table(tmp_path: Path):
    conn: sqlite3.Connection = store.open_db(tmp_path / "fresh.sqlite")
    try:
        names = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()
    assert "chunk_lemma_state" in names
