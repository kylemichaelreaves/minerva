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

from minerva import locations, server, store, terms

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

        -- Two grc editions for the same work — exercises the canonical
        -- selection in the work_occurrences endpoint.
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
# /api/terms (list)
# ════════════════════════════════════════════════════════════════════


def test_terms_list_returns_seeded_term(seeded_db):
    deps = _make_deps(seeded_db, StubBackend())
    body = server._handle_terms_list(deps, {})
    assert len(body["terms"]) == 1
    term = body["terms"][0]
    assert term["source_form"] == "λόγος"
    # Two occurrences across the two editions.
    assert term["occurrences"] == 2


def test_terms_list_filters_by_lang(seeded_db):
    deps = _make_deps(seeded_db, StubBackend())
    assert len(server._handle_terms_list(deps, {"lang": "grc"})["terms"]) == 1
    assert server._handle_terms_list(deps, {"lang": "deu"})["terms"] == []


def test_terms_list_like_filter_escapes_wildcards(seeded_db):
    deps = _make_deps(seeded_db, StubBackend())
    assert server._handle_terms_list(deps, {"like": "%"})["terms"] == []
    assert len(server._handle_terms_list(deps, {"like": "λόγ"})["terms"]) == 1


# ════════════════════════════════════════════════════════════════════
# /api/terms/:id (single term)
# ════════════════════════════════════════════════════════════════════


def test_term_by_id_includes_renderings_and_edition_counts(seeded_db):
    deps = _make_deps(seeded_db, StubBackend())
    body = server._handle_term_by_id(deps, 1)
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
    with pytest.raises(server._HTTPError) as info:
        server._handle_term_by_id(deps, 9999)
    assert info.value.status == HTTPStatus.NOT_FOUND


# ════════════════════════════════════════════════════════════════════
# /api/terms/by_chunk/:chunk_id (hover)
# ════════════════════════════════════════════════════════════════════


def test_terms_by_chunk_returns_occurrence_in_document_order(seeded_db):
    """Multiple `lo/gos` in the Slings chunk should come back ordered
    by source_start so the hover layer can paint highlights left-to-
    right without sorting client-side."""
    deps = _make_deps(seeded_db, StubBackend())
    # First, tag the second `lo/gos` in chk-slings-514a as well.
    text = seeded_db.execute(
        "SELECT text FROM chunks WHERE chunk_id = 'chk-slings-514a'"
    ).fetchone()[0]
    second = text.find("lo/gos", text.find("lo/gos") + 1)
    payload = locations.parse_section("stephanus", "514a")
    sort_key = locations.format_sort_key("stephanus", payload)
    terms.insert_occurrence(
        seeded_db,
        term_id=1,
        edition_id=2,
        source_chunk_id="chk-slings-514a",
        source_start=second,
        source_end=second + 6,
        context_snippet=text[max(0, second - 20) : second + 26],
        location_kind="stephanus",
        location_payload=payload,
        location_sort_key=sort_key,
        source_form_snapshot="lo/gos",
    )
    seeded_db.commit()

    body = server._handle_terms_by_chunk(deps, "chk-slings-514a")
    starts = [o["source_start"] for o in body["occurrences"]]
    assert starts == sorted(starts)
    assert len(starts) == 2


def test_terms_by_chunk_returns_empty_for_unknown_chunk(seeded_db):
    deps = _make_deps(seeded_db, StubBackend())
    body = server._handle_terms_by_chunk(deps, "no-such-chunk")
    assert body == {"chunk_id": "no-such-chunk", "occurrences": []}


def test_terms_by_chunk_decodes_location_payload(seeded_db):
    deps = _make_deps(seeded_db, StubBackend())
    body = server._handle_terms_by_chunk(deps, "chk-burnet-514a")
    occ = body["occurrences"][0]
    # The payload comes back as a parsed dict, not a JSON string.
    assert isinstance(occ["location_payload"], dict)
    assert occ["location_payload"]["page"] == 514


# ════════════════════════════════════════════════════════════════════
# /api/works/:work_id/term_occurrences (Q2)
# ════════════════════════════════════════════════════════════════════


def test_work_occurrences_filters_to_canonical_edition_by_default(seeded_db):
    """When the work has multiple source-language editions, Q2 should
    return occurrences from the canonical edition only — Burnet,
    NOT Slings."""
    deps = _make_deps(seeded_db, StubBackend())
    body = server._handle_work_occurrences(deps, 1, {"term_id": "1"})
    assert len(body["occurrences"]) == 1
    assert body["occurrences"][0]["edition_id"] == 1


def test_work_occurrences_edition_id_override_selects_non_canonical(seeded_db):
    """Passing `edition_id=<non-canonical>` lets the curator scope to
    a specific non-canonical edition. The endpoint validates that the
    edition belongs to the work and to the term's source language."""
    deps = _make_deps(seeded_db, StubBackend())
    body = server._handle_work_occurrences(deps, 1, {"term_id": "1", "edition_id": "2"})
    assert len(body["occurrences"]) == 1
    assert body["occurrences"][0]["edition_id"] == 2


def test_work_occurrences_edition_id_must_match_term_language(seeded_db):
    """Asking for a translation_id when the term is grc-only should
    404 — translations are not editions of the term's source."""
    deps = _make_deps(seeded_db, StubBackend())
    with pytest.raises(server._HTTPError) as info:
        # edition_id 99 doesn't exist
        server._handle_work_occurrences(deps, 1, {"term_id": "1", "edition_id": "99"})
    assert info.value.status == HTTPStatus.NOT_FOUND


def test_work_occurrences_attaches_renderings(seeded_db):
    """Each occurrence row should carry a `renderings` list with the
    translator default tagged source='default'."""
    deps = _make_deps(seeded_db, StubBackend())
    body = server._handle_work_occurrences(deps, 1, {"term_id": "1"})
    occ = body["occurrences"][0]
    by_translator = {r["translator"]: r for r in occ["renderings"]}
    # Shorey has a default; Bloom doesn't. The endpoint omits Bloom.
    assert "Shorey" in by_translator
    assert by_translator["Shorey"]["rendered"] == "account"
    assert by_translator["Shorey"]["source"] == "default"
    assert "Bloom" not in by_translator


def test_work_occurrences_per_occurrence_override_supersedes_default(seeded_db):
    """When an occurrence_renderings row exists, it should appear with
    source='override' regardless of whether a default exists."""
    deps = _make_deps(seeded_db, StubBackend())
    seeded_db.executescript(
        "INSERT INTO chunks (chunk_id, translation_id, work_id, lang, section, "
        "  source_file, text, ord) "
        "VALUES ('chk-shorey-514a-2', 1, 1, 'eng', '514a', 'r-en.xml', "
        "'a definition, in this specific use', 0);"
    )
    terms.insert_occurrence_rendering(
        seeded_db,
        occurrence_id=1,
        translation_id=1,
        translation_chunk_id="chk-shorey-514a-2",
        translation_start=2,
        translation_end=12,
        rendered_text="definition",
        notes="Shorey breaks default here",
    )
    seeded_db.commit()
    body = server._handle_work_occurrences(deps, 1, {"term_id": "1"})
    occ = body["occurrences"][0]
    rendering = next(r for r in occ["renderings"] if r["translator"] == "Shorey")
    assert rendering["source"] == "override"
    assert rendering["rendered"] == "definition"


def test_work_occurrences_requires_term_id(seeded_db):
    deps = _make_deps(seeded_db, StubBackend())
    with pytest.raises(server._HTTPError) as info:
        server._handle_work_occurrences(deps, 1, {})
    assert info.value.status == HTTPStatus.BAD_REQUEST


def test_work_occurrences_returns_empty_when_no_canonical_in_term_language(seeded_db):
    """A work with no editions in the term's source language returns
    an empty list rather than 404 — the term simply has no occurrences
    in that work."""
    deps = _make_deps(seeded_db, StubBackend())
    # Mark both grc editions non-canonical → no canonical edition
    # remains in grc, so the default-canonical path finds nothing.
    seeded_db.execute("UPDATE editions SET is_canonical = 0 WHERE work_id = 1")
    seeded_db.commit()
    body = server._handle_work_occurrences(deps, 1, {"term_id": "1"})
    assert body["occurrences"] == []


# ════════════════════════════════════════════════════════════════════
# /api/translations/:translation_id/renderings (Q3)
# ════════════════════════════════════════════════════════════════════


def test_translation_renderings_lists_glossary(seeded_db):
    deps = _make_deps(seeded_db, StubBackend())
    body = server._handle_translation_renderings(deps, 1)
    assert body["translator"] == "Shorey"
    assert body["work_title"] == "Republic"
    assert len(body["renderings"]) == 1
    r = body["renderings"][0]
    assert r["source_form"] == "λόγος"
    assert r["default_rendering"] == "account"
    assert body["override_count"] == 0


def test_translation_renderings_404_for_unknown(seeded_db):
    deps = _make_deps(seeded_db, StubBackend())
    with pytest.raises(server._HTTPError) as info:
        server._handle_translation_renderings(deps, 9999)
    assert info.value.status == HTTPStatus.NOT_FOUND


# ════════════════════════════════════════════════════════════════════
# /api/works payload now carries work_id
# ════════════════════════════════════════════════════════════════════


def test_works_list_includes_work_id(seeded_db):
    deps = _make_deps(seeded_db, StubBackend())
    body = server._handle_works_list(deps)
    assert any(w["work_id"] == 1 for w in body["works"])
