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
    _work_id, edition_id, translation_id = _resolve_work_refs(
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
    _work_id, edition_id, translation_id = _resolve_work_refs(
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
    _work_id, edition_id, translation_id = _resolve_work_refs(
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
    name = conn.execute(
        "SELECT name FROM editions WHERE id = ?", (edition_id,)
    ).fetchone()[0]
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
    first_ed = conn.execute(
        "SELECT edition_id FROM chunks WHERE chunk_id = 'p1'"
    ).fetchone()[0]

    _work_id, edition_id, translation_id = _resolve_work_refs(
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


def test_a_re_source_replaces_the_canonical_edition_rather_than_colliding(tmp_path: Path):
    """Re-sourcing a work points the same `work`/`lang` pair at a different
    edition, so the incoming name and year differ. The lookup matches on
    all four of `(work_id, name, language, year)` and missed, then the
    insert collided with `editions_canonical_unique`, which covers only
    `(work_id, language)` — aborting the whole re-ingest (#410). Measured
    when Babrius's Greek moved from Crusius 1897 to Schneidewin (#398)."""

    conn = store.open_db(tmp_path / "refs.sqlite")
    work_id, first, _ = _resolve_work_refs(
        conn,
        corpus="aesop",
        author="Aesop",
        work="Fables (Babrius)",
        lang="grc",
        translator="(Babrius, Greek verse)",
        edition_year="2nd c. CE (Crusius ed., 1897)",
    )
    work_id_2, second, _ = _resolve_work_refs(
        conn,
        corpus="aesop",
        author="Aesop",
        work="Fables (Babrius)",
        lang="grc",
        translator="Friedrich Schneidewin",
        edition_year="1865",
    )
    assert work_id_2 == work_id
    assert second == first  # the row is updated, not duplicated
    name, year = conn.execute(
        "SELECT name, year FROM editions WHERE id = ?", (first,)
    ).fetchone()
    assert (name, year) == ("Friedrich Schneidewin", 1865)
    assert conn.execute(
        "SELECT COUNT(*) FROM editions WHERE work_id = ? AND language = 'grc'", (work_id,)
    ).fetchone()[0] == 1


def test_an_unchanged_edition_is_reused_without_a_write(tmp_path: Path):
    """The ordinary re-ingest path. Same name and year must still take the
    exact-match branch, or every ingest would rewrite every edition row."""

    conn = store.open_db(tmp_path / "refs.sqlite")
    kw = {
        "corpus": "plato",
        "author": "Plato",
        "work": "Republic",
        "lang": "grc",
        "translator": "Platonis Opera, ed. Burnet",
        "edition_year": "1903",
    }
    _w1, first, _ = _resolve_work_refs(conn, **kw)
    _w2, second, _ = _resolve_work_refs(conn, **kw)
    assert second == first
    assert conn.execute("SELECT COUNT(*) FROM editions").fetchone()[0] == 1
