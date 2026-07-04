"""Registry-level missing ingest path detection (audit shortlist #5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from minerva.ingest.registry import (
    INGEST_SOURCES,
    IngestSource,
    MissingIngestSourcesError,
    iter_registered_chunks,
    missing_registered_sources,
)


def test_missing_registered_sources_lists_absent_paths(tmp_path: Path):
    paths = {s.kwarg_name: tmp_path / "absent" for s in INGEST_SOURCES}
    missing = missing_registered_sources(paths)
    assert missing
    assert all(not Path(p).exists() for _, p in missing if p is not None)


def test_iter_registered_chunks_raises_on_missing_paths(capsys):
    paths = {s.kwarg_name: None for s in INGEST_SOURCES}
    with pytest.raises(MissingIngestSourcesError) as exc:
        list(iter_registered_chunks(paths, only=frozenset({"plato"})))
    assert exc.value.missing
    err = capsys.readouterr().err
    assert "SKIPPED plato" in err


def test_iter_registered_chunks_allows_opt_in_missing(monkeypatch, tmp_path: Path):
    def fake_parse(path: Path):
        from minerva import tei

        yield tei.Chunk(
            chunk_id="x",
            corpus="plato",
            author="Plato",
            work="Republic",
            lang="eng",
            section=None,
            book=None,
            page=None,
            speaker=None,
            text="hello",
            source_file="x.xml",
            translator=None,
            edition_year=None,
        )

    fake = IngestSource("plato", tmp_path, fake_parse)
    monkeypatch.setattr(
        "minerva.ingest.registry.INGEST_SOURCES",
        (fake,),
    )
    paths = {fake.kwarg_name: None}
    chunks = list(
        iter_registered_chunks(
            paths,
            only=frozenset({"plato"}),
            allow_missing_sources=True,
        )
    )
    assert len(chunks) == 0
