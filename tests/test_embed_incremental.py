"""Tests for the incremental-embed path in `minerva embed` (Phase 1a of
the 2026-05-29 ingestion-bottleneck remediation plan).

The default code path now skips chunks that already have an
``embeddings`` row for the requested ``--model``. ``--all`` retains
the prior "re-encode everything" behaviour. The tests below seed a
small in-memory corpus, plant a partial embeddings table, and verify
that:

* ``iter_chunks_without_embeddings`` yields only the un-embedded
  chunk IDs;
* ``count_chunks_without_embeddings`` returns the same population
  size;
* a model change forces re-encoding (the skip predicate keys on
  ``(chunk_id, model)``);
* the language filter narrows both helpers correctly.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from conftest import make_chunk

from minerva import store


def _seed_chunks(tmp_path: Path) -> tuple[Path, list[dict]]:
    """Three chunks across two languages — enough to exercise the
    lang filter without ceremony."""

    chunks = [
        make_chunk(chunk_id="a", lang="eng", text="The first English chunk."),
        make_chunk(chunk_id="b", lang="eng", text="The second English chunk."),
        make_chunk(chunk_id="c", lang="grc", text="Ἑν τῇ ἀρχῇ ἦν ὁ λόγος."),
    ]
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    return jsonl, chunks


def test_iter_chunks_without_embeddings_yields_missing_only(tmp_path: Path):
    db = tmp_path / "embed-skip.sqlite"
    jsonl, _chunks = _seed_chunks(tmp_path)
    conn = store.open_db(db)
    assert store.insert_chunks(conn, jsonl) == 3

    # Plant an embedding for chunk 'a' only — 'b' and 'c' should remain
    # in the to-encode set.
    fake = np.ones((4,), dtype=np.float32)
    store.upsert_embeddings(
        conn,
        model="m1",
        dim=4,
        items=[("a", fake)],
    )

    pending = [r["chunk_id"] for r in store.iter_chunks_without_embeddings(conn, model="m1")]
    assert pending == ["b", "c"]
    assert store.count_chunks_without_embeddings(conn, model="m1") == 2


def test_model_change_forces_reencode(tmp_path: Path):
    """``embeddings.chunk_id`` is a primary key but each row records
    its ``model`` — a different model name must NOT skip the chunk
    (or we'd never re-encode after switching backends)."""

    db = tmp_path / "embed-model.sqlite"
    jsonl, _chunks = _seed_chunks(tmp_path)
    conn = store.open_db(db)
    store.insert_chunks(conn, jsonl)

    fake = np.zeros((4,), dtype=np.float32)
    store.upsert_embeddings(conn, model="m1", dim=4, items=[("a", fake)])

    # Under model `m1`: 'a' is embedded → skip.
    assert store.count_chunks_without_embeddings(conn, model="m1") == 2
    # Under model `m2`: nothing is embedded under that name → all three
    # show up as pending even though chunk_id PK collides.
    assert store.count_chunks_without_embeddings(conn, model="m2") == 3


def test_lang_filter_narrows_pending(tmp_path: Path):
    db = tmp_path / "embed-lang.sqlite"
    jsonl, _chunks = _seed_chunks(tmp_path)
    conn = store.open_db(db)
    store.insert_chunks(conn, jsonl)
    # Nothing embedded yet — language filter alone determines population.
    assert store.count_chunks_without_embeddings(conn, model="m1", lang="eng") == 2
    assert store.count_chunks_without_embeddings(conn, model="m1", lang="grc") == 1
    pending_grc = [
        r["chunk_id"]
        for r in store.iter_chunks_without_embeddings(conn, model="m1", lang="grc")
    ]
    assert pending_grc == ["c"]
