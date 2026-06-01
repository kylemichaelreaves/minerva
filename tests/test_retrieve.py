"""Tests for `minerva.retrieve` — query sanitization, score normalization,
filter SQL fragments, and end-to-end search against a small in-memory index."""

from __future__ import annotations

import numpy as np

from minerva import retrieve

# ---------- _sanitize_fts_query ----------


def test_sanitize_empty_input():
    assert retrieve._sanitize_fts_query("") == ""
    assert retrieve._sanitize_fts_query("   ") == ""


def test_sanitize_strips_punctuation():
    assert retrieve._sanitize_fts_query("hello, world!") == '"hello" OR "world"'


def test_sanitize_single_token():
    assert retrieve._sanitize_fts_query("justice") == '"justice"'


def test_sanitize_multi_token_joined_with_or():
    out = retrieve._sanitize_fts_query("divided line republic")
    assert out == '"divided" OR "line" OR "republic"'


def test_sanitize_drops_pure_punctuation():
    assert retrieve._sanitize_fts_query("?!.") == ""


# ---------- _normalize_scores ----------


def test_normalize_empty_dict():
    assert retrieve._normalize_scores({}) == {}


def test_normalize_single_value_maps_to_one():
    out = retrieve._normalize_scores({"a": 7.5})
    assert out == {"a": 1.0}


def test_normalize_all_equal_maps_to_one():
    out = retrieve._normalize_scores({"a": 2.0, "b": 2.0, "c": 2.0})
    assert out == {"a": 1.0, "b": 1.0, "c": 1.0}


def test_normalize_min_max_maps_to_zero_one_range():
    out = retrieve._normalize_scores({"low": 0.0, "mid": 5.0, "high": 10.0})
    assert out["low"] == 0.0
    assert out["high"] == 1.0
    assert abs(out["mid"] - 0.5) < 1e-9


# ---------- filter SQL builders ----------


def test_lang_filter_for_specific_lang():
    sql, params = retrieve._lang_filter("eng")
    assert sql == " AND chunks.lang = ?"
    assert params == ("eng",)


def test_lang_filter_for_any_or_none_returns_no_clause():
    assert retrieve._lang_filter(None) == ("", ())
    assert retrieve._lang_filter("any") == ("", ())


def test_corpus_filter_for_specific_corpus():
    sql, params = retrieve._corpus_filter("plato")
    assert sql == " AND cf.corpus = ?"
    assert params == ("plato",)


def test_corpus_filter_for_any_or_none_returns_no_clause():
    assert retrieve._corpus_filter(None) == ("", ())
    assert retrieve._corpus_filter("any") == ("", ())


def test_speaker_filter_uses_collate_nocase():
    sql, params = retrieve._speaker_filter("Socrates")
    assert sql == " AND chunks.speaker = ? COLLATE NOCASE"
    assert params == ("Socrates",)


def test_speaker_filter_for_empty_or_any_returns_no_clause():
    assert retrieve._speaker_filter(None) == ("", ())
    assert retrieve._speaker_filter("") == ("", ())
    assert retrieve._speaker_filter("any") == ("", ())


# ---------- search end-to-end ----------


def test_search_returns_hits_for_topical_query(populated_db):
    hits = retrieve.search(populated_db, "divided line", top_k=3, lang="eng")
    assert len(hits) > 0
    # Top hit's score is normalized; should be the maximum (1.0).
    assert hits[0].score == 1.0
    assert all(isinstance(h, retrieve.Hit) for h in hits)


def test_search_respects_corpus_filter(populated_db):
    hits = retrieve.search(populated_db, "function virtue", top_k=3, corpus="aristotle", lang="eng")
    assert all(h.meta["corpus"] == "aristotle" for h in hits)


def test_search_respects_lang_filter(populated_db):
    hits = retrieve.search(populated_db, "divided line", top_k=3, lang="eng")
    assert all(h.meta["lang"] == "eng" for h in hits)


def test_search_returns_empty_for_nonsense_query(populated_db):
    hits = retrieve.search(populated_db, "zxqv asdfgh", top_k=3, lang="eng")
    assert hits == []


def test_search_top_hit_for_divided_line_is_in_republic(populated_db):
    hits = retrieve.search(populated_db, "divided line", top_k=3, lang="eng")
    assert hits[0].meta["work"] == "Republic"


# ---------- speaker filter end-to-end ----------


def test_search_with_speaker_filter_returns_only_matching_chunks(speaker_db):
    hits = retrieve.search(
        speaker_db,
        "Socrates Theaetetus knowledge perception inquiry",
        top_k=10,
        lang="eng",
        speaker="Socrates",
    )
    assert len(hits) > 0
    assert all(h.meta["speaker"] == "Socrates" for h in hits)


def test_search_speaker_filter_is_case_insensitive(speaker_db):
    hits = retrieve.search(
        speaker_db,
        "Socrates Theaetetus knowledge perception",
        top_k=10,
        lang="eng",
        speaker="socrates",
    )
    assert len(hits) > 0
    assert all(h.meta["speaker"] == "Socrates" for h in hits)


def test_search_speaker_any_means_no_filter(speaker_db):
    hits_any = retrieve.search(
        speaker_db,
        "knowledge perception",
        top_k=10,
        lang="eng",
        speaker="any",
    )
    speakers = {h.meta["speaker"] for h in hits_any}
    # Both Socrates and Theaetetus should be reachable.
    assert "Socrates" in speakers
    assert "Theaetetus" in speakers


def test_search_speaker_filter_returns_nothing_for_unknown_speaker(speaker_db):
    hits = retrieve.search(
        speaker_db,
        "knowledge perception",
        top_k=10,
        lang="eng",
        speaker="Aristotle",
    )
    assert hits == []


# ---------- format_locator ----------


def test_format_locator_plato_with_book():
    meta = {"author": "Plato", "work": "Republic", "section": "509d", "book": "6", "lang": "eng"}
    assert retrieve.format_locator(meta) == "Plato, Republic 509d Bk 6"


def test_format_locator_aristotle_no_book():
    meta = {
        "author": "Aristotle",
        "work": "Nicomachean Ethics",
        "section": "1097b",
        "book": None,
        "lang": "eng",
    }
    assert retrieve.format_locator(meta) == "Aristotle, Nicomachean Ethics 1097b"


def test_format_locator_book_only_for_republic_or_laws():
    # "Phaedo" with book metadata should NOT print "Bk N"
    meta = {"author": "Plato", "work": "Phaedo", "section": "72e", "book": "1", "lang": "eng"}
    assert "Bk" not in retrieve.format_locator(meta)


def test_format_locator_appends_lang_when_not_english():
    meta = {"author": "Plato", "work": "Republic", "section": "509d", "book": None, "lang": "grc"}
    out = retrieve.format_locator(meta)
    assert out.endswith("[grc]")


def test_format_locator_unknown_for_empty_meta():
    assert retrieve.format_locator({}) == "(unknown)"


# ---------- _vector_search (without sentence-transformers; uses raw cosine) ----------


def test_normalize_handles_negative_values():
    out = retrieve._normalize_scores({"a": -2.0, "b": 0.0, "c": 2.0})
    assert out["a"] == 0.0
    assert out["c"] == 1.0
    assert abs(out["b"] - 0.5) < 1e-9


def test_normalize_returns_python_floats_not_numpy_scalars():
    out = retrieve._normalize_scores({"a": 0.0, "b": 1.0})
    for v in out.values():
        assert isinstance(v, float)
        assert not isinstance(v, np.floating)
