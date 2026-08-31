"""``chunk_lemma_state`` must survive ``index --reset`` (#263).

The attempt marker added by migration 0027 is only worth having if it
outlives a re-index. If it did not, the first ``--reset`` would wipe it
and the 859 zero-lemma chunks would silently go back to being
reprocessed on every pass — the #192 failure mode, where a table outside
the preservation path was annihilated and nobody noticed because the
symptom is just "slower".
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index


def _run_index(db: Path, jsonl: Path, *, reset: bool) -> None:
    assert cmd_index(argparse.Namespace(db=db, input=jsonl, reset=reset)) == 0


def _seed(tmp_path: Path, chunks: list[dict]) -> tuple[Path, Path]:
    db = tmp_path / "lemma-state.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    return db, jsonl


def test_attempt_state_survives_reset_when_content_unchanged(tmp_path: Path):
    db, jsonl = _seed(
        tmp_path,
        [
            make_chunk(chunk_id="productive", text="alpha beta gamma"),
            make_chunk(chunk_id="barren", text="1234 5678"),
        ],
    )
    _run_index(db, jsonl, reset=False)

    conn = store.open_db(db)
    conn.execute(
        "INSERT INTO chunk_lemmas "
        "(chunk_id, token_index, surface_form, surface_start, surface_end, lemma) "
        "VALUES ('productive', 0, 'alpha', 0, 5, 'alpha')"
    )
    conn.executemany(
        "INSERT INTO chunk_lemma_state (chunk_id, text_hash, token_count) VALUES (?, ?, ?)",
        [("productive", "hash-p", 1), ("barren", "hash-b", 0)],
    )
    conn.commit()
    conn.close()

    _run_index(db, jsonl, reset=True)

    conn = store.open_db(db)
    try:
        rows = dict(conn.execute("SELECT chunk_id, token_count FROM chunk_lemma_state").fetchall())
        bad = conn.execute("PRAGMA foreign_key_check(chunk_lemma_state)").fetchall()
    finally:
        conn.close()
    # The barren row is the one that matters: it has no chunk_lemmas
    # companion, so nothing else in the preservation path would carry it.
    assert rows == {"productive": 1, "barren": 0}
    assert bad == []


def test_attempt_state_for_a_vanished_chunk_is_swept(tmp_path: Path):
    """A chunk whose text changed enough to change its content-hashed id
    leaves its marker pointing at nothing. FK enforcement is off during
    the restore, so the cascade cannot do this — the post-insert sweep
    must."""

    db, jsonl = _seed(
        tmp_path,
        [
            make_chunk(chunk_id="stable", text="unchanged across reingest"),
            make_chunk(chunk_id="old_id", text="this text WILL change"),
        ],
    )
    _run_index(db, jsonl, reset=False)

    conn = store.open_db(db)
    conn.executemany(
        "INSERT INTO chunk_lemma_state (chunk_id, text_hash, token_count) VALUES (?, ?, ?)",
        [("stable", "hash-s", 2), ("old_id", "hash-o", 0)],
    )
    conn.commit()
    conn.close()

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
    try:
        ids = [
            r[0]
            for r in conn.execute(
                "SELECT chunk_id FROM chunk_lemma_state ORDER BY chunk_id"
            ).fetchall()
        ]
        bad = conn.execute("PRAGMA foreign_key_check(chunk_lemma_state)").fetchall()
    finally:
        conn.close()
    assert ids == ["stable"]
    assert bad == []


def test_state_only_db_is_snapshotted_and_survives_reset(tmp_path: Path):
    """A DB whose only preserved state is attempt markers — every chunk
    tried, none productive — must still take a snapshot. Gating the
    snapshot on the other four counts alone is the #274 defect, where
    ``reference_targets`` was restored only if cross_references existed.
    """

    db, jsonl = _seed(tmp_path, [make_chunk(chunk_id="barren", text="1234 5678")])
    _run_index(db, jsonl, reset=False)

    conn = store.open_db(db)
    conn.execute(
        "INSERT INTO chunk_lemma_state (chunk_id, text_hash, token_count) "
        "VALUES ('barren', 'hash-b', 0)"
    )
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM chunk_lemmas").fetchone()[0] == 0
    conn.close()

    _run_index(db, jsonl, reset=True)

    conn = store.open_db(db)
    try:
        n = conn.execute("SELECT COUNT(*) FROM chunk_lemma_state").fetchone()[0]
    finally:
        conn.close()
    assert n == 1, "attempt-marker-only DB lost its state across --reset"
