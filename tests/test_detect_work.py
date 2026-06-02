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
    c.executemany(
        "INSERT INTO works (id, author, title) VALUES (?, ?, ?)",
        [
            (1, "Nietzsche", "Zur Genealogie der Moral"),
            (2, "Nietzsche", "Jenseits von Gut und Böse"),
            (3, "Nietzsche", "Der Antichrist"),
            (4, "Nietzsche", "Briefe"),
            (5, "Kant", "Kritik der reinen Vernunft"),
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
