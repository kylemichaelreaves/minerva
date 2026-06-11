"""Tests for the embedding-matrix cache in `store.load_all_embeddings`.

Regression guard for the audit finding that vector retrieval was
loading every embedding row + stacking into a dense matrix on each
hybrid search. The cache memoizes per connection, invalidated on
`upsert_embeddings` and on `insert_chunks` (re-ingest may rewrite ids)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from minerva import store


def _seed_translation(conn: sqlite3.Connection) -> int:
    """Set up the minimum works/translations rows that an English chunk
    needs as a FK target, returning the translation_id."""
    conn.execute(
        "INSERT INTO works(id, author, title, original_language, citation_system) "
        "VALUES (1, 'Plato', 'Republic', 'grc', 'stephanus')"
    )
    cur = conn.execute(
        "INSERT INTO translations(work_id, translator_name, year, language) "
        "VALUES (1, 'Shorey', 1969, 'eng')"
    )
    return int(cur.lastrowid)


@pytest.fixture
def conn_with_embeddings(tmp_path: Path) -> sqlite3.Connection:
    conn = store.open_db(tmp_path / "e.sqlite")
    tid = _seed_translation(conn)
    # Need at least one chunk row for `upsert_embeddings`' FK to satisfy.
    conn.execute(
        "INSERT INTO chunks(chunk_id, edition_id, translation_id, lang, "
        "source_file, text, ord) VALUES(?,?,?,?,?,?,?)",
        ("c1", None, tid, "eng", "x", "text", 0),
    )
    conn.execute(
        "INSERT INTO chunks(chunk_id, edition_id, translation_id, lang, "
        "source_file, text, ord) VALUES(?,?,?,?,?,?,?)",
        ("c2", None, tid, "eng", "x", "text", 1),
    )
    conn.commit()
    store.upsert_embeddings(
        conn,
        model="test",
        dim=3,
        items=[
            ("c1", np.array([1.0, 0.0, 0.0], dtype=np.float32)),
            ("c2", np.array([0.0, 1.0, 0.0], dtype=np.float32)),
        ],
    )
    store.invalidate_embedding_cache()
    return conn


def test_load_all_embeddings_caches_across_calls(conn_with_embeddings):
    ids1, mat1 = store.load_all_embeddings(conn_with_embeddings)
    ids2, mat2 = store.load_all_embeddings(conn_with_embeddings)
    assert ids1 == ids2
    # Cache hit returns the same list/array object identities.
    assert ids1 is ids2
    assert mat1 is mat2


def test_upsert_embeddings_invalidates_cache(conn_with_embeddings):
    ids1, _mat1 = store.load_all_embeddings(conn_with_embeddings)
    assert len(ids1) == 2
    # Add a new chunk row + embedding; cache must be dropped.
    tid = conn_with_embeddings.execute("SELECT id FROM translations LIMIT 1").fetchone()[0]
    conn_with_embeddings.execute(
        "INSERT INTO chunks(chunk_id, edition_id, translation_id, lang, "
        "source_file, text, ord) VALUES(?,?,?,?,?,?,?)",
        ("c3", None, tid, "eng", "x", "text", 2),
    )
    conn_with_embeddings.commit()
    store.upsert_embeddings(
        conn_with_embeddings,
        model="test",
        dim=3,
        items=[("c3", np.array([0.0, 0.0, 1.0], dtype=np.float32))],
    )
    ids2, _mat2 = store.load_all_embeddings(conn_with_embeddings)
    assert len(ids2) == 3
    assert ids1 is not ids2  # cache was rebuilt


def test_explicit_invalidate(conn_with_embeddings):
    ids1, _ = store.load_all_embeddings(conn_with_embeddings)
    store.invalidate_embedding_cache(conn_with_embeddings)
    ids2, _ = store.load_all_embeddings(conn_with_embeddings)
    # Same content but rebuilt arrays.
    assert ids1 == ids2
    assert ids1 is not ids2


def test_invalidate_with_no_arg_clears_everything(conn_with_embeddings):
    store.load_all_embeddings(conn_with_embeddings)
    store.invalidate_embedding_cache()
    ids2, _ = store.load_all_embeddings(conn_with_embeddings)
    assert len(ids2) == 2  # rebuilt


# ---------- generation counter (audit item: id-reuse / same-count re-embed) ----------


def test_external_same_count_reembed_invalidates_via_generation(tmp_path: Path):
    """A second connection re-embedding the same chunk (same row count,
    new vectors) bumps `embeddings.generation`; the first connection's
    cached matrix must be rebuilt, not served stale."""

    path = tmp_path / "g.sqlite"
    conn_a = store.open_db(path)
    tid = _seed_translation(conn_a)
    conn_a.execute(
        "INSERT INTO chunks(chunk_id, edition_id, translation_id, lang, "
        "source_file, text, ord) VALUES(?,?,?,?,?,?,?)",
        ("c1", None, tid, "eng", "x", "text", 0),
    )
    conn_a.commit()
    store.upsert_embeddings(
        conn_a, model="test", dim=3, items=[("c1", np.array([1.0, 0.0, 0.0], dtype=np.float32))]
    )
    store.invalidate_embedding_cache()
    _ids, mat = store.load_all_embeddings(conn_a)
    assert np.allclose(mat[0], [1.0, 0.0, 0.0])

    conn_b = store.open_db(path)
    store.upsert_embeddings(
        conn_b, model="test", dim=3, items=[("c1", np.array([0.0, 1.0, 0.0], dtype=np.float32))]
    )
    conn_b.close()

    _ids, mat2 = store.load_all_embeddings(conn_a)  # row count unchanged
    assert np.allclose(mat2[0], [0.0, 1.0, 0.0])


def test_upsert_bumps_generation(conn_with_embeddings):
    from minerva.store.embeddings import embedding_generation

    gen = embedding_generation(conn_with_embeddings)
    assert gen >= 1  # the fixture's upsert bumped it from 0
    store.upsert_embeddings(
        conn_with_embeddings,
        model="test",
        dim=3,
        items=[("c1", np.array([0.5, 0.5, 0.0], dtype=np.float32))],
    )
    assert embedding_generation(conn_with_embeddings) == gen + 1


def test_missing_generation_key_treated_as_zero_with_rowcount_fallback(conn_with_embeddings):
    """Backward compat: a DB without the meta key reads as generation 0
    and the cache still validates on row count."""

    conn = conn_with_embeddings
    conn.execute("DELETE FROM meta WHERE key='embeddings.generation'")
    conn.commit()
    store.invalidate_embedding_cache()
    ids1, _ = store.load_all_embeddings(conn)
    assert len(ids1) == 2
    # A direct write that bypasses the bump still invalidates via the
    # row-count check, exactly as before the generation counter existed.
    tid = conn.execute("SELECT id FROM translations LIMIT 1").fetchone()[0]
    conn.execute(
        "INSERT INTO chunks(chunk_id, edition_id, translation_id, lang, "
        "source_file, text, ord) VALUES(?,?,?,?,?,?,?)",
        ("c9", None, tid, "eng", "x", "text", 9),
    )
    conn.execute(
        "INSERT INTO embeddings(chunk_id, model, dim, vector) VALUES (?,?,?,?)",
        ("c9", "test", 3, np.zeros(3, dtype=np.float32).tobytes()),
    )
    conn.commit()
    ids2, _ = store.load_all_embeddings(conn)
    assert len(ids2) == 3
