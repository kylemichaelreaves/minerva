"""``refs_scan_state`` orphan reaping across ``minerva index`` (#264).

The table is a skip cache keyed on ``chunk_id`` with no foreign key to
``chunks``, so nothing ever dropped its rows for deleted chunks — 31,629
of 460,235 (6.9%) in the live DB, accumulated across many re-ingests.

Untidiness is the smaller half. ``chunk_id`` is derived from content, so
a chunk deleted and later re-created with the same text gets *the same
id back* and silently inherits the stale "already scanned" marker. If a
rules module was edited in between it never fires for that chunk, and
the run exits 0 having emitted nothing — indistinguishable from a
correctly-skipped run.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index


def _run_index(db: Path, jsonl: Path, *, reset: bool = False) -> None:
    args = argparse.Namespace(db=db, input=jsonl, reset=reset)
    assert cmd_index(args) == 0


def _write(jsonl: Path, chunks: list[dict]) -> None:
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))


def _scan_state(conn) -> set[str]:
    return {
        row[0] for row in conn.execute("SELECT chunk_id FROM refs_scan_state")
    }


def test_index_reaps_scan_state_for_deleted_chunks(tmp_path: Path):
    """A scan-state row whose chunk left the corpus is dropped; the row
    for a chunk that is still there is kept."""

    db = tmp_path / "scan.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    _write(
        jsonl,
        [
            make_chunk(chunk_id="stays", text="this chunk is in both ingests"),
            make_chunk(chunk_id="goes", text="this chunk is dropped"),
        ],
    )
    _run_index(db, jsonl)

    conn = store.open_db(db)
    conn.executemany(
        "INSERT INTO refs_scan_state(chunk_id, text_hash) VALUES (?, ?)",
        [("stays", "h1"), ("goes", "h2")],
    )
    conn.commit()
    assert _scan_state(conn) == {"stays", "goes"}
    conn.close()

    # Second ingest drops one chunk.
    _write(jsonl, [make_chunk(chunk_id="stays", text="this chunk is in both ingests")])
    _run_index(db, jsonl)

    conn = store.open_db(db)
    assert _scan_state(conn) == {"stays"}
    conn.close()


def test_recreated_chunk_does_not_inherit_stale_scanned_marker(tmp_path: Path):
    """The defect that makes this more than tidiness: a chunk deleted and
    re-created gets the same content-derived id back, so without the reap
    it inherits the marker saying it was already scanned."""

    db = tmp_path / "recreate.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    both = [
        make_chunk(chunk_id="keeper", text="always present"),
        make_chunk(chunk_id="cycles", text="deleted, then restored verbatim"),
    ]
    _write(jsonl, both)
    _run_index(db, jsonl)

    conn = store.open_db(db)
    conn.executemany(
        "INSERT INTO refs_scan_state(chunk_id, text_hash) VALUES (?, ?)",
        [("keeper", "h1"), ("cycles", "h2")],
    )
    conn.commit()
    conn.close()

    # Out …
    _write(jsonl, [both[0]])
    _run_index(db, jsonl)
    # … and back in, byte-identical, so the id is identical too.
    _write(jsonl, both)
    _run_index(db, jsonl)

    conn = store.open_db(db)
    assert conn.execute(
        "SELECT 1 FROM chunks WHERE chunk_id = 'cycles'"
    ).fetchone() is not None, "test precondition: the chunk came back"
    assert "cycles" not in _scan_state(conn), (
        "the re-created chunk inherited its old scanned marker, so a rules "
        "module edited in between would never fire for it"
    )
    conn.close()


def test_reap_is_a_noop_when_every_chunk_survives(tmp_path: Path):
    """The common case — a content-stable re-index — must not touch a
    single row, so the skip cache keeps doing its job."""

    db = tmp_path / "stable.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    _write(jsonl, [make_chunk(chunk_id="c1", text="unchanged text")])
    _run_index(db, jsonl)

    conn = store.open_db(db)
    conn.execute(
        "INSERT INTO refs_scan_state(chunk_id, text_hash) VALUES ('c1', 'h1')"
    )
    conn.commit()
    conn.close()

    _run_index(db, jsonl)

    conn = store.open_db(db)
    assert _scan_state(conn) == {"c1"}
    conn.close()
