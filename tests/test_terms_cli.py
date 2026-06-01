"""Tests for the `minerva terms` curator CLI.

We exercise the subcommands by invoking ``main`` with synthetic
``argv`` lists and capturing stdout/stderr. The point isn't to test
argparse — it's to lock down the curator-facing contract: which
flags land which rows, which errors are reported, which output shape
gets emitted to JSON.

Each test creates a fresh DB under ``tmp_path`` so the runs don't
interact.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from minerva import cli, store

# ════════════════════════════════════════════════════════════════════
# Test fixture
# ════════════════════════════════════════════════════════════════════


def _seed_db(db_path: Path) -> None:
    """Set up the minimum works/editions/translations/chunks rows the
    curator commands operate against."""
    conn = store.open_db(db_path)
    conn.executescript(
        """
        INSERT INTO works (id, author, title, original_language, citation_system)
        VALUES (1, 'Plato', 'Republic', 'grc', 'stephanus');

        INSERT INTO editions (id, work_id, name, language, year, is_canonical)
        VALUES (1, 1, 'Burnet OCT', 'grc', 1903, 1);

        INSERT INTO translations (id, work_id, translator_name, year, language)
        VALUES (1, 1, 'Paul Shorey', 1969, 'eng');

        INSERT INTO chunks (chunk_id, edition_id, lang, section, source_file, text, ord)
        VALUES ('chk-330a', 1, 'grc', '330a',
                'r.xml', 'pollou\\\\s o( au)to\\\\s lo/gos kai\\\\ a)/llo lo/gos te', 0);
        """
    )
    conn.commit()
    conn.close()


def _run(argv: list[str], capsys) -> tuple[int, str, str]:
    rc = cli.main(argv)
    out, err = capsys.readouterr()
    return rc, out, err


@pytest.fixture
def fresh_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "curator.sqlite"
    _seed_db(db_path)
    return db_path


# ════════════════════════════════════════════════════════════════════
# Read commands
# ════════════════════════════════════════════════════════════════════


def test_list_empty(fresh_db, capsys):
    rc, out, _ = _run(["terms", "list", "--db", str(fresh_db)], capsys)
    assert rc == 0
    # Header always prints; the body is empty when there are no terms.
    assert "source_form" in out
    assert "λόγος" not in out


def test_works_command_emits_seeded_work(fresh_db, capsys):
    rc, out, _ = _run(["terms", "works", "--db", str(fresh_db)], capsys)
    assert rc == 0
    assert "Republic" in out
    assert "stephanus" in out


def test_works_json_output(fresh_db, capsys):
    rc, out, _ = _run(["terms", "works", "--db", str(fresh_db), "--json"], capsys)
    assert rc == 0
    parsed = json.loads(out)
    assert any(w["title"] == "Republic" for w in parsed)


def test_editions_filtered_by_work_id(fresh_db, capsys):
    rc, out, _ = _run(
        ["terms", "editions", "--db", str(fresh_db), "--work-id", "1", "--json"],
        capsys,
    )
    assert rc == 0
    parsed = json.loads(out)
    assert len(parsed) == 1
    assert parsed[0]["lang"] == "grc"


# ════════════════════════════════════════════════════════════════════
# add / show
# ════════════════════════════════════════════════════════════════════


def test_add_creates_term_and_show_prints_it(fresh_db, capsys):
    rc, out, _ = _run(
        [
            "terms",
            "add",
            "--db",
            str(fresh_db),
            "--form",
            "λόγος",
            "--lang",
            "grc",
            "--gloss",
            "reason, account, ratio, word",
            "--transliteration",
            "lo/gos",
            "--description",
            "A central Platonic term.",
        ],
        capsys,
    )
    assert rc == 0
    assert "created term id=" in out

    rc, out, _ = _run(["terms", "show", "1", "--db", str(fresh_db)], capsys)
    assert rc == 0
    assert "λόγος" in out
    assert "lo/gos" in out
    assert "reason, account" in out


def test_add_duplicate_form_reports_existing(fresh_db, capsys):
    _run(
        ["terms", "add", "--db", str(fresh_db), "--form", "λόγος", "--lang", "grc", "--gloss", "x"],
        capsys,
    )
    rc, _, err = _run(
        [
            "terms",
            "add",
            "--db",
            str(fresh_db),
            "--form",
            "λόγος",
            "--lang",
            "grc",
            "--gloss",
            "x again",
        ],
        capsys,
    )
    assert rc == 1
    assert "already exists" in err


def test_show_by_form_with_lang(fresh_db, capsys):
    _run(
        ["terms", "add", "--db", str(fresh_db), "--form", "λόγος", "--lang", "grc", "--gloss", "x"],
        capsys,
    )
    rc, out, _ = _run(
        ["terms", "show", "λόγος", "--lang", "grc", "--db", str(fresh_db)],
        capsys,
    )
    assert rc == 0
    assert "id:" in out
    assert "λόγος" in out


def test_show_unknown_term_returns_error(fresh_db, capsys):
    rc, _, err = _run(["terms", "show", "9999", "--db", str(fresh_db)], capsys)
    assert rc == 1
    assert "no term matches" in err


# ════════════════════════════════════════════════════════════════════
# tag — the heavy command
# ════════════════════════════════════════════════════════════════════


def test_tag_uses_transliteration_as_match_form_for_greek(fresh_db, capsys):
    """Curator stores `λόγος` for display and `lo/gos` for chunk
    matching — `tag` must use the beta-code form to find positions
    in the Perseus-encoded chunk text."""
    _run(
        [
            "terms",
            "add",
            "--db",
            str(fresh_db),
            "--form",
            "λόγος",
            "--lang",
            "grc",
            "--transliteration",
            "lo/gos",
            "--gloss",
            "x",
        ],
        capsys,
    )
    rc, out, _ = _run(
        ["terms", "tag", "--db", str(fresh_db), "--term", "1", "--chunk", "chk-330a"],
        capsys,
    )
    assert rc == 0
    assert "instance 1/" in out


def test_tag_increments_instance_index_for_repeated_form(fresh_db, capsys):
    """The seeded chunk has two occurrences of `lo/gos`. First tag
    gets instance 1, second gets instance 2 via the shadow-address
    contract from `terms.insert_occurrence`."""
    _run(
        [
            "terms",
            "add",
            "--db",
            str(fresh_db),
            "--form",
            "λόγος",
            "--lang",
            "grc",
            "--transliteration",
            "lo/gos",
            "--gloss",
            "x",
        ],
        capsys,
    )
    _run(
        [
            "terms",
            "tag",
            "--db",
            str(fresh_db),
            "--term",
            "1",
            "--chunk",
            "chk-330a",
            "--occurrence",
            "1",
        ],
        capsys,
    )
    rc, _out, _ = _run(
        [
            "terms",
            "tag",
            "--db",
            str(fresh_db),
            "--term",
            "1",
            "--chunk",
            "chk-330a",
            "--occurrence",
            "2",
        ],
        capsys,
    )
    assert rc == 0
    # Verify the row's instance_index in the DB.
    conn = sqlite3.connect(fresh_db)
    indices = [
        r[0]
        for r in conn.execute(
            "SELECT instance_index FROM term_occurrences "
            "WHERE source_chunk_id = ? ORDER BY instance_index",
            ("chk-330a",),
        )
    ]
    assert indices == [1, 2]


def test_tag_match_miss_hints_at_transliteration(fresh_db, capsys):
    """When the term's source_form doesn't appear in the chunk and no
    transliteration is set, the error should hint that beta-code is
    expected for Greek chunks — the most common failure mode."""
    _run(
        ["terms", "add", "--db", str(fresh_db), "--form", "λόγος", "--lang", "grc", "--gloss", "x"],
        capsys,
    )
    rc, _, err = _run(
        ["terms", "tag", "--db", str(fresh_db), "--term", "1", "--chunk", "chk-330a"],
        capsys,
    )
    assert rc == 1
    assert "beta-code" in err


def test_tag_rejects_translation_chunk(fresh_db, capsys):
    """Occurrences anchor to source-language chunks. A chunk whose
    translation_id is set must be rejected at tag time."""
    conn = sqlite3.connect(fresh_db)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO chunks (chunk_id, translation_id, lang, section, "
        "source_file, text, ord) "
        "VALUES ('chk-eng', 1, 'eng', '330a', 'r-en.xml', 'account ...', 0)"
    )
    conn.commit()
    conn.close()
    _run(
        [
            "terms",
            "add",
            "--db",
            str(fresh_db),
            "--form",
            "account",
            "--lang",
            "eng",
            "--gloss",
            "x",
        ],
        capsys,
    )
    rc, _, err = _run(
        ["terms", "tag", "--db", str(fresh_db), "--term", "1", "--chunk", "chk-eng"],
        capsys,
    )
    assert rc == 1
    assert "translation" in err


# ════════════════════════════════════════════════════════════════════
# render / relate / canonical
# ════════════════════════════════════════════════════════════════════


def test_render_inserts_then_updates(fresh_db, capsys):
    """Calling `render` twice for the same (term, translation) updates
    in place rather than creating a duplicate row."""
    _run(
        ["terms", "add", "--db", str(fresh_db), "--form", "λόγος", "--lang", "grc", "--gloss", "x"],
        capsys,
    )
    rc, out, _ = _run(
        [
            "terms",
            "render",
            "--db",
            str(fresh_db),
            "--term",
            "1",
            "--translation",
            "1",
            "--as",
            "account",
        ],
        capsys,
    )
    assert rc == 0 and "created rendering" in out
    rc, out, _ = _run(
        [
            "terms",
            "render",
            "--db",
            str(fresh_db),
            "--term",
            "1",
            "--translation",
            "1",
            "--as",
            "reasoning",
            "--note",
            "Shorey's second-choice rendering in dialectical contexts.",
        ],
        capsys,
    )
    assert rc == 0 and "updated rendering" in out
    conn = sqlite3.connect(fresh_db)
    rows = conn.execute("SELECT default_rendering, translator_note FROM term_renderings").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "reasoning"
    assert "second-choice" in rows[0][1]


def test_relate_symmetric_inserts_both_directions(fresh_db, capsys):
    """--symmetric should add the reverse relation in one shot;
    asymmetric calls leave only the forward direction."""
    for form in ("λόγος", "νοῦς"):
        _run(
            [
                "terms",
                "add",
                "--db",
                str(fresh_db),
                "--form",
                form,
                "--lang",
                "grc",
                "--gloss",
                "x",
            ],
            capsys,
        )
    rc, _, _ = _run(
        [
            "terms",
            "relate",
            "--db",
            str(fresh_db),
            "--a",
            "1",
            "--b",
            "2",
            "--kind",
            "contrast",
            "--symmetric",
        ],
        capsys,
    )
    assert rc == 0
    conn = sqlite3.connect(fresh_db)
    pairs = sorted(
        (r[0], r[1]) for r in conn.execute("SELECT term_id, related_term_id FROM term_relations")
    )
    assert pairs == [(1, 2), (2, 1)]


def test_relate_self_rejected(fresh_db, capsys):
    _run(
        ["terms", "add", "--db", str(fresh_db), "--form", "λόγος", "--lang", "grc", "--gloss", "x"],
        capsys,
    )
    rc, _, err = _run(
        ["terms", "relate", "--db", str(fresh_db), "--a", "1", "--b", "1"],
        capsys,
    )
    assert rc == 1
    assert "cannot relate a term to itself" in err


def test_canonical_swap_enforces_unique_per_pair(fresh_db, capsys):
    """Adding a second grc edition for the same work, then marking
    it canonical, should flip is_canonical on the first one."""
    conn = sqlite3.connect(fresh_db)
    conn.execute(
        "INSERT INTO editions (id, work_id, name, language, year, is_canonical) "
        "VALUES (2, 1, 'Slings OCT', 'grc', 2003, 0)"
    )
    conn.commit()
    conn.close()
    rc, out, _ = _run(
        ["terms", "canonical", "--db", str(fresh_db), "--edition", "2"],
        capsys,
    )
    assert rc == 0 and "canonical" in out
    conn = sqlite3.connect(fresh_db)
    flags = dict(
        conn.execute(
            "SELECT id, is_canonical FROM editions WHERE work_id = 1 AND language = 'grc'"
        ).fetchall()
    )
    assert flags == {1: 0, 2: 1}


def test_canonical_unset(fresh_db, capsys):
    rc, _, _ = _run(
        ["terms", "canonical", "--db", str(fresh_db), "--edition", "1", "--unset"],
        capsys,
    )
    assert rc == 0
    conn = sqlite3.connect(fresh_db)
    flag = conn.execute("SELECT is_canonical FROM editions WHERE id = 1").fetchone()[0]
    assert flag == 0


# ════════════════════════════════════════════════════════════════════
# find (chunk lookup)
# ════════════════════════════════════════════════════════════════════


def test_find_emits_chunk_id_for_known_locator(fresh_db, capsys):
    rc, out, _ = _run(
        [
            "terms",
            "find",
            "--db",
            str(fresh_db),
            "--work",
            "Republic",
            "--lang",
            "grc",
            "--section",
            "330a",
            "--json",
        ],
        capsys,
    )
    assert rc == 0
    parsed = json.loads(out)
    assert parsed[0]["chunk_id"] == "chk-330a"


def test_find_returns_error_when_locator_unknown(fresh_db, capsys):
    rc, _, err = _run(
        ["terms", "find", "--db", str(fresh_db), "--work", "Phaedo", "--lang", "grc"],
        capsys,
    )
    assert rc == 1
    assert "no chunks match" in err


# ════════════════════════════════════════════════════════════════════
# suggest-locator
# ════════════════════════════════════════════════════════════════════


def _seed_db_with_sibling(db_path: Path) -> None:
    """Build a minimal fixture with two `works` rows that share an
    (author, original_language, citation_system) identity — KrV's
    cross-edition setup — and two chunks each so we can verify the
    helper resolves siblings via that triple, not via work_id."""
    conn = store.open_db(db_path)
    conn.executescript(
        """
        INSERT INTO works (id, author, title, original_language, citation_system)
        VALUES (10, 'Kant', 'Kritik der reinen Vernunft', 'deu', 'kant_ab'),
               (11, 'Kant', 'Critique of Pure Reason',    'deu', 'kant_ab');

        INSERT INTO editions (id, work_id, name, language, year, is_canonical)
        VALUES (10, 10, 'zeno HTML', 'deu', 1781, 1);

        INSERT INTO translations (id, work_id, translator_name, year, language)
        VALUES (10, 11, 'Guyer / Wood', 1998, 'eng');

        INSERT INTO chunks (chunk_id, edition_id, lang, section, source_file, text, ord)
        VALUES ('de-1', 10, 'deu', 'Einleitung, ¶1', 'krv_de.html',
                '[45] Daß alle unsere Erkenntnis mit der Erfahrung anfange', 0),
               ('de-2', 10, 'deu', 'Einleitung, ¶2', 'krv_de.html',
                'Wenn aber gleich alle unsere Erkenntnis', 1);
        INSERT INTO chunks (chunk_id, translation_id, lang, section, source_file, text, ord)
        VALUES ('en-1', 10, 'eng', 'B1', 'krv_en.pdf',
                'All our cognition begins with experience', 0),
               ('en-2', 10, 'eng', 'B2', 'krv_en.pdf',
                'Although all our cognition starts with experience', 1);
        """
    )
    conn.commit()
    conn.close()


def test_suggest_locator_returns_sibling_sections(tmp_path, capsys):
    db_path = tmp_path / "curator.sqlite"
    _seed_db_with_sibling(db_path)
    rc, out, err = _run(
        ["terms", "suggest-locator", "--db", str(db_path), "--chunk", "de-1"],
        capsys,
    )
    assert rc == 0
    # The English sibling sections should appear in the table.
    assert "B1" in out
    assert "B2" in out
    # Inline AA-page anchor surfaced as a hint.
    assert "[45]" in err


def test_suggest_locator_unknown_chunk_errors(fresh_db, capsys):
    rc, _, err = _run(
        ["terms", "suggest-locator", "--db", str(fresh_db), "--chunk", "missing"],
        capsys,
    )
    assert rc == 1
    assert "no chunk" in err
