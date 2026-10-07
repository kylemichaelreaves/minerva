"""Two chunks of one source that hash to the same ``chunk_id`` (#707).

``chunk_id`` hashes the locator and the first 120 characters of text, so two
paragraphs sharing a section label and an opening collide. The index used to
write with ``INSERT OR REPLACE``, so the later row silently overwrote the
earlier one: five live rows were lost that way (a title-page "OF", a repeated
lacuna marker, ...). Ingest now gives each repeat its own id, and the index
refuses a duplicate rather than resolving it.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from conftest import make_chunk  # type: ignore[import-not-found]

from minerva import store, tei
from minerva.ingest import parallel, registry


def _chunk(chunk_id: str, text: str = "OF") -> tei.Chunk:
    return tei.Chunk(
        chunk_id=chunk_id,
        corpus="hobbes",
        author="Hobbes",
        work="De Cive",
        lang="eng",
        section="English Works, ¶1",
        book=None,
        page=None,
        speaker=None,
        text=text,
        source_file="philosophical_rudiments.txt",
        translator=None,
        edition_year=None,
    )


# ---------- tei.disambiguate_chunk_ids ----------


def test_first_occurrence_keeps_its_id_and_repeats_get_new_ones():
    out = list(tei.disambiguate_chunk_ids([_chunk("a"), _chunk("b"), _chunk("a"), _chunk("a")]))
    ids = [c.chunk_id for c in out]
    assert ids[0] == "a"
    assert ids[1] == "b"
    assert len(set(ids)) == 4


def test_a_chunk_without_a_collision_is_returned_unchanged():
    only = _chunk("a")
    assert next(tei.disambiguate_chunk_ids([only])) is only


def test_repeat_ids_are_deterministic_across_runs():
    # Derived state (embeddings, lemmas, xrefs) is keyed on chunk_id, so a
    # re-ingest of unchanged text must mint the same ids again.
    first_run = [c.chunk_id for c in tei.disambiguate_chunk_ids([_chunk("a")] * 3)]
    second_run = [c.chunk_id for c in tei.disambiguate_chunk_ids([_chunk("a")] * 3)]
    assert first_run == second_run


def test_repeat_ids_keep_every_other_field():
    first, second = tei.disambiguate_chunk_ids([_chunk("a", "X"), _chunk("a", "X")])
    assert dataclasses.replace(second, chunk_id=first.chunk_id) == first


# ---------- every ingest path applies it ----------


def _colliding_source(monkeypatch: pytest.MonkeyPatch, module) -> registry.IngestSource:
    def parse(_path: Path) -> Iterator[tei.Chunk]:
        yield _chunk("dup")
        yield _chunk("dup")

    source = registry.IngestSource(id="collide", default_path=Path(), parse=parse)
    monkeypatch.setattr(module, "INGEST_SOURCES", (source,))
    return source


def test_serial_ingest_yields_unique_ids(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = _colliding_source(monkeypatch, registry)
    monkeypatch.setattr(registry, "missing_registered_sources", lambda *_a, **_k: [])
    chunks = list(registry.iter_registered_chunks({source.kwarg_name: tmp_path}))
    assert len({c.chunk_id for c in chunks}) == 2


def test_parallel_ingest_worker_writes_unique_ids(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _colliding_source(monkeypatch, parallel)
    shard = tmp_path / "shard.jsonl"
    result = parallel._worker_parse_source("collide", str(tmp_path), str(shard))
    assert result["error"] is None
    ids = [json.loads(line)["chunk_id"] for line in shard.read_text().splitlines()]
    assert len(ids) == 2
    assert len(set(ids)) == 2


# ---------- the index refuses what slips through ----------


def test_insert_chunks_refuses_a_duplicate_chunk_id(tmp_path: Path):
    jsonl = tmp_path / "chunks.jsonl"
    rows = [make_chunk(chunk_id="dup", section="¶1"), make_chunk(chunk_id="dup", section="¶2")]
    jsonl.write_text("\n".join(json.dumps(r) for r in rows))
    conn = store.open_db(tmp_path / "t.sqlite")
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_chunks(conn, jsonl)
    conn.close()
