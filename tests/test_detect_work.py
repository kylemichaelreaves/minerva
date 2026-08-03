"""Work auto-detection from a query (retrieval scoping)."""

from __future__ import annotations

import sqlite3

import pytest

from minerva.agent import detect_work


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute(
        "CREATE TABLE works (id INTEGER PRIMARY KEY, author TEXT, title TEXT)"
    )
    c.execute(
        "CREATE TABLE translations "
        "(id INTEGER PRIMARY KEY, work_id INTEGER, language TEXT, title_local TEXT)"
    )
    c.execute(
        "CREATE TABLE editions "
        "(id INTEGER PRIMARY KEY, work_id INTEGER, language TEXT, title_local TEXT)"
    )
    c.executemany(
        "INSERT INTO works (id, author, title) VALUES (?, ?, ?)",
        [
            (1, "Nietzsche", "Zur Genealogie der Moral"),
            (2, "Nietzsche", "Jenseits von Gut und Böse"),
            (3, "Nietzsche", "Der Antichrist"),
            (4, "Nietzsche", "Briefe"),
            (5, "Kant", "Kritik der reinen Vernunft"),
            # Plato, canonicalised to Latinized-Greek titles (migration 0023).
            (10, "Plato", "Politeia"),
            (11, "Plato", "Phaidros"),
            (12, "Plato", "Nomoi"),
            # Same title_local as Plato 11, different author: only the
            # corpus filter keeps these apart.
            (20, "Aesop", "Phaedrus"),
            # Two works of one author sharing a title_local — the
            # ambiguity case detect_work must refuse to guess at.
            (30, "Twinauthor", "Erstes Werk"),
            (31, "Twinauthor", "Zweites Werk"),
        ],
    )
    c.executemany(
        "INSERT INTO translations (work_id, language, title_local) VALUES (?, ?, ?)",
        [
            (10, "eng", "Republic"),
            (11, "eng", "Phaedrus"),
            (12, "eng", "Laws"),
            (30, "eng", "Twin Work"),
            (31, "eng", "Twin Work"),
            # A translation row carrying no local title must not match.
            (1, "eng", None),
        ],
    )
    c.executemany(
        "INSERT INTO editions (work_id, language, title_local) VALUES (?, ?, ?)",
        [
            (10, "deu", "Der Staat"),
            (11, "grc", None),
        ],
    )
    return c


def test_detects_named_work(conn):
    assert detect_work(conn, "Wo spricht er in Die Genealogie der Moral?", "nietzsche") == 1


def test_requires_all_significant_tokens(conn):
    # "Moral" alone is not enough to scope to the Genealogie.
    assert detect_work(conn, "Was sagt Nietzsche über Moral?", "nietzsche") is None


def test_stopwords_do_not_trigger(conn):
    # A bare "der" must not match "Der Antichrist".
    assert detect_work(conn, "Was ist der Mensch?", "nietzsche") is None


def test_scoped_to_corpus(conn):
    # The Kant title's tokens aren't in the query; also corpus-scoped.
    assert detect_work(conn, "Die Genealogie der Moral", "kant") is None


def test_prefers_most_specific(conn):
    # Mentioning the full Jenseits title scopes to it (3 sig tokens),
    # not to anything shorter.
    assert detect_work(conn, "in Jenseits von Gut und Böse", "nietzsche") == 2


def test_no_match_returns_none(conn):
    assert detect_work(conn, "a question about nothing in particular", "nietzsche") is None


def test_detects_work_by_english_translation_title(conn):
    # "Republic" lives in translations.title_local, not works.title.
    assert detect_work(conn, "the divided line in Plato's Republic", "plato") == 10


def test_detects_work_by_german_edition_title(conn):
    # "Der Staat" lives in editions.title_local; "der" is a stopword,
    # so "Staat" alone has to carry the match.
    assert detect_work(conn, "Wo steht das in Platons Der Staat?", "plato") == 10


def test_canonical_title_still_detected_alongside_local_titles(conn):
    assert detect_work(conn, "the divided line in Plato's Politeia", "plato") == 10


def test_local_title_is_corpus_scoped(conn):
    # Aesop's Phaedrus (the fabulist) and Plato's Phaidros both answer to
    # "Phaedrus"; only the corpus filter keeps them apart.
    assert detect_work(conn, "what does Phaedrus say", "plato") == 11
    assert detect_work(conn, "what does Phaedrus say", "aesop") == 20


def test_ambiguous_local_title_returns_none(conn):
    # Two works of one author share "Twin Work". detect_work is
    # conservative: refuse to narrow rather than pick by row order.
    assert detect_work(conn, "in Twin Work he argues", "twinauthor") is None


def test_null_local_title_does_not_match(conn):
    # translations/editions rows with NULL title_local must contribute
    # no tokens — otherwise they'd match every query.
    assert detect_work(conn, "a question about nothing in particular", "plato") is None
    assert detect_work(conn, "was sagt er über Moral?", "nietzsche") is None
