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
    # An IN list since #174: the id is resolved to the works.author
    # values it stands for, which for seven corpora is not the id.
    sql, params = retrieve._corpus_filter("plato")
    assert sql == " AND cf.corpus IN (?)"
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


def test_format_locator_does_not_misattribute_signature_lines():
    """A 'signature' chunk is Nietzsche's own draft title/valediction, not
    editorial apparatus (#291) — it must cite him normally, not the
    'editorial note (translator)' form note/cast get."""
    sig_meta = {
        "author": "Nietzsche",
        "work": "Briefe",
        "section": "¶12",
        "translator": "(Original)",
        "block_type": "signature",
    }
    loc = retrieve.format_locator(sig_meta)
    assert loc.startswith("Nietzsche, Briefe")
    assert "editorial" not in loc


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


def test_default_fetch_pool_still_finds_primary_text_past_a_dominant_apparatus_share(
    tmp_path: Path,
):
    """#468: a bare-name query whose candidate pool is otherwise dominated by
    short apparatus/signature-typed chunks must still surface enough primary
    text within `search()`'s DEFAULT fetch_pool for the #165 cap to hold —
    not just when a caller passes a wide `fetch_pool` explicitly. 40 short
    signature lines all outscore 5 much longer body chunks under BM25's
    length normalization (same shape #291 found live: Nietzsche's own
    signature lines outrank his philosophy on a bare-name query)."""

    def sig(cid: str, n: int) -> dict:
        return {
            "chunk_id": cid,
            "corpus": "locke",
            "author": "Locke",
            "work": "Test Work",
            "lang": "eng",
            "section": f"sig{n}",
            "book": None,
            "page": None,
            "speaker": None,
            "text": f"This is a short signature line naming its author, Author, number {n}.",
            "source_file": "x",
            "translator": None,
            "edition_year": None,
            "block_type": "signature",
        }

    def body(cid: str, n: int) -> dict:
        return {
            "chunk_id": cid,
            "corpus": "locke",
            "author": "Locke",
            "work": "Test Work",
            "lang": "eng",
            "section": f"body{n}",
            "book": None,
            "page": None,
            "speaker": None,
            "text": (
                f"Author wrote at considerable length here about a real philosophical "
                f"topic numbered {n}, developing the argument across many clauses and "
                f"sentences so that this passage is substantially longer than a bare "
                f"signature line, the way genuine discursive prose actually reads."
            ),
            "source_file": "x",
            "translator": None,
            "edition_year": None,
            "block_type": None,
        }

    rows = [sig(f"s{i}", i) for i in range(40)] + [body(f"b{i}", i) for i in range(5)]
    jsonl = tmp_path / "c.jsonl"
    jsonl.write_text("\n".join(json.dumps(r) for r in rows))
    conn = store.open_db(tmp_path / "pool.sqlite")
    store.insert_chunks(conn, jsonl)

    # No fetch_pool passed — exercises search()'s own default.
    hits = retrieve.search(conn, "Author", top_k=8, lang="eng")
    n_sig = sum(1 for h in hits if h.meta.get("block_type") == "signature")
    # cap(2) + at most one reserved-term seat (#291's own live measurement:
    # exactly 2/8 at a wide-enough pool, one more when the term is also rare
    # enough to reserve a seat) — never the whole page.
    assert n_sig <= 3


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
    hits = retrieve.search(
        conn, "Socrates narrates first person", top_k=5, lang="eng", corpus="plato"
    )
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
            "corpus": "hume",
            "author": "Hume",
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
    hits = retrieve._vector_search(conn, qv, top_k=3, lang="eng", corpus="hume", speaker=None)
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


# ---------- apparatus share cap (#165) ----------


def _apparatus_conn(rows: list[tuple[str, str | None]]):
    """Minimal `chunks_full` carrying just what the cap consults."""

    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE chunks_full (chunk_id TEXT PRIMARY KEY, block_type TEXT)")
    conn.executemany("INSERT INTO chunks_full VALUES (?, ?)", rows)
    return conn


def test_apparatus_may_not_take_more_than_a_third():
    # Six notes ahead of the text is exactly the divided-line case: the
    # Republic's notes outnumber its English text 2:1 and are shorter,
    # which both halves of retrieval reward.
    ordered = [f"n{i}" for i in range(6)] + ["t0", "t1", "t2", "t3"]
    conn = _apparatus_conn(
        [(f"n{i}", "note") for i in range(6)] + [(f"t{i}", None) for i in range(4)]
    )
    got = retrieve._cap_apparatus(conn, ordered, top_k=6)
    assert len(got) == 6
    assert sum(1 for c in got if c.startswith("n")) == 2  # 6 // 3
    # The primary text that was buried is now present, in score order.
    assert got == ["n0", "n1", "t0", "t1", "t2", "t3"]


def test_cap_keeps_the_highest_scoring_apparatus():
    # Order is never reshuffled — the notes that survive are the two the
    # ranking liked best, not an arbitrary pair.
    ordered = ["n0", "t0", "n1", "n2", "t1"]
    conn = _apparatus_conn(
        [("n0", "note"), ("n1", "note"), ("n2", "cast"), ("t0", None), ("t1", None)]
    )
    assert retrieve._cap_apparatus(conn, ordered, top_k=3) == ["n0", "t0", "t1"]


def test_cast_lists_count_as_apparatus():
    # Dramatis-personae lists are apparatus too. top_k=3 allows one, so
    # the text is reached, and the leftover slot is backfilled from the
    # deferred casts rather than left empty.
    ordered = ["c0", "c1", "c2", "t0"]
    conn = _apparatus_conn([(f"c{i}", "cast") for i in range(3)] + [("t0", None)])
    assert retrieve._cap_apparatus(conn, ordered, top_k=3) == ["c0", "t0", "c1"]


def test_all_apparatus_pool_still_fills_the_page():
    # A question genuinely about a footnote, or a work that is mostly
    # apparatus, must not come back short — the deferred notes are given
    # their slots back rather than dropped.
    ordered = [f"n{i}" for i in range(5)]
    conn = _apparatus_conn([(f"n{i}", "note") for i in range(5)])
    assert retrieve._cap_apparatus(conn, ordered, top_k=4) == ["n0", "n1", "n2", "n3"]


def test_no_apparatus_is_untouched():
    ordered = ["t0", "t1", "t2"]
    conn = _apparatus_conn([(f"t{i}", None) for i in range(3)])
    assert retrieve._cap_apparatus(conn, ordered, top_k=2) == ["t0", "t1"]


def test_cap_is_at_least_one_for_small_top_k():
    # top_k=2 would floor to 0 slots; apparatus stays reachable.
    ordered = ["n0", "t0"]
    conn = _apparatus_conn([("n0", "note"), ("t0", None)])
    assert retrieve._cap_apparatus(conn, ordered, top_k=2) == ["n0", "t0"]


def test_apparatus_beyond_the_top_k_window_is_still_counted():
    # Regression: looking up block_type for only a prefix of the
    # candidates made a note further down read as primary text and take
    # a slot reserved for the philosopher's own words.
    ordered = ["t0"] + [f"n{i}" for i in range(30)]
    conn = _apparatus_conn([("t0", None)] + [(f"n{i}", "note") for i in range(30)])
    got = retrieve._cap_apparatus(conn, ordered, top_k=3)
    assert got[0] == "t0"
    assert sum(1 for c in got if c.startswith("n")) <= 2


def test_signature_lines_count_toward_the_apparatus_cap():
    # #291: Nachlass title-page drafts and Briefe valedictions are typed
    # block_type='signature'. They're the author's own words, unlike
    # note/cast, but must still be capped — a signature line is what
    # outranked Nietzsche's actual philosophy on a query containing his
    # name in the first place.
    ordered = [f"s{i}" for i in range(6)] + ["t0", "t1", "t2", "t3"]
    conn = _apparatus_conn(
        [(f"s{i}", "signature") for i in range(6)] + [(f"t{i}", None) for i in range(4)]
    )
    got = retrieve._cap_apparatus(conn, ordered, top_k=6)
    assert sum(1 for c in got if c.startswith("s")) == 2  # 6 // 3
    assert got == ["s0", "s1", "t0", "t1", "t2", "t3"]


# ---------- deterministic ranking (#165) ----------


def test_rank_ids_breaks_ties_on_chunk_id():
    # Insertion order is deliberately not score order: `fused` is seeded
    # from a set union whose iteration order is hash-randomised, so the
    # result must not depend on it.
    fused = {"zz": 1.0, "aa": 1.0, "mm": 2.0, "bb": 0.5}
    assert retrieve._rank_ids(fused, fused) == ["mm", "aa", "zz", "bb"]


def test_rank_ids_is_insertion_order_independent():
    scores = {"a": 1.0, "b": 1.0, "c": 1.0}
    shuffled = {"c": 1.0, "a": 1.0, "b": 1.0}
    assert retrieve._rank_ids(scores, scores) == retrieve._rank_ids(shuffled, shuffled)


def test_rank_ids_handles_ids_missing_from_fused():
    # The reserved-seat path ranks a set that can include ids the fusion
    # never scored; they sort last rather than raising.
    fused = {"a": 2.0}
    assert retrieve._rank_ids({"a", "b"}, fused) == ["a", "b"]


def _seed_apparatus_reservation_db(tmp_path: Path):
    """As above, but the rare term appears only in editorial notes — the
    shape that let reserved seats smuggle apparatus past the cap."""

    def ch(cid: str, text: str, block_type: str | None = None) -> dict:
        row = {
            "chunk_id": cid,
            "corpus": "hume",
            "author": "Hume",
            "work": "Work",
            "lang": "eng",
            "source_file": "f.txt",
            "section": cid,
            "text": text,
        }
        if block_type:
            row["block_type"] = block_type
        return row

    # `misbegotten` is unique to n1, so it is unambiguously the rarest
    # token and the reserved seat goes to a note. n2/n3 are dense in the
    # query's common words, so they compete for the ranked slots too —
    # which is what the cap has to hold back.
    chunks = [
        ch("t1", "good good moral moral virtue virtue order order justice justice good"),
        ch("t2", "good good good moral moral moral virtue virtue order order justice"),
        ch("t3", "good moral virtue order justice and the good life considered again"),
        ch("n1", "A note on the misbegotten passage, and also the good.", "note"),
        ch("n2", "A note: good good moral moral virtue virtue order justice good.", "note"),
        ch("n3", "A note: good moral moral virtue virtue virtue order order good.", "note"),
    ]
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(tmp_path / "idx.sqlite")
    store.insert_chunks(conn, jsonl)
    return conn


def test_reserved_seats_cannot_smuggle_apparatus_past_the_cap(tmp_path: Path):
    """Regression: the cap ran *before* the reserved-seat merge, and the
    rarest term in a question is often rarest precisely because only a
    footnote uses it — so the merge reinstated the notes the cap had
    just excluded. Measured on the real index this returned 3 notes in a
    top-6 whose cap was 2."""

    conn = _seed_apparatus_reservation_db(tmp_path)
    hits = retrieve.search(
        conn, "good moral virtue misbegotten", top_k=3, lang="eng", min_chunk_chars=0
    )
    notes = [h for h in hits if h.meta.get("block_type") == "note"]
    assert len(notes) <= 1  # max(1, 3 // 3)
    # The reservation still did its job: the rare term is represented.
    assert notes, "the rare term's only carrier must still get its seat"


# ---------- corpus filter resolves ids to authors (#174) ----------


def test_corpus_filter_binds_the_author_not_the_id():
    sql, params = retrieve._corpus_filter("marcus_aurelius")
    assert sql == " AND cf.corpus IN (?)"
    # `chunks_full.corpus` is LOWER(works.author); the id matched nothing.
    assert params == ("marcus aurelius",)


def test_corpus_filter_expands_a_multi_author_corpus():
    sql, params = retrieve._corpus_filter("presocratic")
    assert sql.startswith(" AND cf.corpus IN (?")
    assert sql.count("?") == len(params) > 1
    assert "heraclitus" in params


def test_corpus_filter_single_author_corpus_unchanged():
    sql, params = retrieve._corpus_filter("plato")
    assert sql == " AND cf.corpus IN (?)"
    assert params == ("plato",)


# ---------- the length floor exempts verse-addressed works (#268) ----------


def _seed_verse_db(tmp_path: Path):
    """Short chunks on both sides of the exemption.

    `citation_system` rides the JSONL row (`store.chunks` honors it as a
    `citation_system_override` when the works row is created), so the two
    works differ in exactly the field the exemption reads. The German verse
    lands as a `translations` row rather than an `editions` one — corpus
    `hume` has original_language `eng`, and `_resolve_work_refs` classifies
    on `lang == works.original_language` — which is what makes the
    translation half of `_min_chars_filter` load-bearing here.
    """

    def ch(cid: str, work: str, lang: str, text: str, citation_system: str) -> dict:
        return {
            "chunk_id": cid,
            "corpus": "hume",
            "author": "Scripture" if citation_system == "bcv" else "Prose",
            "work": work,
            "lang": lang,
            "source_file": "f.txt",
            "section": cid,
            "text": text,
            "citation_system": citation_system,
        }

    chunks = [
        # 24 chars: John 10:30 in the Vulgate, one of the two verses #268
        # names as unreachable.
        ch("verse_ed", "Gospel", "eng", "Ego et Pater unum sumus.", "bcv"),
        ch("verse_tr", "Gospel", "deu", "Ich und der Vater sind eins.", "bcv"),
        # 30 chars of paragraph-addressed correspondence: the signature
        # class the floor was written against. Must stay filtered.
        ch("sig", "Letters", "eng", "Ever yours, Ego Pater sumus.", "paragraph"),
        ch(
            "body",
            "Letters",
            "eng",
            "A long paragraph of prose that comfortably clears the sixty-character "
            "floor and mentions Ego and Pater and sumus so BM25 can match it.",
            "paragraph",
        ),
    ]
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(tmp_path / "idx.sqlite")
    store.insert_chunks(conn, jsonl)
    return conn


def test_min_chars_filter_disabled_returns_no_clause():
    assert retrieve._min_chars_filter(0) == ("", ())
    assert retrieve._min_chars_filter(-1) == ("", ())


def test_min_chars_filter_exempts_both_edition_and_translation_columns():
    """A predicate on one column alone exempts only half the scripture:
    the Vulgate, KJV and Luther are `editions` rows today, while nothing
    stops the next scripture ingest from landing as a `translations` one."""

    sql, params = retrieve._min_chars_filter(60)
    assert sql.startswith(" AND (length(chunks.text) >= ?")
    assert "chunks.edition_id IN" in sql
    assert "chunks.translation_id IN" in sql
    assert params == (60, "bcv", "surah_ayah", "bcv", "surah_ayah")


def test_verse_work_ids_lists_only_verse_addressed_works(tmp_path: Path):
    conn = _seed_verse_db(tmp_path)
    ids = set(retrieve._verse_work_ids(conn).tolist())
    titles = {
        r[0]
        for r in conn.execute(
            f"SELECT title FROM works WHERE id IN ({','.join('?' * len(ids))})", tuple(ids)
        )
    }
    assert titles == {"Gospel"}


def test_short_verse_is_retrievable_despite_the_floor(tmp_path: Path):
    """#268: at the default floor the verse was not merely down-ranked,
    it was absent — no query could reach it."""

    conn = _seed_verse_db(tmp_path)
    hits = retrieve.search(conn, "Ego et Pater unum sumus", lang="eng", top_k=8)
    assert "verse_ed" in {h.chunk_id for h in hits}


def test_short_verse_on_the_translation_side_is_retrievable(tmp_path: Path):
    conn = _seed_verse_db(tmp_path)
    hits = retrieve.search(conn, "Ich und der Vater sind eins", lang="deu", top_k=8)
    assert "verse_tr" in {h.chunk_id for h in hits}


def test_short_paragraph_chunk_stays_filtered(tmp_path: Path):
    """The floor's own rationale survives: a 30-character signature in a
    paragraph-addressed work is still excluded, and only reachable with
    the floor explicitly disabled."""

    conn = _seed_verse_db(tmp_path)
    hits = retrieve.search(conn, "Ever yours Ego Pater sumus", lang="eng", top_k=8)
    assert "sig" not in {h.chunk_id for h in hits}
    unfiltered = retrieve.search(
        conn, "Ever yours Ego Pater sumus", lang="eng", top_k=8, min_chunk_chars=0
    )
    assert "sig" in {h.chunk_id for h in unfiltered}


def test_reserved_seats_can_reserve_a_short_verse(tmp_path: Path):
    """The reservation path passes the floor through to `_fts_match`, so it
    inherits the exemption — confirmed rather than assumed, since a term
    rare enough to earn a seat is often carried only by a short verse."""

    conn = _seed_verse_db(tmp_path)
    ids = retrieve._reserved_term_ids(
        conn,
        "unum",
        lang="eng",
        corpus=None,
        speaker=None,
        work_id=None,
        min_chunk_chars=60,
        fold_lang=None,
    )
    assert "verse_ed" in ids


def test_vector_search_exempts_verse_works_from_the_floor(tmp_path: Path):
    """Both halves of hybrid retrieval must agree about which chunks
    exist; the numpy filter reads the same citation systems as the SQL."""

    conn = _seed_verse_db(tmp_path)
    store.upsert_embeddings(
        conn,
        model="t",
        dim=2,
        items=[
            ("verse_ed", np.array([1.0, 0.0], dtype=np.float32)),
            ("sig", np.array([1.0, 0.0], dtype=np.float32)),
            ("body", np.array([0.0, 1.0], dtype=np.float32)),
        ],
    )
    store.invalidate_embedding_cache()
    qv = np.array([1.0, 0.0], dtype=np.float32)
    hits = retrieve._vector_search(
        conn, qv, top_k=3, lang="eng", corpus=None, speaker=None, min_chunk_chars=60
    )
    assert "verse_ed" in hits  # 24 chars, exempt
    assert "sig" not in hits  # 28 chars, paragraph-addressed


def test_editorial_apparatus_is_capped_like_notes():
    """An editors' introduction may not crowd out the author (#534).

    Same policy as notes and cast lists: apparatus supports the text, so it
    takes at most `_APPARATUS_MAX_SHARE` of a result set.
    """
    assert "editorial" in retrieve._APPARATUS_TYPES
    assert "editorial" in retrieve._CAPPED_TYPES


def test_spurious_fragment_is_capped_and_not_cited_as_the_author():
    """DK's doubtful and forged fragments are kept but are not the
    author's words (#683): capped like apparatus, and cited as what they
    are rather than as `Empedocles, Fragments …`."""
    assert "spurious" in retrieve._CAPPED_TYPES
    meta = {
        "author": "Empedocles",
        "work": "Fragments (DK 31)",
        "section": "31 B 155",
        "block_type": "spurious",
        "translator": "(Original)",
    }
    loc = retrieve.format_locator(meta)
    assert loc == "Fragments (DK 31) 31 B 155 — doubtful or spurious fragment"
    loc = retrieve.format_locator({**meta, "translator": "Hermann Diels"})
    assert loc == "Fragments (DK 31) 31 B 155 — doubtful or spurious fragment (Hermann Diels)"


def test_apparatus_of_an_original_edition_names_no_translator():
    # The grc edition's translator field is the placeholder `(Original)`;
    # it used to print as `editorial apparatus ((Original))`.
    loc = retrieve.format_locator(
        {
            "work": "Fragments (DK 31)",
            "section": "31 B 98",
            "block_type": "editorial",
            "translator": "(Original)",
        }
    )
    assert loc == "Fragments (DK 31) 31 B 98 — editorial apparatus"


def test_editorial_locator_names_the_editor_not_the_author():
    loc = retrieve.format_locator(
        {
            "author": "Hegel",
            "work": "Lectures on the Philosophy of World History",
            "section": "Editorial Introduction, ¶1",
            "block_type": "editorial",
            "translator": "Hodgson / Brown",
        }
    )
    # `_APPARATUS_LABEL.get(block_type, "editorial")` falls back to the bare
    # word "editorial" for an UNKNOWN block_type too, so `"editorial" in
    # loc.lower()` can't fail whether or not the explicit dict entry
    # exists. Assert the full label text, which only the explicit
    # "editorial" -> "editorial apparatus" entry produces.
    assert "editorial apparatus" in loc
    assert "Hodgson" in loc
