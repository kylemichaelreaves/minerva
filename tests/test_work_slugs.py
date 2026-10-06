"""Slugs for reader work URLs (#602).

The algorithm is specified in
``docs/superpowers/specs/2026-09-14-reader-work-url-slugs-design.md`` and has
TWO implementations — this one and ``web/src/slug.ts``. They are held together
by ``data/authors/work_slugs.json``, asserted from both suites; see
``test_work_slugs_fixture_matches_index``.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from minerva.reader.slugs import (
    SlugCollisionError,
    slug_snapshot_drift,
    slugify,
    validate_slug_snapshot,
    work_key,
    work_slug_table,
)

INDEX_PATH = Path(__file__).resolve().parents[1] / "data" / "index.sqlite"


def test_slugify_lowercases_and_hyphenates_ascii() -> None:
    assert slugify("Nicomachean Ethics") == "nicomachean-ethics"


def test_slugify_strips_combining_marks_after_nfkd() -> None:
    assert slugify("Die fröhliche Wissenschaft") == "die-frohliche-wissenschaft"


def test_slugify_expands_characters_nfkd_does_not_decompose() -> None:
    # NFKD leaves these atomic, so step 2 of the spec has to spell them out.
    assert slugify("bloßen") == "blossen"
    assert slugify("Æsop") == "aesop"
    assert slugify("œuvre") == "oeuvre"
    assert slugify("Søren") == "soren"


def test_slugify_collapses_runs_of_punctuation_to_one_hyphen() -> None:
    assert slugify("Beantwortung der Frage: Was ist Aufklärung?") == (
        "beantwortung-der-frage-was-ist-aufklarung"
    )


def test_slugify_trims_leading_and_trailing_hyphens() -> None:
    assert slugify("  ...Leviathan!  ") == "leviathan"


def test_work_slug_table_is_keyed_by_slug_pair_and_collision_free() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE works (author TEXT, title TEXT);"
        "INSERT INTO works VALUES ('Kant', 'Beantwortung der Frage: Was ist Aufklärung?'),"
        " ('Nietzsche', 'Die fröhliche Wissenschaft');"
    )
    assert work_slug_table(conn) == {
        "kant/beantwortung-der-frage-was-ist-aufklarung": {
            "author": "Kant",
            "title": "Beantwortung der Frage: Was ist Aufklärung?",
        },
        "nietzsche/die-frohliche-wissenschaft": {
            "author": "Nietzsche",
            "title": "Die fröhliche Wissenschaft",
        },
    }


def test_work_slug_table_raises_on_a_colliding_pair() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE works (author TEXT, title TEXT);"
        "INSERT INTO works VALUES ('Kant', 'Was ist Aufklärung?'), ('Kant', 'Was ist Aufklarung!');"
    )
    with pytest.raises(SlugCollisionError, match="kant/was-ist-aufklarung"):
        work_slug_table(conn)


# ── The committed fixture ────────────────────────────────────────────────
# `data/index.sqlite` is gitignored, so a test that reads the live index runs
# here and SKIPS in CI (#573). The fixture below is committed, so these two
# assertions measure the same thing on both machines; the index comparison
# underneath them is the one that only ever runs locally, and `make
# check-authors` is what makes that matter.

WORK_SLUGS_PATH = Path(__file__).resolve().parents[1] / "data" / "authors" / "work_slugs.json"


def _fixture() -> dict[str, dict[str, str]]:
    return json.loads(WORK_SLUGS_PATH.read_text(encoding="utf-8"))


def test_every_fixture_key_is_the_slug_of_its_own_author_and_title() -> None:
    mismatched = {
        key: entry
        for key, entry in _fixture().items()
        if work_key(entry["author"], entry["title"]) != key
    }
    assert mismatched == {}


def test_the_fixture_has_no_empty_slug_on_either_side() -> None:
    empty = [key for key in _fixture() if any(part == "" for part in key.split("/"))]
    assert empty == []


@pytest.mark.skipif(not INDEX_PATH.exists(), reason="data/index.sqlite is gitignored")
def test_work_slugs_fixture_matches_index() -> None:
    conn = sqlite3.connect(f"file:{INDEX_PATH}?mode=ro", uri=True)
    try:
        assert work_slug_table(conn) == _fixture()
    finally:
        conn.close()


# ── What the gate actually runs ──────────────────────────────────────────


def test_validate_slug_snapshot_accepts_a_self_consistent_snapshot() -> None:
    assert validate_slug_snapshot({"kant/kritik": {"author": "Kant", "title": "Kritik"}}) == []


def test_validate_slug_snapshot_rejects_a_key_that_is_not_its_own_slug() -> None:
    errs = validate_slug_snapshot({"kant/Kritik": {"author": "Kant", "title": "Kritik"}})
    assert len(errs) == 1
    assert "kant/Kritik" in errs[0]


def test_validate_slug_snapshot_rejects_an_empty_slug_on_either_side() -> None:
    errs = validate_slug_snapshot({"/kritik": {"author": "!!!", "title": "Kritik"}})
    assert len(errs) == 1
    assert "empty" in errs[0]


def test_slug_snapshot_drift_is_silent_when_the_snapshot_matches() -> None:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE works (author TEXT, title TEXT);INSERT INTO works VALUES ('Kant', 'Kritik');"
    )
    assert slug_snapshot_drift(conn, {"kant/kritik": {"author": "Kant", "title": "Kritik"}}) == []


def test_slug_snapshot_drift_names_a_work_the_snapshot_is_missing() -> None:
    """An ingest landed and nobody re-ran `make generate-authors`."""

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE works (author TEXT, title TEXT);"
        "INSERT INTO works VALUES ('Kant', 'Kritik'), ('Hume', 'Treatise');"
    )
    errs = slug_snapshot_drift(conn, {"kant/kritik": {"author": "Kant", "title": "Kritik"}})
    assert len(errs) == 1
    assert "missing from the snapshot: hume/treatise" in errs[0]
    assert "generate-authors" in errs[0]


def test_slug_snapshot_drift_names_a_work_the_index_no_longer_has() -> None:
    """The other direction: a work was renamed or pruned and the committed
    table still advertises a slug that resolves to nothing."""

    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE works (author TEXT, title TEXT);INSERT INTO works VALUES ('Kant', 'Kritik');"
    )
    errs = slug_snapshot_drift(
        conn,
        {
            "kant/kritik": {"author": "Kant", "title": "Kritik"},
            "hume/treatise": {"author": "Hume", "title": "Treatise"},
        },
    )
    assert len(errs) == 1
    assert "no longer in the index: hume/treatise" in errs[0]
