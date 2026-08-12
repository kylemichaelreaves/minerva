"""Regression tests for `minerva.glossary_import` internals — the
IN-list batching in `_chunk_rows` (works >999 chunks, e.g. Psalms)
and the dry-run term-id sentinel."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from minerva import store
from minerva.glossary_import import _chunk_rows, _ensure_term
from minerva.glossary_spec import Term


@pytest.fixture
def big_work_db(tmp_path: Path) -> tuple[sqlite3.Connection, list[str]]:
    """A work with 1,050 chunks — past SQLite's historical 999
    bound-variable cap that the unbatched IN-list used to blow."""

    conn = store.open_db(tmp_path / "g.sqlite")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT INTO works(id, author, title, original_language, citation_system) "
        "VALUES (1, 'Anon', 'Psalmi', 'lat', 'paragraph')"
    )
    cur = conn.execute(
        "INSERT INTO editions(work_id, name, language, year) VALUES (1, 'Vulgata', 'lat', 1592)"
    )
    eid = int(cur.lastrowid)
    n = 1050
    conn.executemany(
        # `work_id` mirrors the edition's, as `insert_chunks` writes it —
        # `chunks_full` inner-joins `works` on it since migration 0030 (#339).
        "INSERT INTO chunks(chunk_id, edition_id, translation_id, work_id, lang, section, "
        "source_file, text, ord) VALUES (?,?,?,?,?,?,?,?,?)",
        [(f"ps-{i:04d}", eid, None, 1, "lat", f"§{i}", "x", f"text {i}", i) for i in range(n)],
    )
    conn.commit()
    return conn, [f"ps-{i:04d}" for i in range(n)]


def test_chunk_rows_batches_past_sqlite_variable_cap(big_work_db) -> None:
    conn, ids = big_work_db
    # Pin the per-statement bound-variable cap to the historical 999 so
    # the regression reproduces even on modern SQLite builds (~32k cap).
    conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)
    out = _chunk_rows(conn, ids)
    assert len(out) == len(ids)
    # ord ordering must hold across batch boundaries.
    assert [r[0] for r in out] == ids
    assert out[0][1] == "§0" and out[-1][1] == "§1049"


def test_chunk_rows_empty_input(big_work_db) -> None:
    conn, _ids = big_work_db
    assert _chunk_rows(conn, []) == []


def test_dry_run_term_sentinels_negative_unique_and_non_writing(tmp_path: Path) -> None:
    """The dry-run sentinel must never collide with a real (positive)
    PK — the old `-abs(hash(...)) | 1` could yield -1 == a plausible id
    space collision at hash()==0 and varied under hash randomization."""

    conn = store.open_db(tmp_path / "t.sqlite")
    conn.row_factory = sqlite3.Row
    seen: set[int] = set()
    for form in ("λόγος", "ψυχή", "ἀρετή"):
        term = Term(lemma=form, source_form=form, short_gloss="g", long_description="d")
        tid = _ensure_term(conn, "grc", term, dry_run=True)
        assert tid < 0
        seen.add(tid)
    assert len(seen) == 3
    assert conn.execute("SELECT COUNT(*) FROM terms").fetchone()[0] == 0


def test_dry_run_returns_real_id_for_existing_term(tmp_path: Path) -> None:
    conn = store.open_db(tmp_path / "t.sqlite")
    conn.row_factory = sqlite3.Row
    term = Term(lemma="λόγος", source_form="λόγος", short_gloss="g", long_description="d")
    real_id = _ensure_term(conn, "grc", term, dry_run=False)
    assert real_id > 0
    assert _ensure_term(conn, "grc", term, dry_run=True) == real_id
