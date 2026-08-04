"""Tests for the glossary spec's natural-key anchors (#193).

`editions.id` and `translations.id` are surrogate keys handed out by
insertion order, so ``minerva index --reset`` reshuffles them. A spec
that stored the id recorded where a work happened to sit, not which work
the curator meant — which is how ``aristotle.grc.yaml``'s edition 58
came to name Homer's Iliad. These tests pin the resolution that replaces
it, and the errors it produces when a name doesn't land.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from minerva import store
from minerva.glossary_spec import (
    SpecError,
    load_spec,
    resolve_against_db,
    resolve_and_validate,
)


@pytest.fixture
def catalog(tmp_path: Path) -> sqlite3.Connection:
    """works/editions/translations shaped like the real index, including
    the two irregularities the resolver has to cope with: one translator
    who rendered several works for the same author, and a translation
    filed under its own `works` row rather than its edition's."""

    conn = store.open_db(tmp_path / "catalog.sqlite")

    def work(author: str, title: str) -> int:
        return int(
            conn.execute(
                "INSERT INTO works (author, title, original_language, citation_system) "
                "VALUES (?, ?, 'grc', 'bekker')",
                (author, title),
            ).lastrowid
        )

    # Decoys inserted FIRST so the ids of the rows we care about are not 1.
    iliad = work("Homer", "Iliad")
    conn.execute(
        "INSERT INTO editions (work_id, name, language, year) VALUES (?, ?, 'grc', ?)",
        (iliad, "Homeri Opera", 1920),
    )
    conn.execute(
        "INSERT INTO translations (work_id, translator_name, language, year) "
        "VALUES (?, ?, 'eng', ?)",
        (iliad, "A. T. Murray", 1924),
    )

    categories = work("Aristotle", "Categories")
    ethics = work("Aristotle", "Nicomachean Ethics")
    eudemian = work("Aristotle", "Eudemian Ethics")
    conn.execute(
        "INSERT INTO editions (work_id, name, language, year) VALUES (?, ?, 'grc', ?)",
        (categories, "Immanuel Bekker", 1837),
    )
    conn.execute(
        "INSERT INTO editions (work_id, name, language, year) VALUES (?, ?, 'grc', ?)",
        (ethics, "J. Bywater", 1894),
    )
    conn.execute(
        "INSERT INTO translations (work_id, translator_name, language, year) "
        "VALUES (?, ?, 'eng', NULL)",
        (categories, "E. M. Edghill"),
    )
    # One translator, two works, same author — the author-wide fallback
    # must refuse to guess between these.
    for w in (ethics, eudemian):
        conn.execute(
            "INSERT INTO translations (work_id, translator_name, language, year) "
            "VALUES (?, ?, 'eng', ?)",
            (w, "H. Rackham", 1934),
        )
    # Hegel's shape: the translation lives under its OWN works row, so a
    # work-scoped lookup from the edition's title finds nothing.
    pinkard = work("Hegel", "Phenomenology of Spirit (Pinkard)")
    phaenomenologie = work("Hegel", "Phänomenologie des Geistes")
    conn.execute(
        "INSERT INTO editions (work_id, name, language, year) VALUES (?, ?, 'deu', ?)",
        (phaenomenologie, "Suhrkamp", 1986),
    )
    conn.execute(
        "INSERT INTO translations (work_id, translator_name, language, year) "
        "VALUES (?, ?, 'eng', ?)",
        (pinkard, "Terry Pinkard", 2018),
    )
    conn.commit()
    return conn


def _spec(tmp_path: Path, body: str, *, author: str = "Aristotle", language: str = "grc"):
    path = tmp_path / "spec.yaml"
    path.write_text(
        f"version: 1\nlanguage: {language}\nauthor: {author}\nterms:\n{body}",
        encoding="utf-8",
    )
    return load_spec(path)


_TERM_HEAD = """  - lemma: οὐσία
    short_gloss: substance
    long_description: The first category.
    apply_to:
"""


def _ids(conn: sqlite3.Connection, sql: str, *params: object) -> int:
    row = conn.execute(sql, params).fetchone()
    assert row is not None, f"fixture missing row for {sql!r} {params!r}"
    return int(row[0])


def test_natural_keys_resolve_to_the_right_ids(catalog, tmp_path: Path):
    spec = _spec(
        tmp_path,
        _TERM_HEAD
        + """      - work: Categories
        edition: Immanuel Bekker
        translations:
          - translator: E. M. Edghill
            rendering: substance
""",
    )
    resolved, errors = resolve_and_validate(spec, catalog)
    assert errors == []

    apply = resolved.terms[0].apply_to[0]
    expected_edition = _ids(
        catalog,
        "SELECT e.id FROM editions e JOIN works w ON w.id = e.work_id "
        "WHERE w.title = 'Categories'",
    )
    expected_translation = _ids(
        catalog,
        "SELECT id FROM translations WHERE translator_name = 'E. M. Edghill'",
    )
    assert apply.edition_id == expected_edition
    assert apply.translations[0].translation_id == expected_translation
    # The decoys did their job: neither id is 1, so a resolver that
    # simply returned the first row would not pass this.
    assert expected_edition != 1 and expected_translation != 1


def test_numeric_ids_still_accepted_as_an_override(catalog, tmp_path: Path):
    """The escape hatch stays open for rows a name cannot separate."""

    edition_id = _ids(
        catalog,
        "SELECT e.id FROM editions e JOIN works w ON w.id = e.work_id "
        "WHERE w.title = 'Categories'",
    )
    translation_id = _ids(
        catalog, "SELECT id FROM translations WHERE translator_name = 'E. M. Edghill'"
    )
    spec = _spec(
        tmp_path,
        _TERM_HEAD
        + f"""      - work: Categories
        edition_id: {edition_id}
        translations:
          - id: {translation_id}
            rendering: substance
""",
    )
    resolved, errors = resolve_and_validate(spec, catalog)
    assert errors == []
    assert resolved.terms[0].apply_to[0].edition_id == edition_id


def test_rotted_numeric_edition_id_is_still_caught(catalog, tmp_path: Path):
    """The #193 scenario itself: a numeric id that now names another
    author's work. The `work:` cross-check is the only thing standing
    between that and Aristotle's vocabulary attaching to the Iliad."""

    homer_edition = _ids(
        catalog,
        "SELECT e.id FROM editions e JOIN works w ON w.id = e.work_id "
        "WHERE w.title = 'Iliad'",
    )
    spec = _spec(
        tmp_path,
        _TERM_HEAD
        + f"""      - work: Categories
        edition_id: {homer_edition}
""",
    )
    _, errors = resolve_and_validate(spec, catalog)
    assert any("belongs to 'Iliad'" in e for e in errors), errors


@pytest.mark.parametrize(
    ("anchors", "expected"),
    [
        ("        edition: Immanuel Bekker\n        edition_id: 3\n", "exactly one"),
        ("", "exactly one"),
    ],
    ids=["both", "neither"],
)
def test_edition_anchor_must_be_exactly_one(tmp_path: Path, anchors: str, expected: str):
    with pytest.raises(SpecError, match=expected):
        _spec(tmp_path, _TERM_HEAD + "      - work: Categories\n" + anchors)


def test_translation_anchor_must_be_exactly_one(tmp_path: Path):
    with pytest.raises(SpecError, match="exactly one"):
        _spec(
            tmp_path,
            _TERM_HEAD
            + """      - work: Categories
        edition: Immanuel Bekker
        translations:
          - translator: E. M. Edghill
            id: 4
            rendering: substance
""",
        )


def test_unknown_edition_name_lists_the_candidates(catalog, tmp_path: Path):
    """A miss must say what IS there — these names are long and easy to
    mistype, and a bare 'not found' leaves the curator guessing."""

    spec = _spec(
        tmp_path,
        _TERM_HEAD
        + """      - work: Categories
        edition: Bekker
""",
    )
    _, errors = resolve_and_validate(spec, catalog)
    assert len(errors) == 1
    assert "no 'grc' edition named 'Bekker'" in errors[0]
    assert "'Immanuel Bekker' (1837)" in errors[0]


def test_ambiguous_translator_refuses_to_guess(catalog, tmp_path: Path):
    """Rackham translated both Ethics. Work-scoping resolves it; without
    a scope the resolver must report rather than pick."""

    spec = _spec(
        tmp_path,
        _TERM_HEAD
        + """      - work: Nicomachean Ethics
        edition: J. Bywater
        translations:
          - translator: H. Rackham
            work: Eudemian Ethics
            rendering: virtue
""",
    )
    resolved, errors = resolve_and_validate(spec, catalog)
    assert errors == []
    eudemian_rackham = _ids(
        catalog,
        "SELECT t.id FROM translations t JOIN works w ON w.id = t.work_id "
        "WHERE w.title = 'Eudemian Ethics'",
    )
    assert resolved.terms[0].apply_to[0].translations[0].translation_id == eudemian_rackham


def test_translator_under_a_sibling_works_row_resolves(catalog, tmp_path: Path):
    """Ingest files some translations under their own `works` row — work
    'Phenomenology of Spirit (Pinkard)' beside 'Phänomenologie des
    Geistes'. The work-scoped lookup misses; the author-wide fallback
    must find it."""

    spec = _spec(
        tmp_path,
        _TERM_HEAD.replace("οὐσία", "Geist").replace("substance", "spirit")
        + """      - work: Phänomenologie des Geistes
        edition: Suhrkamp
        translations:
          - translator: Terry Pinkard
            rendering: spirit
""",
        author="Hegel",
        language="deu",
    )
    resolved, errors = resolve_and_validate(spec, catalog)
    assert errors == []
    expected = _ids(
        catalog, "SELECT id FROM translations WHERE translator_name = 'Terry Pinkard'"
    )
    assert resolved.terms[0].apply_to[0].translations[0].translation_id == expected


def test_unknown_translator_lists_the_candidates(catalog, tmp_path: Path):
    spec = _spec(
        tmp_path,
        _TERM_HEAD
        + """      - work: Categories
        edition: Immanuel Bekker
        translations:
          - translator: Edghill
            rendering: substance
""",
    )
    _, errors = resolve_and_validate(spec, catalog)
    assert len(errors) == 1
    assert "no translation by 'Edghill'" in errors[0]
    assert "'E. M. Edghill'" in errors[0]


def test_unresolved_anchor_leaves_id_none_and_is_not_double_reported(
    catalog, tmp_path: Path
):
    """A failed resolution must not then trip the id-existence check —
    one clear error, not two, and never a bare `edition_id None does not
    exist`."""

    spec = _spec(
        tmp_path,
        _TERM_HEAD
        + """      - work: Categories
        edition: Nonexistent
        translations:
          - translator: Nobody
            rendering: substance
""",
    )
    resolved, errors = resolve_and_validate(spec, catalog)
    assert resolved.terms[0].apply_to[0].edition_id is None
    assert len(errors) == 2
    assert not any("does not exist" in e for e in errors)


def test_resolve_against_db_leaves_the_input_spec_untouched(catalog, tmp_path: Path):
    """Resolution returns a new spec rather than mutating in place, so a
    caller holding the parsed spec still sees what the file said."""

    spec = _spec(
        tmp_path,
        _TERM_HEAD
        + """      - work: Categories
        edition: Immanuel Bekker
""",
    )
    resolved, _ = resolve_against_db(spec, catalog)
    assert spec.terms[0].apply_to[0].edition_id is None
    assert resolved.terms[0].apply_to[0].edition_id is not None
    assert resolved.terms[0].apply_to[0].edition_name == "Immanuel Bekker"


def test_edition_year_disambiguates_a_repeated_edition_name(catalog, tmp_path: Path):
    """`editions` is UNIQUE (work_id, name, year), so one name can appear
    twice under different years. A second edition in the same language
    has to be non-canonical — `editions_canonical_unique` is a partial
    UNIQUE on (work_id, language) WHERE is_canonical = 1."""

    work_id = _ids(catalog, "SELECT id FROM works WHERE title = 'Categories'")
    catalog.execute(
        "INSERT INTO editions (work_id, name, language, year, is_canonical) "
        "VALUES (?, ?, 'grc', ?, 0)",
        (work_id, "Immanuel Bekker", 1831),
    )
    catalog.commit()

    ambiguous = _spec(
        tmp_path,
        _TERM_HEAD + "      - work: Categories\n        edition: Immanuel Bekker\n",
    )
    _, errors = resolve_and_validate(ambiguous, catalog)
    assert len(errors) == 1
    assert "add `edition_year:`" in errors[0]

    pinned = _spec(
        tmp_path,
        _TERM_HEAD
        + "      - work: Categories\n        edition: Immanuel Bekker\n"
        + "        edition_year: 1831\n",
    )
    resolved, errors = resolve_and_validate(pinned, catalog)
    assert errors == []
    expected = _ids(
        catalog,
        "SELECT id FROM editions WHERE name = 'Immanuel Bekker' AND year = 1831",
    )
    assert resolved.terms[0].apply_to[0].edition_id == expected


def test_shipped_aristotle_spec_uses_natural_keys_only(tmp_path: Path):
    """The one curated spec in the repo must not regress to surrogate
    ids — that is the state #193 documents, where every anchor pointed
    at another author's work."""

    spec = load_spec(Path("data/glossary/aristotle.grc.yaml"))
    assert spec.terms, "spec parsed empty"
    for term in spec.terms:
        for apply in term.apply_to:
            assert apply.edition_id is None, f"{term.lemma} still anchors on edition_id"
            assert apply.edition_name, f"{term.lemma} has no edition name"
            for tr in apply.translations:
                assert tr.translation_id is None, f"{term.lemma} still anchors on id"
                assert tr.translator_name, f"{term.lemma} has no translator name"
