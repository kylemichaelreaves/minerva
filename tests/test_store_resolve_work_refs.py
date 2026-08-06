"""Lock the edition-vs-translation classification in ``_resolve_work_refs``.

Must stay aligned with ``migrations/0003_chunks_backfill.py`` — drift
corrupts the on-disk shape on re-ingest.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import make_chunk

from minerva import store
from minerva.store.chunks import _resolve_work_refs


def test_resolve_work_refs_classifies_greek_as_edition(tmp_path: Path):
    conn = store.open_db(tmp_path / "refs.sqlite")
    edition_id, translation_id = _resolve_work_refs(
        conn,
        corpus="plato",
        author="Plato",
        work="Republic",
        lang="grc",
        translator="Platonis Opera, ed. Burnet",
        edition_year="1903",
    )
    assert edition_id is not None
    assert translation_id is None


def test_resolve_work_refs_classifies_english_as_translation(tmp_path: Path):
    conn = store.open_db(tmp_path / "refs.sqlite")
    edition_id, translation_id = _resolve_work_refs(
        conn,
        corpus="plato",
        author="Plato",
        work="Republic",
        lang="eng",
        translator="Shorey",
        edition_year="1969",
    )
    assert edition_id is None
    assert translation_id is not None


def test_resolve_work_refs_original_marker_is_edition(tmp_path: Path):
    conn = store.open_db(tmp_path / "refs.sqlite")
    edition_id, translation_id = _resolve_work_refs(
        conn,
        corpus="hegel",
        author="Hegel",
        work="Phänomenologie des Geistes",
        lang="deu",
        translator="(Original)",
        edition_year="1907",
    )
    assert edition_id is not None
    assert translation_id is None
    name = conn.execute("SELECT name FROM editions WHERE id = ?", (edition_id,)).fetchone()[0]
    assert name == "Phänomenologie des Geistes"


def test_resolve_work_refs_reuses_existing_rows(tmp_path: Path):
    db = tmp_path / "reuse.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(
        json.dumps(
            make_chunk(
                chunk_id="p1",
                corpus="plato",
                lang="grc",
                translator="Burnet",
                edition_year="1903",
            )
        )
        + "\n"
    )
    conn = store.open_db(db)
    store.insert_chunks(conn, jsonl)
    first_ed = conn.execute("SELECT edition_id FROM chunks WHERE chunk_id = 'p1'").fetchone()[0]

    edition_id, translation_id = _resolve_work_refs(
        conn,
        corpus="plato",
        author="Plato",
        work="Republic",
        lang="grc",
        translator="Burnet",
        edition_year="1903",
    )
    assert edition_id == first_ed
    assert translation_id is None
