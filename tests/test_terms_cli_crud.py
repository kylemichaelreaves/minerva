"""Coverage for the curator-facing `terms` write and detail commands.

Until #154 the `terms` CLI had no tests at all; that PR added
`test_terms_cli_like.py` covering only the two `--like` read paths it
changed. Everything that *mutates* the curator DB — `add`, `canonical`,
`render`, `relate` — stayed uncovered, along with `show` and the
`work_id`-filtered listings (#159).

That matters more than a coverage number: these commands write the
glossary, and a regression in them is silent until someone notices bad
data in the Reader. The `--like` bug in #154 was in a *read* path and
still went unnoticed for the repo's entire history.

Like `test_terms_cli_like.py`, these drive the argparse handlers
directly against a real SQLite store, so the assertions cover the SQL
each command actually runs — not a mock of it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from minerva import store
from minerva.cli.terms.crud import (
    cmd_terms_add,
    cmd_terms_canonical,
    cmd_terms_list,
    cmd_terms_show,
)
from minerva.cli.terms.linking import (
    cmd_terms_editions,
    cmd_terms_relate,
    cmd_terms_render,
    cmd_terms_translations,
)


@pytest.fixture
def curator_db(tmp_path: Path) -> Path:
    """A store wired end to end: two works, two editions of one of them
    (so the canonical two-step has something to clear), a translation, a
    term with a rendering, and one anchored occurrence.

    The occurrence needs a real `chunks` row — `term_occurrences` has an
    FK to it and `store.open_db` enables `PRAGMA foreign_keys`.
    """

    db_path = tmp_path / "curator.sqlite"
    conn = store.open_db(db_path)

    conn.execute(
        "INSERT INTO works (id, author, title, original_language, citation_system) "
        "VALUES (1, 'Hegel', 'Phänomenologie des Geistes', 'deu', 'paragraph')"
    )
    conn.execute(
        "INSERT INTO works (id, author, title, original_language, citation_system) "
        "VALUES (2, 'Plato', 'Politeia', 'grc', 'stephanus')"
    )
    # Two editions of work 1, the FIRST marked canonical. `is_canonical`
    # defaults to 1, so this is the state `terms canonical` must clear.
    conn.execute(
        "INSERT INTO editions (id, work_id, name, language, year, is_canonical) "
        "VALUES (10, 1, 'Hoffmeister', 'deu', 1952, 1)"
    )
    conn.execute(
        "INSERT INTO editions (id, work_id, name, language, year, is_canonical) "
        "VALUES (11, 1, 'Bonsiepen-Heede', 'deu', 1980, 0)"
    )
    conn.execute(
        "INSERT INTO editions (id, work_id, name, language, year, is_canonical) "
        "VALUES (12, 2, 'Burnet', 'grc', 1903, 1)"
    )
    conn.execute(
        "INSERT INTO translations (id, work_id, translator_name, year, language) "
        "VALUES (20, 1, 'Miller', 1977, 'eng')"
    )
    conn.execute(
        "INSERT INTO terms (id, source_form, source_language, transliteration, "
        "lemma, short_gloss, long_description) "
        "VALUES (1, 'Geist', 'deu', NULL, 'Geist', 'spirit', 'Line one.\nLine two.')"
    )
    # A term with neither transliteration nor lemma, and no renderings or
    # occurrences — drives `show`'s other branch in every optional block.
    conn.execute(
        "INSERT INTO terms (id, source_form, source_language, short_gloss, "
        "long_description) VALUES (2, 'Aufhebung', 'deu', 'sublation', '')"
    )
    conn.execute(
        "INSERT INTO term_renderings (term_id, translation_id, default_rendering) "
        "VALUES (1, 20, 'Spirit')"
    )
    conn.execute(
        "INSERT INTO chunks (chunk_id, edition_id, lang, source_file, text, ord) "
        "VALUES ('c1', 10, 'deu', 'f.txt', 'Der Geist ist ...', 1)"
    )
    conn.execute(
        "INSERT INTO term_occurrences (term_id, edition_id, work_id, source_chunk_id, "
        "  source_start, source_end, context_snippet, location_kind, "
        "  location_payload, location_sort_key, source_form_snapshot, instance_index) "
        "VALUES (1, 10, 1, 'c1', 4, 9, 'Der Geist ist', 'paragraph', '{}', 'p0001', "
        "        'Geist', 1)"
    )
    conn.commit()
    conn.close()
    return db_path


def _ns(db: Path, **kw) -> argparse.Namespace:
    return argparse.Namespace(db=db, **kw)


def _canonical_flags(db: Path) -> dict[int, int]:
    conn = store.open_db(db)
    try:
        return {r["id"]: r["is_canonical"] for r in conn.execute("SELECT id, is_canonical FROM editions")}
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────
#  show
# ──────────────────────────────────────────────────────────────────


def test_show_by_id_prints_renderings_and_occurrences(curator_db, capsys):
    """The populated branches: lemma set, one rendering, one occurrence."""

    assert cmd_terms_show(_ns(curator_db, term_id_or_form="1", lang=None)) == 0
    out = capsys.readouterr().out
    assert "source_form:      Geist" in out
    assert "lemma:            Geist" in out
    # long_description is printed line by line, indented.
    assert "  Line one." in out and "  Line two." in out
    assert "Miller (1977) → eng: Spirit" in out
    assert "Hoffmeister (deu): 1" in out
    assert "(none)" not in out


def test_show_empty_sections_say_none(curator_db, capsys):
    """Term 2 has no transliteration, lemma, renderings or occurrences —
    both `(none)` branches, and the optional field lines are absent."""

    assert cmd_terms_show(_ns(curator_db, term_id_or_form="2", lang=None)) == 0
    out = capsys.readouterr().out
    assert "transliteration:" not in out
    assert "lemma:" not in out
    assert out.count("(none)") == 2


def test_show_by_form_and_by_form_with_lang(curator_db, capsys):
    """The non-digit lookup path, with and without the `--lang` narrowing."""

    assert cmd_terms_show(_ns(curator_db, term_id_or_form="Geist", lang=None)) == 0
    assert "id:               1" in capsys.readouterr().out

    assert cmd_terms_show(_ns(curator_db, term_id_or_form="Geist", lang="deu")) == 0
    assert "id:               1" in capsys.readouterr().out

    # Right form, wrong language — the lang clause must actually filter.
    assert cmd_terms_show(_ns(curator_db, term_id_or_form="Geist", lang="grc")) == 1
    assert "no term matches" in capsys.readouterr().err


def test_show_unknown_term_exits_1(curator_db, capsys):
    assert cmd_terms_show(_ns(curator_db, term_id_or_form="Nichts", lang=None)) == 1
    assert "no term matches 'Nichts'" in capsys.readouterr().err


def test_show_prints_transliteration_when_set(curator_db, capsys):
    """The optional transliteration line — the fixture's two terms both
    leave it NULL, so it needs a term that sets it."""

    conn = store.open_db(curator_db)
    conn.execute(
        "INSERT INTO terms (source_form, source_language, transliteration, "
        "short_gloss, long_description) VALUES ('λόγος', 'grc', 'logos', 'reason', '')"
    )
    conn.commit()
    conn.close()

    assert cmd_terms_show(_ns(curator_db, term_id_or_form="λόγος", lang=None)) == 0
    assert "transliteration:  logos" in capsys.readouterr().out


def test_list_filters_by_lang(curator_db, capsys):
    """`terms list --lang` — the other WHERE branch alongside `--like`,
    which `test_terms_cli_like.py` covers."""

    args = _ns(curator_db, lang="deu", like=None, json=True)
    assert cmd_terms_list(args) == 0
    rows = json.loads(capsys.readouterr().out)
    assert {r["source_form"] for r in rows} == {"Geist", "Aufhebung"}
    assert all(r["lang"] == "deu" for r in rows)

    args = _ns(curator_db, lang="grc", like=None, json=True)
    assert cmd_terms_list(args) == 0
    assert json.loads(capsys.readouterr().out) == []


# ──────────────────────────────────────────────────────────────────
#  add
# ──────────────────────────────────────────────────────────────────


def _add_ns(db: Path, form: str, **kw) -> argparse.Namespace:
    base = {
        "form": form,
        "lang": "deu",
        "transliteration": None,
        "lemma": None,
        "gloss": "g",
        "description": None,
        "description_file": None,
    }
    base.update(kw)
    return _ns(db, **base)


def test_add_creates_term(curator_db, capsys):
    assert cmd_terms_add(_add_ns(curator_db, "Begriff", gloss="concept")) == 0
    assert "created term id=" in capsys.readouterr().out

    conn = store.open_db(curator_db)
    row = conn.execute(
        "SELECT short_gloss, long_description FROM terms WHERE source_form='Begriff'"
    ).fetchone()
    conn.close()
    assert row["short_gloss"] == "concept"
    # No description supplied → stored as '' (the column is NOT NULL).
    assert row["long_description"] == ""


def test_add_reads_description_from_file(curator_db, tmp_path, capsys):
    desc = tmp_path / "d.txt"
    desc.write_text("From a file.", encoding="utf-8")
    assert cmd_terms_add(_add_ns(curator_db, "Wesen", description_file=desc)) == 0
    capsys.readouterr()

    conn = store.open_db(curator_db)
    row = conn.execute(
        "SELECT long_description FROM terms WHERE source_form='Wesen'"
    ).fetchone()
    conn.close()
    assert row["long_description"] == "From a file."


def test_add_duplicate_reports_existing_id_and_exits_1(curator_db, capsys):
    """The (source_form, source_language) UNIQUE collision must name the
    existing row rather than surfacing a raw IntegrityError."""

    assert cmd_terms_add(_add_ns(curator_db, "Geist")) == 1
    err = capsys.readouterr().err
    assert "term already exists: id=1" in err

    conn = store.open_db(curator_db)
    n = conn.execute("SELECT COUNT(*) FROM terms WHERE source_form='Geist'").fetchone()[0]
    conn.close()
    assert n == 1, "the failed insert must not have been committed"


def test_add_reraises_integrity_error_it_cannot_explain(curator_db):
    """The duplicate handler only swallows the error when it can point at
    the colliding row. A different constraint — here the `source_language`
    CHECK — must propagate rather than be reported as a duplicate."""

    with pytest.raises(Exception) as exc:
        cmd_terms_add(_add_ns(curator_db, "Xyz", lang="klingon"))
    assert "CHECK" in str(exc.value) or "constraint" in str(exc.value).lower()


# ──────────────────────────────────────────────────────────────────
#  canonical
# ──────────────────────────────────────────────────────────────────


def test_canonical_set_clears_the_previous_one(curator_db, capsys):
    """Setting canonical is a two-step because of the UNIQUE index from
    migration 0004: clear the old for the (work_id, language) pair, then
    set the new. Edition 12 belongs to another work and must be left
    alone."""

    assert _canonical_flags(curator_db) == {10: 1, 11: 0, 12: 1}

    assert cmd_terms_canonical(_ns(curator_db, edition=11, unset=False)) == 0
    assert "marked canonical" in capsys.readouterr().out

    assert _canonical_flags(curator_db) == {10: 0, 11: 1, 12: 1}


def test_canonical_unset_touches_only_that_edition(curator_db, capsys):
    assert cmd_terms_canonical(_ns(curator_db, edition=10, unset=True)) == 0
    assert "marked non-canonical" in capsys.readouterr().out
    assert _canonical_flags(curator_db) == {10: 0, 11: 0, 12: 1}


def test_canonical_unknown_edition_exits_1(curator_db, capsys):
    assert cmd_terms_canonical(_ns(curator_db, edition=999, unset=False)) == 1
    assert "no edition with id=999" in capsys.readouterr().err
    assert _canonical_flags(curator_db) == {10: 1, 11: 0, 12: 1}


# ──────────────────────────────────────────────────────────────────
#  editions / translations listings
# ──────────────────────────────────────────────────────────────────


def test_editions_filter_by_work_id(curator_db, capsys):
    all_rows = json.loads(
        _run_ok(cmd_terms_editions, _ns(curator_db, work_id=None, json=True), capsys)
    )
    assert len(all_rows) == 3

    work1 = json.loads(
        _run_ok(cmd_terms_editions, _ns(curator_db, work_id=1, json=True), capsys)
    )
    assert {r["name"] for r in work1} == {"Hoffmeister", "Bonsiepen-Heede"}


def test_translations_filter_by_work_id(curator_db, capsys):
    rows = json.loads(
        _run_ok(cmd_terms_translations, _ns(curator_db, work_id=1, json=True), capsys)
    )
    assert [r["translator"] for r in rows] == ["Miller"]

    none = json.loads(
        _run_ok(cmd_terms_translations, _ns(curator_db, work_id=2, json=True), capsys)
    )
    assert none == []

    # Unfiltered — the other side of the `work_id is not None` branch.
    all_rows = json.loads(
        _run_ok(cmd_terms_translations, _ns(curator_db, work_id=None, json=True), capsys)
    )
    assert [r["translator"] for r in all_rows] == ["Miller"]


def _run_ok(fn, args, capsys) -> str:
    assert fn(args) == 0
    return capsys.readouterr().out


# ──────────────────────────────────────────────────────────────────
#  render / relate
# ──────────────────────────────────────────────────────────────────


def _render_ns(db: Path, **kw) -> argparse.Namespace:
    base = {
        "term_id": 2,
        "translation_id": 20,
        "rendering": "Sublation",
        "note": None,
        "note_file": None,
    }
    base.update(kw)
    return _ns(db, **base)


def test_render_inserts_then_updates(curator_db, capsys):
    """Second call for the same (term, translation) must UPDATE, not
    insert a duplicate — the pair is UNIQUE."""

    assert cmd_terms_render(_render_ns(curator_db)) == 0
    assert "created rendering id=" in capsys.readouterr().out

    assert cmd_terms_render(_render_ns(curator_db, rendering="Supersession")) == 0
    assert "updated rendering id=" in capsys.readouterr().out

    conn = store.open_db(curator_db)
    rows = conn.execute(
        "SELECT default_rendering FROM term_renderings WHERE term_id=2"
    ).fetchall()
    conn.close()
    assert [r["default_rendering"] for r in rows] == ["Supersession"]


def test_render_update_keeps_existing_note_when_none_passed(curator_db, capsys):
    """The UPDATE uses COALESCE(?, translator_note), so omitting --note
    must preserve the note rather than blank it."""

    assert cmd_terms_render(_render_ns(curator_db, note="first note")) == 0
    assert cmd_terms_render(_render_ns(curator_db, rendering="Other", note=None)) == 0
    capsys.readouterr()

    conn = store.open_db(curator_db)
    row = conn.execute(
        "SELECT translator_note FROM term_renderings WHERE term_id=2"
    ).fetchone()
    conn.close()
    assert row["translator_note"] == "first note"


def _relate_ns(db: Path, **kw) -> argparse.Namespace:
    base = {
        "a": 1,
        "b": 2,
        "kind": "contrast",
        "symmetric": False,
        "note": None,
        "note_file": None,
    }
    base.update(kw)
    return _ns(db, **base)


def test_relate_self_is_rejected_before_touching_the_db(curator_db, capsys):
    assert cmd_terms_relate(_relate_ns(curator_db, a=1, b=1)) == 1
    assert "cannot relate a term to itself" in capsys.readouterr().err


def test_relate_symmetric_writes_both_directions(curator_db, capsys):
    assert cmd_terms_relate(_relate_ns(curator_db, symmetric=True)) == 0
    assert "(symmetric)" in capsys.readouterr().out

    conn = store.open_db(curator_db)
    pairs = {
        (r["term_id"], r["related_term_id"])
        for r in conn.execute("SELECT term_id, related_term_id FROM term_relations")
    }
    conn.close()
    assert pairs == {(1, 2), (2, 1)}


def test_relate_duplicate_exits_1(curator_db, capsys):
    assert cmd_terms_relate(_relate_ns(curator_db)) == 0
    capsys.readouterr()
    assert cmd_terms_relate(_relate_ns(curator_db)) == 1
    assert "relation already exists" in capsys.readouterr().err


def test_relate_unknown_term_is_reported_not_raised(curator_db, capsys):
    """FK violation takes the same branch as the duplicate case — it must
    exit 1 with a message rather than propagate."""

    assert cmd_terms_relate(_relate_ns(curator_db, b=999)) == 1
    assert "violates FK" in capsys.readouterr().err
