"""``refs_scan_state`` must survive ``index --reset`` (#288).

The skip cache that exists to stop `refs build --strategy rules` doing a
full-corpus pass was not on the preservation path: `--reset` unlinks the
DB, the migrations recreate the table empty, and 428,606 markers on the
live DB went with it. Same failure mode as #263 and #192 — a table
outside the path is annihilated and nobody notices, because the symptom
is only "slower".

The mirror image of `tests/test_refs_scan_state_reaping.py`, which covers
the *over*-keeping half of the same pair (#264 part 1). Both hazards a
restore could reintroduce are already handled: orphans by that sweep, and
stale markers on a changed chunk by the `text_hash` comparison in the
skip predicate — which matters because `chunk_id` hashes only
``text[:120]`` (#285), so an edit past that point keeps the id.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index


def _run_index(db: Path, jsonl: Path, *, reset: bool) -> None:
    assert cmd_index(argparse.Namespace(db=db, input=jsonl, reset=reset)) == 0


def _seed(tmp_path: Path, chunks: list[dict]) -> tuple[Path, Path]:
    db = tmp_path / "scan-state.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    return db, jsonl


def _mark_scanned(db: Path, rows: list[tuple[str, str]]) -> None:
    conn = store.open_db(db)
    try:
        conn.executemany(
            "INSERT INTO refs_scan_state (chunk_id, text_hash) VALUES (?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _scan_state(db: Path) -> dict[str, str]:
    conn = store.open_db(db)
    try:
        return dict(conn.execute("SELECT chunk_id, text_hash FROM refs_scan_state").fetchall())
    finally:
        conn.close()


def test_scan_markers_survive_reset_when_content_unchanged(tmp_path: Path):
    """The whole point: a content-stable ``--reset`` puts back the same
    content-hashed chunk ids with the same text, so nothing needs
    rescanning — and the cache that says so must still be there."""

    db, jsonl = _seed(
        tmp_path,
        [
            make_chunk(chunk_id="c1", text="Conceive then a divided line."),
            make_chunk(chunk_id="c2", text="And the sun is the offspring."),
        ],
    )
    _run_index(db, jsonl, reset=False)
    _mark_scanned(db, [("c1", "hash-1"), ("c2", "hash-2")])

    _run_index(db, jsonl, reset=True)

    assert _scan_state(db) == {"c1": "hash-1", "c2": "hash-2"}


def test_scan_marker_for_a_vanished_chunk_is_swept(tmp_path: Path):
    """A restored marker whose chunk did not come back is an orphan — the
    table carries no foreign key, and the restore runs with FK enforcement
    off besides. The #264 part-1 sweep is what covers it, and this asserts
    the two changes compose rather than trusting that they do."""

    db, jsonl = _seed(
        tmp_path,
        [
            make_chunk(chunk_id="stable", text="unchanged across reingest"),
            make_chunk(chunk_id="old_id", text="this text WILL change"),
        ],
    )
    _run_index(db, jsonl, reset=False)
    _mark_scanned(db, [("stable", "hash-s"), ("old_id", "hash-o")])

    jsonl2 = tmp_path / "seed2.jsonl"
    jsonl2.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(chunk_id="stable", text="unchanged across reingest"),
                make_chunk(chunk_id="new_id", text="this text WILL change — it did"),
            ]
        )
    )
    _run_index(db, jsonl2, reset=True)

    assert _scan_state(db) == {"stable": "hash-s"}


def test_scan_state_only_db_is_snapshotted_and_survives_reset(tmp_path: Path):
    """A DB whose *only* preserved state is scan markers must still take a
    snapshot. Inferring one table's worth from another's count is the #274
    defect, and the reason every table here is probed in its own right."""

    db, jsonl = _seed(tmp_path, [make_chunk(chunk_id="c1")])
    _run_index(db, jsonl, reset=False)
    _mark_scanned(db, [("c1", "hash-1")])

    conn = store.open_db(db)
    try:
        for table in ("cross_references", "chunk_lemmas", "embeddings", "terms"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    finally:
        conn.close()

    _run_index(db, jsonl, reset=True)

    assert _scan_state(db) == {"c1": "hash-1"}, "scan-marker-only DB lost its cache across --reset"


def test_restore_survives_a_snapshot_taken_one_migration_back(tmp_path: Path):
    """The snapshot is taken at the top of ``cmd_index``, before the fresh
    DB is migrated — so on the first ``--reset`` after a migration that
    adds a column, the live table has a column the snapshot does not.

    Copying by the live column list raises ``no such column`` and takes
    the whole index run with it, losing the markers this path exists to
    keep. Migration 0028 (``refs_scan_state.rules_hash``, #287) is the
    first column-add to an already-preserved table, and every existing
    DB walks through this window exactly once.
    """

    db, jsonl = _seed(tmp_path, [make_chunk(chunk_id="c1", text="Sokrates.")])
    _run_index(db, jsonl, reset=False)
    _mark_scanned(db, [("c1", "hash-1")])

    # Put the DB back to how 0027 left it: the column gone and the
    # migration unrecorded, so the fresh DB re-applies it. Raw connection
    # deliberately — `store.open_db` would migrate it straight back.
    raw = sqlite3.connect(db)
    try:
        raw.execute("ALTER TABLE refs_scan_state DROP COLUMN rules_hash")
        raw.execute("DELETE FROM schema_migrations WHERE version = 28")
        raw.commit()
    finally:
        raw.close()

    _run_index(db, jsonl, reset=True)

    assert _scan_state(db) == {"c1": "hash-1"}
    conn = store.open_db(db)
    try:
        assert (
            conn.execute("SELECT rules_hash FROM refs_scan_state WHERE chunk_id = 'c1'").fetchone()[
                0
            ]
            is None
        ), (
            "a marker restored from a pre-0028 snapshot carries no rules "
            "hash — NULL is what buys it exactly one rescan"
        )
    finally:
        conn.close()


def test_non_reset_reindex_leaves_a_populated_cache_alone(tmp_path: Path):
    """The live table is never wiped by a non-reset run, so the restore
    must not fire — ``refs_scan_state.chunk_id`` is a PRIMARY KEY and a
    second copy of the same rows is a constraint failure, not a no-op."""

    db, jsonl = _seed(tmp_path, [make_chunk(chunk_id="c1")])
    _run_index(db, jsonl, reset=True)
    _mark_scanned(db, [("c1", "hash-1")])

    # Two more non-reset passes: the first writes the snapshot the second
    # would restore from, which is the window where a missing guard bites.
    _run_index(db, jsonl, reset=False)
    _run_index(db, jsonl, reset=False)

    assert _scan_state(db) == {"c1": "hash-1"}
