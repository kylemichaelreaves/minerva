"""Tests for the term-glossary helpers in `minerva.terms`."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from minerva import store, terms


def _seed(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        INSERT INTO works(id, author, title, original_language, citation_system)
        VALUES (1, 'Plato', 'Republic', 'grc', 'stephanus');

        INSERT INTO editions(id, work_id, name, language, year, notes)
        VALUES (1, 1, 'Burnet OCT', 'grc', 1903, NULL);

        INSERT INTO chunks(chunk_id, edition_id, translation_id, lang,
                           source_file, text, ord)
        VALUES ('chk-1', 1, NULL, 'grc', 'r.xml', 'λόγος λόγος λόγος', 0);

        INSERT INTO terms(id, source_form, source_language,
                          short_gloss, long_description)
        VALUES (1, 'λόγος', 'grc',
                'reason, account, ratio, word',
                'A central Platonic term.');
        """
    )
    conn.commit()


@pytest.fixture
def fresh_db(tmp_path: Path) -> sqlite3.Connection:
    conn = store.open_db(tmp_path / "terms.sqlite")
    _seed(conn)
    return conn


def _insert(conn: sqlite3.Connection, **overrides) -> int:
    """Driver for `insert_occurrence` with sensible defaults."""
    args = {
        "term_id": 1,
        "edition_id": 1,
        "source_chunk_id": "chk-1",
        "source_start": 0,
        "source_end": 6,
        "context_snippet": "…λόγος…",
        "location_kind": "stephanus",
        "location_payload": {"kind": "stephanus", "page": 327, "section": "a"},
        "location_sort_key": "P0327a",
        "source_form_snapshot": "λόγος",
    }
    args.update(overrides)
    return terms.insert_occurrence(conn, **args)


def test_next_instance_index_starts_at_one_on_empty_table(fresh_db):
    """No prior occurrences at this shadow prefix → start at 1.
    This is the contract that the relink path relies on."""
    idx = terms.next_instance_index(
        fresh_db,
        edition_id=1,
        location_sort_key="P0327a",
        source_form_snapshot="λόγος",
    )
    assert idx == 1


def test_insert_occurrence_assigns_ascending_instance_indices(fresh_db):
    """Three inserts at the same shadow prefix get 1, 2, 3 — that's
    how the four-tuple shadow address stays unique."""
    _insert(fresh_db, source_start=0, source_end=6)
    _insert(fresh_db, source_start=7, source_end=13)
    _insert(fresh_db, source_start=14, source_end=20)
    rows = fresh_db.execute(
        "SELECT instance_index FROM term_occurrences "
        "WHERE edition_id=1 AND location_sort_key='P0327a' "
        "  AND source_form_snapshot='λόγος' "
        "ORDER BY instance_index"
    ).fetchall()
    assert [r[0] for r in rows] == [1, 2, 3]


def test_insert_occurrence_separate_shadow_prefixes_each_start_at_one(fresh_db):
    """Different (location, source_form, edition) → independent counters.
    Otherwise we'd over-index trivially."""
    _insert(fresh_db, location_sort_key="P0327a", source_form_snapshot="λόγος")
    _insert(fresh_db, location_sort_key="P0327b", source_form_snapshot="λόγος")
    _insert(fresh_db, location_sort_key="P0327a", source_form_snapshot="δίκη")
    rows = fresh_db.execute(
        "SELECT location_sort_key, source_form_snapshot, instance_index "
        "FROM term_occurrences ORDER BY id"
    ).fetchall()
    assert [r[2] for r in rows] == [1, 1, 1]


def test_insert_occurrence_serializes_payload_as_json(fresh_db):
    _insert(fresh_db)
    raw = fresh_db.execute("SELECT location_payload FROM term_occurrences").fetchone()[0]
    # Stored as JSON-as-TEXT; round-trips through json.loads.
    decoded = json.loads(raw)
    assert decoded["kind"] == "stephanus"
    assert decoded["page"] == 327
    assert decoded["section"] == "a"


def test_insert_occurrence_recovers_after_unique_collision(fresh_db):
    """Simulate a parallel-curator race: pre-insert an occurrence at
    instance_index=1 by hand, then call the helper. The helper's
    SELECT-MAX read sees that row, computes 2, and inserts cleanly."""
    fresh_db.execute(
        "INSERT INTO term_occurrences ("
        "  term_id, edition_id, work_id, source_chunk_id, source_start, source_end, "
        "  context_snippet, location_kind, location_payload, "
        "  location_sort_key, source_form_snapshot, instance_index"
        ") VALUES (1, 1, 1, 'chk-1', 0, 6, '…', "
        "  'stephanus', "
        '  \'{"kind":"stephanus","page":327,"section":"a"}\', '
        "  'P0327a', 'λόγος', 1)"
    )
    fresh_db.commit()
    new_id = _insert(fresh_db, source_start=7, source_end=13)
    idx = fresh_db.execute(
        "SELECT instance_index FROM term_occurrences WHERE id=?",
        (new_id,),
    ).fetchone()[0]
    assert idx == 2


def test_insert_occurrence_raises_on_non_shadow_integrity_error(fresh_db):
    """A CHECK or FK violation isn't the shadow race — must bubble
    immediately rather than being silently retried."""
    with pytest.raises(sqlite3.IntegrityError):
        _insert(fresh_db, source_start=10, source_end=5)  # violates CHECK source_end>source_start


def test_fk_cascade_on_chunk_delete_clears_occurrences(fresh_db):
    """Sanity-check that PRAGMA foreign_keys=ON actually fires the
    declared cascade. Without it, the entire shadow-address mechanism
    would silently orphan rows."""
    _insert(fresh_db)
    fresh_db.execute("DELETE FROM chunks WHERE chunk_id='chk-1'")
    fresh_db.commit()
    remaining = fresh_db.execute("SELECT COUNT(*) FROM term_occurrences").fetchone()[0]
    assert remaining == 0


# ════════════════════════════════════════════════════════════════════
# insert_occurrence_rendering — translation-side shadow address
# ════════════════════════════════════════════════════════════════════


def _seed_rendering_target(fresh_db: sqlite3.Connection) -> int:
    """Set up a translation + translation chunk for the rendering
    inserter to write against. Returns the occurrence_id that the
    test should hang the rendering on."""
    fresh_db.executescript(
        "INSERT INTO translations (id, work_id, translator_name, year, language) "
        "VALUES (10, 1, 'Shorey', 1969, 'eng');"
        "INSERT INTO chunks (chunk_id, translation_id, lang, section, source_file, "
        "                    text, ord) "
        "VALUES ('chk-shorey', 10, 'eng', '514a', 'r-en.xml', "
        "        'account of justice; the account again', 0);"
    )
    fresh_db.commit()
    return _insert(fresh_db)


def test_insert_occurrence_rendering_snapshots_locator_and_form(fresh_db):
    """Both shadow columns must be populated from the parent
    occurrence's location_sort_key and the rendered text exactly,
    independent of whatever the caller passes for `notes` or any
    later edit to `rendered_text`."""
    occ_id = _seed_rendering_target(fresh_db)
    rid = terms.insert_occurrence_rendering(
        fresh_db,
        occurrence_id=occ_id,
        translation_id=10,
        translation_chunk_id="chk-shorey",
        translation_start=0,
        translation_end=7,
        rendered_text="account",
    )
    fresh_db.row_factory = sqlite3.Row
    row = fresh_db.execute(
        "SELECT source_locator_sort_key, rendered_form_snapshot, instance_index "
        "FROM occurrence_renderings WHERE id = ?",
        (rid,),
    ).fetchone()
    # Fixture stores location_sort_key='P0327a' (pre-formatter test
    # value) — the shadow column mirrors that exactly.
    assert row["source_locator_sort_key"] == "P0327a"
    assert row["rendered_form_snapshot"] == "account"
    assert row["instance_index"] == 1


def test_insert_occurrence_rendering_duplicates_per_pair_raise(fresh_db):
    """The (occurrence_id, translation_id) UNIQUE constraint catches a
    duplicate insert — the helper surfaces a TermsError rather than
    raw IntegrityError so callers can branch on it cleanly."""
    occ_id = _seed_rendering_target(fresh_db)
    terms.insert_occurrence_rendering(
        fresh_db,
        occurrence_id=occ_id,
        translation_id=10,
        translation_chunk_id="chk-shorey",
        translation_start=0,
        translation_end=7,
        rendered_text="account",
    )
    with pytest.raises(terms.TermsError):
        terms.insert_occurrence_rendering(
            fresh_db,
            occurrence_id=occ_id,
            translation_id=10,
            translation_chunk_id="chk-shorey",
            translation_start=15,
            translation_end=22,
            rendered_text="account",
        )


def test_insert_occurrence_rendering_unknown_occurrence_raises(fresh_db):
    with pytest.raises(terms.TermsError):
        terms.insert_occurrence_rendering(
            fresh_db,
            occurrence_id=9999,
            translation_id=10,
            translation_chunk_id="chk-shorey",
            translation_start=0,
            translation_end=7,
            rendered_text="account",
        )
