"""Tests for chunk_lemmas preservation across ``index --reset``
(Phase 1d of the 2026-05-29 ingestion-bottleneck remediation plan).

Lemmas are content-derived but expensive to recompute (~5-10 min per
language with LatinCy spaCy). chunk_ids are content-hashed, so an
unchanged chunk in a re-ingest keeps the same id; preserving lemmas
keyed by chunk_id means a content-stable re-ingest can skip
lemmatize entirely.

The mechanism: ``_maybe_snapshot_pre_index`` copies the live DB to
``.bak.pre-index`` before ``--reset`` unlinks it;
``_maybe_restore_preserved_state_from_snapshot`` reattaches that
backup into the fresh DB and copies chunk_lemmas back in;
``_sweep_orphan_chunk_lemmas`` drops rows whose chunk text changed
(so the chunk_id no longer matches anything in ``chunks``).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index


def _run_index(db: Path, jsonl: Path, *, reset: bool) -> None:
    """Drive ``cmd_index`` directly so we exercise the snapshot/restore
    helpers under the same Namespace shape argparse builds."""

    args = argparse.Namespace(db=db, input=jsonl, reset=reset)
    rc = cmd_index(args)
    assert rc == 0


def test_chunk_lemmas_survive_reindex_when_content_unchanged(tmp_path: Path):
    db = tmp_path / "lemmas.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(chunk_id="a", text="alpha beta gamma"),
                make_chunk(chunk_id="b", text="delta epsilon zeta"),
            ]
        )
    )
    _run_index(db, jsonl, reset=False)

    # Plant chunk_lemmas the way `terms lemmatize` would. Use the
    # real schema so FK enforcement is exercised.
    conn = store.open_db(db)
    conn.executemany(
        "INSERT INTO chunk_lemmas "
        "(chunk_id, token_index, surface_form, surface_start, surface_end, lemma) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("a", 0, "alpha", 0, 5, "alpha"),
            ("a", 1, "beta", 6, 10, "beta"),
            ("b", 0, "delta", 0, 5, "delta"),
        ],
    )
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM chunk_lemmas").fetchone()[0] == 3
    conn.close()

    # Re-index with --reset and the same JSONL. content-stable →
    # every chunk_id survives, so every lemma row should be preserved.
    _run_index(db, jsonl, reset=True)

    conn = store.open_db(db)
    remaining = conn.execute("SELECT COUNT(*) FROM chunk_lemmas").fetchone()[0]
    assert remaining == 3, f"expected 3 lemmas preserved, got {remaining}"
    # And FK integrity: every lemma still joins to a chunk.
    bad = conn.execute("PRAGMA foreign_key_check(chunk_lemmas)").fetchall()
    assert bad == [], f"FK violations after reindex: {bad}"


def test_chunk_lemmas_orphan_sweep_on_text_change(tmp_path: Path):
    """When a chunk's text changes its content-hashed chunk_id changes
    too. The restored lemma row now points at a no-longer-existent
    chunk_id; the post-insert sweep must drop it."""

    db = tmp_path / "lemmas-changed.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(chunk_id="stable", text="unchanged across reingest"),
                make_chunk(chunk_id="old_id", text="this text WILL change"),
            ]
        )
    )
    _run_index(db, jsonl, reset=False)

    conn = store.open_db(db)
    conn.executemany(
        "INSERT INTO chunk_lemmas "
        "(chunk_id, token_index, surface_form, surface_start, surface_end, lemma) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("stable", 0, "unchanged", 0, 9, "unchanged"),
            ("old_id", 0, "this", 0, 4, "this"),
        ],
    )
    conn.commit()
    conn.close()

    # Re-ingest with chunk_id 'old_id' renamed to 'new_id' — simulates
    # what the real ingester would do for a chunk whose text changed
    # (the production pipeline uses ``_make_chunk_id`` from the new
    # text; we shortcut by writing a different chunk_id directly).
    jsonl2 = tmp_path / "seed2.jsonl"
    jsonl2.write_text(
        "\n".join(
            json.dumps(c)
            for c in [
                make_chunk(chunk_id="stable", text="unchanged across reingest"),
                make_chunk(chunk_id="new_id", text="this text WILL change — and it did"),
            ]
        )
    )
    _run_index(db, jsonl2, reset=True)

    conn = store.open_db(db)
    rows = conn.execute(
        "SELECT chunk_id FROM chunk_lemmas ORDER BY chunk_id"
    ).fetchall()
    assert [r[0] for r in rows] == ["stable"], (
        f"expected only 'stable' to survive, got {rows!r}"
    )
    bad = conn.execute("PRAGMA foreign_key_check(chunk_lemmas)").fetchall()
    assert bad == [], f"orphan sweep left FK violations: {bad}"
