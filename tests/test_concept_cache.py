"""Tests for the concept-expansion cache (`minerva.concept_cache`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from minerva import concept_cache


@pytest.fixture
def conn(tmp_path: Path):
    db = tmp_path / "concept_cache.sqlite"
    c = concept_cache.open_db(db)
    yield c
    c.close()


def test_lookup_miss_returns_none(conn):
    assert (
        concept_cache.lookup(conn, query="anything", corpus="nietzsche", target_lang="deu") is None
    )


def test_round_trip_stores_and_returns_terms(conn):
    concept_cache.insert(
        conn,
        query="Who are the failures according to Nietzsche?",
        corpus="nietzsche",
        target_lang="deu",
        terms=["Mißratenen", "die Gescheiterten"],
        model="anthropic",
    )
    out = concept_cache.lookup(
        conn,
        query="Who are the failures according to Nietzsche?",
        corpus="nietzsche",
        target_lang="deu",
    )
    assert out == ["Mißratenen", "die Gescheiterten"]


def test_normalization_collapses_trivial_variants(conn):
    """Case + whitespace + trailing-punctuation differences must hit
    the same cache entry."""
    concept_cache.insert(
        conn,
        query="Who are the failures?",
        corpus="nietzsche",
        target_lang="deu",
        terms=["Mißratenen"],
        model="anthropic",
    )
    for variant in (
        "Who are the failures?",
        "who are the failures",
        "  WHO ARE THE FAILURES?  ",
        "Who   are\tthe   failures???",
    ):
        assert concept_cache.lookup(conn, query=variant, corpus="nietzsche", target_lang="deu") == [
            "Mißratenen"
        ], f"variant {variant!r} missed"


def test_distinct_corpora_dont_collide(conn):
    """Same query against different corpora must produce distinct
    cache entries — the target language differs and so do the right
    terms (e.g., 'failures' in Hegel would be 'das Misslungene')."""
    concept_cache.insert(
        conn,
        query="failures",
        corpus="nietzsche",
        target_lang="deu",
        terms=["Mißratenen"],
        model="anthropic",
    )
    concept_cache.insert(
        conn,
        query="failures",
        corpus="hegel",
        target_lang="deu",
        terms=["das Misslungene"],
        model="anthropic",
    )
    assert concept_cache.lookup(conn, query="failures", corpus="nietzsche", target_lang="deu") == [
        "Mißratenen"
    ]
    assert concept_cache.lookup(conn, query="failures", corpus="hegel", target_lang="deu") == [
        "das Misslungene"
    ]


def test_distinct_target_langs_dont_collide(conn):
    """Same query against the same corpus but different target_lang
    (rare, but defensive — never collapse the dimension)."""
    concept_cache.insert(
        conn,
        query="substance",
        corpus="aristotle",
        target_lang="grc",
        terms=["οὐσία"],
        model="anthropic",
    )
    concept_cache.insert(
        conn,
        query="substance",
        corpus="aristotle",
        target_lang="lat",
        terms=["substantia"],
        model="anthropic",
    )
    assert concept_cache.lookup(conn, query="substance", corpus="aristotle", target_lang="grc") == [
        "οὐσία"
    ]
    assert concept_cache.lookup(conn, query="substance", corpus="aristotle", target_lang="lat") == [
        "substantia"
    ]


def test_first_insert_wins(conn):
    """Stable expansions — re-inserting the same key does not overwrite.
    LLMs are non-deterministic; we want repeat-question answers to read
    the same way for the user."""
    concept_cache.insert(
        conn,
        query="q",
        corpus="nietzsche",
        target_lang="deu",
        terms=["original"],
        model="anthropic",
    )
    concept_cache.insert(
        conn,
        query="q",
        corpus="nietzsche",
        target_lang="deu",
        terms=["replacement"],
        model="anthropic",
    )
    out = concept_cache.lookup(conn, query="q", corpus="nietzsche", target_lang="deu")
    assert out == ["original"]


def test_hit_count_increments_on_lookup(conn):
    concept_cache.insert(
        conn,
        query="hot concept",
        corpus="nietzsche",
        target_lang="deu",
        terms=["x"],
        model="anthropic",
    )
    for _ in range(3):
        concept_cache.lookup(conn, query="hot concept", corpus="nietzsche", target_lang="deu")
    top = concept_cache.stats_top(conn, limit=5)
    assert top[0]["query_norm"] == "hot concept"
    assert top[0]["hit_count"] == 3


def test_count_reflects_inserts(conn):
    assert concept_cache.count(conn) == 0
    for i in range(4):
        concept_cache.insert(
            conn,
            query=f"q{i}",
            corpus="nietzsche",
            target_lang="deu",
            terms=["x"],
            model="anthropic",
        )
    assert concept_cache.count(conn) == 4


def test_delete_all_wipes_cache(conn):
    concept_cache.insert(
        conn,
        query="q",
        corpus="nietzsche",
        target_lang="deu",
        terms=["x"],
        model="anthropic",
    )
    assert concept_cache.delete_all(conn) == 1
    assert concept_cache.lookup(conn, query="q", corpus="nietzsche", target_lang="deu") is None


def test_empty_query_is_not_cached(conn):
    """An empty / whitespace-only query has no meaningful cache key —
    insert returns False and lookup returns None."""
    assert (
        concept_cache.insert(
            conn,
            query="   ",
            corpus="nietzsche",
            target_lang="deu",
            terms=["x"],
            model="anthropic",
        )
        is False
    )
    assert concept_cache.lookup(conn, query="   ", corpus="nietzsche", target_lang="deu") is None
