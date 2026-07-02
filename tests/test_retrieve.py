"""Tests for `minerva.retrieve` — query sanitization, score normalization,
filter SQL fragments, and end-to-end search against a small in-memory index."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from minerva import retrieve, store

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


def test_work_filter_for_specific_work():
    sql, params = retrieve._work_filter(792)
    assert sql == " AND cf.work_id = ?"
    assert params == (792,)


def test_work_filter_for_none_returns_no_clause():
    assert retrieve._work_filter(None) == ("", ())


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


def test_format_locator_attributes_apparatus_to_translator():
    """A note/cast locator names the translator/editor, never the author."""
    note_meta = {
        "author": "Plato",
        "work": "Republic",
        "section": "327a",
        "translator": "Plato in Twelve Volumes, Vol. 5 translated by Paul Shorey.",
        "block_type": "note",
    }
    loc = retrieve.format_locator(note_meta)
    assert "Plato," not in loc  # not attributed to the philosopher
    assert "editorial note" in loc
    assert "Paul Shorey" in loc
    assert "Republic 327a" in loc
    # Body prose still attributes to the author.
    body_meta = {"author": "Plato", "work": "Republic", "section": "327a", "block_type": None}
    assert retrieve.format_locator(body_meta).startswith("Plato, Republic 327a")


def test_format_locator_attributes_objection_to_objector():
    """An objection locator names the objector (chunks.speaker) — never
    Descartes, whose work merely hosts the exchange. See
    split_descartes_objections.py."""
    obj_meta = {
        "author": "Descartes",
        "work": "Objections et Réponses",
        "section": "Obj. III, ¶ 3",
        "speaker": "Hobbes",
        "translator": "Clerselier (éd. Cousin)",
        "block_type": "objection",
    }
    loc = retrieve.format_locator(obj_meta)
    assert "Descartes," not in loc
    assert "objection" in loc
    assert "Hobbes" in loc
    assert "Objections et Réponses Obj. III, ¶ 3" in loc
    # Descartes's replies in the same work are his own words — normal
    # author attribution.
    rep_meta = {
        "author": "Descartes",
        "work": "Objections et Réponses",
        "section": "Rép. I, ¶ 2",
        "speaker": None,
        "block_type": None,
    }
    assert retrieve.format_locator(rep_meta).startswith("Descartes, Objections et Réponses")


def test_search_readmits_apparatus_with_attribution(tmp_path: Path):
    """Apparatus is retrievable again (2b), but its citation attributes it to
    the responsible translator/editor — never the philosopher."""

    def chunk(cid: str, text: str, block_type: str | None = None) -> dict:
        return {
            "chunk_id": cid,
            "corpus": "plato",
            "author": "Plato",
            "work": "Republic",
            "lang": "eng",
            "section": "327a",
            "book": "1",
            "page": None,
            "speaker": None,
            "text": text,
            "source_file": "republic_en.xml",
            "translator": "Shorey",
            "edition_year": "1930",
            "block_type": block_type,
        }

    rows = [
        chunk("body1", "The just city mirrors the just soul in its structure and harmony."),
        chunk(
            "note1",
            "Editor's footnote: Socrates narrates this dialogue in the first person.",
            block_type="note",
        ),
        chunk("cast1", "Cast: Socrates, Glaucon, Polemarchus, Thrasymachus.", block_type="cast"),
    ]
    jsonl = tmp_path / "c.jsonl"
    jsonl.write_text("\n".join(json.dumps(r) for r in rows))
    conn = store.open_db(tmp_path / "apparatus.sqlite")
    store.insert_chunks(conn, jsonl)

    # The note IS retrievable again (re-admitted) on a phrase only it carries.
    hits = retrieve.search(conn, "Socrates narrates first person", top_k=5, lang="eng", corpus="plato")
    by_id = {h.chunk_id: h for h in hits}
    assert "note1" in by_id
    # But its citation attributes it to the translator + "editorial note",
    # never to Plato.
    loc = retrieve.format_locator(by_id["note1"].meta)
    assert "editorial note" in loc and "Shorey" in loc and "Plato," not in loc
    # Body text remains attributed to the author.
    body = retrieve.search(conn, "just city just soul harmony", top_k=5, lang="eng", corpus="plato")
    body_hit = {h.chunk_id: h for h in body}["body1"]
    assert retrieve.format_locator(body_hit.meta).startswith("Plato, Republic")


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


# ---------- rare-term lexical reservation ----------


def _seed_reservation_db(tmp_path: Path):
    """Two chunks dense in common words (high BM25 breadth) and one carrying a
    rare term once — the shape that buries a key term in a verbose query."""

    def ch(cid: str, text: str) -> dict:
        return {
            "chunk_id": cid,
            "corpus": "test",
            "author": "Test",
            "work": "Work",
            "lang": "eng",
            "source_file": "f.txt",
            "section": cid,
            "text": text,
        }

    chunks = [
        ch("a", "good good good moral moral moral virtue virtue order order justice"),
        ch("b", "good good moral moral virtue virtue order order justice justice good"),
        ch("c", "A short passage concerning the misbegotten, and also the good."),
    ]
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(tmp_path / "idx.sqlite")
    store.insert_chunks(conn, jsonl)
    return conn


def test_reservation_surfaces_rare_term_over_common_word_breadth(tmp_path: Path):
    conn = _seed_reservation_db(tmp_path)
    # 'misbegotten' (df 1) is the rarest token; a,b outscore c on the repeated
    # common words, but reservation must keep c's passage a seat at top_k=2.
    hits = retrieve.search(
        conn, "good moral virtue misbegotten", top_k=2, lang="eng", min_chunk_chars=0
    )
    assert "c" in {h.chunk_id for h in hits}


def test_reservation_is_noop_without_a_rare_term(tmp_path: Path):
    conn = _seed_reservation_db(tmp_path)
    # No rare outlier: the common-word passages win and c is not forced in.
    hits = retrieve.search(conn, "good moral virtue", top_k=2, lang="eng", min_chunk_chars=0)
    assert {h.chunk_id for h in hits} == {"a", "b"}


def test_reserved_term_ids_picks_rarest_token(tmp_path: Path):
    conn = _seed_reservation_db(tmp_path)
    ids = retrieve._reserved_term_ids(
        conn,
        "good moral misbegotten",
        lang="eng",
        corpus=None,
        speaker=None,
        work_id=None,
        min_chunk_chars=0,
        fold_lang=None,
    )
    assert ids == ["c"]


# ---------- filtered vector search: memoized metadata (no per-request scan) ----------


def _seed_embedded_db(tmp_path: Path):
    conn = _seed_reservation_db(tmp_path)
    store.upsert_embeddings(
        conn,
        model="t",
        dim=3,
        items=[
            ("a", np.array([1.0, 0.0, 0.0], dtype=np.float32)),
            ("b", np.array([0.0, 1.0, 0.0], dtype=np.float32)),
            ("c", np.array([0.0, 0.0, 1.0], dtype=np.float32)),
        ],
    )
    store.invalidate_embedding_cache()
    return conn


def test_filtered_vector_search_does_not_rescan_chunks_full(tmp_path: Path):
    """Regression: every filtered vector search used to SELECT all of
    chunks_full into a dict per request (under corpus_lock). The filter
    columns are now memoized alongside the embedding matrix — after the
    first call, no statement may touch chunks_full."""

    conn = _seed_embedded_db(tmp_path)
    qv = np.array([1.0, 0.2, 0.1], dtype=np.float32)
    retrieve._vector_search(
        conn, qv, top_k=3, lang="eng", corpus=None, speaker=None, min_chunk_chars=1
    )  # warm
    stmts: list[str] = []
    conn.set_trace_callback(stmts.append)
    hits = retrieve._vector_search(
        conn, qv, top_k=3, lang="eng", corpus=None, speaker=None, min_chunk_chars=1
    )
    conn.set_trace_callback(None)
    assert hits
    assert not any("chunks_full" in s for s in stmts)


def test_filtered_vector_search_filters_still_apply(tmp_path: Path):
    conn = _seed_embedded_db(tmp_path)
    qv = np.array([1.0, 0.2, 0.1], dtype=np.float32)
    # Non-matching lang excludes everything.
    assert retrieve._vector_search(conn, qv, top_k=3, lang="deu", corpus=None, speaker=None) == {}
    # Matching lang + corpus returns the full set.
    hits = retrieve._vector_search(conn, qv, top_k=3, lang="eng", corpus="test", speaker=None)
    assert set(hits) == {"a", "b", "c"}
    # min_chunk_chars excludes nothing here (all chunks are > 10 chars).
    hits = retrieve._vector_search(
        conn, qv, top_k=3, lang="eng", corpus=None, speaker=None, min_chunk_chars=10
    )
    assert set(hits) == {"a", "b", "c"}


def test_filtered_vector_search_sees_reingested_metadata(tmp_path: Path):
    """The memoized filter columns must be invalidated together with
    the matrix cache when chunks are rewritten."""

    conn = _seed_embedded_db(tmp_path)
    qv = np.array([1.0, 0.2, 0.1], dtype=np.float32)
    hits = retrieve._vector_search(conn, qv, top_k=3, lang="eng", corpus=None, speaker=None)
    assert set(hits) == {"a", "b", "c"}  # warm cache
    # Rewrite a chunk's lang (what a re-ingest can do) and invalidate,
    # as insert_chunks does. The rebuilt filter columns must see it.
    conn.execute("UPDATE chunks SET lang='deu' WHERE chunk_id='a'")
    conn.commit()
    store.invalidate_embedding_cache(conn)
    hits = retrieve._vector_search(conn, qv, top_k=3, lang="eng", corpus=None, speaker=None)
    assert set(hits) == {"b", "c"}
