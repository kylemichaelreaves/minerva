"""The embedding model is pinned by revision, and the revision is part of the
key stored rows are compared against (#500).

Hugging Face resolves an unpinned name to whatever `main` is today, so an
upstream push silently moved new encodes into a different vector space from
the stored ones. The incremental embed already re-encodes any row whose
`embeddings.model` differs from the model in use (#285); carrying the
revision in that string is what makes an upstream change a re-encode instead
of a silent mix of spaces.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest
from conftest import make_chunk

from minerva import embed, store

_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_SHA = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"


class _FakeST:
    calls: ClassVar[list[tuple[str, dict]]] = []

    def __init__(self, name: str, **kwargs) -> None:
        _FakeST.calls.append((name, kwargs))

    def get_sentence_embedding_dimension(self) -> int:
        return 4


@pytest.fixture
def fake_st(monkeypatch):
    _FakeST.calls = []
    mod = types.ModuleType("sentence_transformers")
    mod.SentenceTransformer = _FakeST
    monkeypatch.setitem(sys.modules, "sentence_transformers", mod)
    return _FakeST


def test_default_model_is_pinned_to_a_commit():
    assert f"{_NAME}@{_SHA}" == embed.DEFAULT_MODEL


def test_embedder_loads_the_pinned_revision(fake_st):
    e = embed.Embedder()
    assert fake_st.calls == [(_NAME, {"revision": _SHA})]
    # The stored key carries the revision, so a different pin re-encodes.
    assert e.model_name == f"{_NAME}@{_SHA}"


def test_an_unpinned_spec_loads_without_a_revision(fake_st):
    embed.Embedder("some/model")
    assert fake_st.calls == [("some/model", {"revision": None})]


def _db_with_unpinned_rows(tmp_path: Path) -> Path:
    path = tmp_path / "pre.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(
        "\n".join(
            json.dumps(make_chunk(chunk_id=cid, lang="eng", text=f"text {cid}"))
            for cid in ("a", "b", "c")
        )
    )
    conn = store.open_db(path)
    store.insert_chunks(conn, jsonl)
    vec = np.ones((4,), dtype=np.float32)
    store.upsert_embeddings(conn, model=_NAME, dim=4, items=[("a", vec), ("b", vec)])
    store.upsert_embeddings(conn, model="other/model", dim=4, items=[("c", vec)])
    version = int(_MIGRATION.split("_")[0])
    conn.execute("DELETE FROM schema_migrations WHERE version = ?", (version,))
    conn.commit()
    conn.close()
    return path


_MIGRATION = "0040_embeddings_model_revision"


def test_migration_relabels_unpinned_rows_with_the_cached_revision(tmp_path: Path):
    path = _db_with_unpinned_rows(tmp_path)
    conn = store.open_db(path)  # replays the migration
    try:
        rows = dict(conn.execute("SELECT chunk_id, model FROM embeddings").fetchall())
        meta = conn.execute("SELECT value FROM meta WHERE key = 'embeddings.model'").fetchone()[0]
        changed = conn.execute(
            "SELECT rows_changed FROM schema_migrations WHERE version = 40"
        ).fetchone()[0]
    finally:
        conn.close()
    assert rows == {"a": f"{_NAME}@{_SHA}", "b": f"{_NAME}@{_SHA}", "c": "other/model"}
    assert meta == "other/model"  # the last write's model; not this model's row
    assert changed == 2


def test_relabelled_rows_are_current_for_the_incremental_embed(tmp_path: Path):
    path = _db_with_unpinned_rows(tmp_path)
    conn = store.open_db(path)
    try:
        missing = store.count_chunks_without_embeddings(conn, model=embed.DEFAULT_MODEL, lang=None)
    finally:
        conn.close()
    assert missing == 1  # only "c", embedded under a different model


def test_migration_is_a_noop_without_unpinned_rows(tmp_path: Path):
    conn = store.open_db(tmp_path / "fresh.sqlite")
    try:
        changed = conn.execute(
            "SELECT rows_changed FROM schema_migrations WHERE version = 40"
        ).fetchone()[0]
    finally:
        conn.close()
    assert changed is None
