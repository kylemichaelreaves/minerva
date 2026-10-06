"""Server tests for the term-glossary endpoints introduced in this
follow-on pass. Mirrors the layout of `test_server_reader.py` —
direct calls into the `_handle_*` helpers, no live HTTP loop."""

from __future__ import annotations

import sqlite3
from http import HTTPStatus
from pathlib import Path

import pytest
from conftest import StubBackend
from conftest import make_deps as _make_deps

from minerva import locations, store, terms
from minerva.http.handlers import (
    _handle_term_by_id,
    _handle_works_list,
)
from minerva.http.server_core import _HTTPError

# ════════════════════════════════════════════════════════════════════
# Fixture: a minimal works/editions/translations/terms seed that
# every endpoint can be exercised against.
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def seeded_db(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "terms.sqlite"
    conn = store.open_db(db)
    conn.executescript(
        """
        INSERT INTO works (id, author, title, original_language, citation_system)
        VALUES (1, 'Plato', 'Republic', 'grc', 'stephanus');

        -- Two grc editions for the same work, so the per-edition
        -- occurrence counts on the term card have two rows.
        INSERT INTO editions (id, work_id, name, language, year, is_canonical)
        VALUES (1, 1, 'Burnet OCT', 'grc', 1903, 1),
               (2, 1, 'Slings OCT', 'grc', 2003, 0);

        INSERT INTO translations (id, work_id, translator_name, year, language)
        VALUES (1, 1, 'Shorey',  1969, 'eng'),
               (2, 1, 'Bloom',   1968, 'eng');

        -- One chunk in each grc edition; same locator, different
        -- physical text (the two editions disagree about which word
        -- appears at 514a in this fabricated fixture).
        -- `work_id` is not optional here: `chunks_full` inner-joins `works`
        -- on it since migration 0030, so a row without it is invisible to
        -- every query that goes through the view (#339).
        INSERT INTO chunks (chunk_id, edition_id, work_id, lang, section, source_file, text, ord)
        VALUES ('chk-burnet-514a', 1, 1, 'grc', '514a', 'r.xml',
                'meta\\\\ tau=ta lo/gos peri\\\\ paidei/as', 0),
               ('chk-slings-514a', 2, 1, 'grc', '514a', 'r2.xml',
                'meta\\\\ tau=ta lo/gos kai\\\\ a)/llo lo/gos', 0);

        -- One translation chunk for Shorey's English Republic
        -- (translation_id = 1).
        INSERT INTO chunks (chunk_id, translation_id, work_id, lang, section, source_file, text, ord)
        VALUES ('chk-shorey-514a', 1, 1, 'eng', '514a', 'r-en.xml',
                'After this, then, I said, liken our nature in its training to such an experience.', 0);

        INSERT INTO terms (id, source_form, source_language, transliteration,
                           short_gloss, long_description)
        VALUES (1, 'λόγος', 'grc', 'lo/gos',
                'reason, account, ratio, word',
                'A central Platonic term.');

        -- Shorey's default rendering of λόγος (Republic). Bloom has no
        -- default — used to exercise "no rendering" pathway.
        INSERT INTO term_renderings (term_id, translation_id, default_rendering,
                                     translator_note)
        VALUES (1, 1, 'account', 'Shorey default in dialectical contexts');
        """
    )
    conn.commit()

    # Tag an occurrence in each edition via the helper so the shadow-
    # address contract is exercised end-to-end.
    payload = locations.parse_section("stephanus", "514a")
    sort_key = locations.format_sort_key("stephanus", payload)
    for chunk_id, edition_id in [("chk-burnet-514a", 1), ("chk-slings-514a", 2)]:
        text = conn.execute("SELECT text FROM chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()[0]
        pos = text.find("lo/gos")
        terms.insert_occurrence(
            conn,
            term_id=1,
            edition_id=edition_id,
            source_chunk_id=chunk_id,
            source_start=pos,
            source_end=pos + len("lo/gos"),
            context_snippet=text[max(0, pos - 20) : pos + 26],
            location_kind="stephanus",
            location_payload=payload,
            location_sort_key=sort_key,
            source_form_snapshot="lo/gos",
            tradition="platonic",
        )
    conn.commit()
    return conn


# ════════════════════════════════════════════════════════════════════
# /api/terms/:id (single term)
# ════════════════════════════════════════════════════════════════════


def test_term_by_id_includes_renderings_and_edition_counts(seeded_db):
    deps = _make_deps(seeded_db, StubBackend())
    body = _handle_term_by_id(deps, 1)
    assert body["source_form"] == "λόγος"
    # Shorey's default rendering surfaces with translator metadata.
    assert len(body["renderings"]) == 1
    assert body["renderings"][0]["default_rendering"] == "account"
    assert body["renderings"][0]["translator_name"] == "Shorey"
    # Per-edition occurrence counts list both editions.
    counts = {r["edition_id"]: r["occurrences"] for r in body["occurrences_by_edition"]}
    assert counts == {1: 1, 2: 1}


def test_term_by_id_404_for_unknown(seeded_db):
    deps = _make_deps(seeded_db, StubBackend())
    with pytest.raises(_HTTPError) as info:
        _handle_term_by_id(deps, 9999)
    assert info.value.status == HTTPStatus.NOT_FOUND


# ════════════════════════════════════════════════════════════════════
# /api/works payload now carries work_id
# ════════════════════════════════════════════════════════════════════


def test_works_list_includes_work_id(seeded_db):
    deps = _make_deps(seeded_db, StubBackend())
    body = _handle_works_list(deps)
    assert any(w["work_id"] == 1 for w in body["works"])
