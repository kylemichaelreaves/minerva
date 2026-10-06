"""Tests for the concordance read queries — lemma_index + lemma_detail.

Focused on the F1 filter-bar additions (``q``, ``max_count``) and the
existing filters they interact with (``letter``, ``pos_in``, ``min_count``).
Builds a small in-memory corpus + lemma cache so the SQL paths run
against real SQLite (no mocks).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from conftest import make_chunk  # type: ignore[import-not-found]

from minerva import store
from minerva.concordance import index_queries
from minerva.concordance import queries as concordance_queries
from minerva.errors import BadRequestError

# ──────────────────────────────────────────────────────────────────
#  Fixtures
# ──────────────────────────────────────────────────────────────────


def _insert_lemma(
    conn: sqlite3.Connection,
    *,
    chunk_id: str,
    token_index: int,
    surface: str,
    lemma: str,
    pos: str,
    feats: str = "",
) -> None:
    """Seed one chunk_lemmas row. Mirrors the writer in
    ``minerva.lemmatize`` minus the spaCy/Stanza machinery."""

    conn.execute(
        """
        INSERT INTO chunk_lemmas
            (chunk_id, token_index, surface_form, surface_start, surface_end,
             lemma, lemma_fold, pos, feats)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk_id,
            token_index,
            surface,
            token_index * 10,
            token_index * 10 + len(surface),
            lemma,
            lemma.lower(),
            pos,
            feats,
        ),
    )


@pytest.fixture
def concordance_db(tmp_path: Path) -> sqlite3.Connection:
    """SQLite store with three German chunks + a hand-seeded lemma cache.

    The lemmas are chosen so each test can exercise one axis cleanly:

      * "Geist"  appears 4 times (varies pos to stress the POS filter)
      * "geistig" appears 2 times (substring match for ``q=geist``)
      * "haben"  appears 6 times (high-frequency control)
      * "fragen" appears 1 time  (drops below the default min_count=2)
    """

    # Chunks live in the corpus; the JSONL → store.insert_chunks path
    # mirrors what `minerva ingest` would have produced.
    chunks = [
        make_chunk(
            chunk_id="phdg-1",
            corpus="hegel",
            author="Hegel",
            work="Phänomenologie des Geistes",
            lang="deu",
            section="Vorrede",
            text="Geist der Geist Geist haben geistig",
        ),
        make_chunk(
            chunk_id="phdg-2",
            corpus="hegel",
            author="Hegel",
            work="Phänomenologie des Geistes",
            lang="deu",
            section="A",
            text="Geist geistig haben haben haben",
        ),
        make_chunk(
            chunk_id="phdg-3",
            corpus="hegel",
            author="Hegel",
            work="Phänomenologie des Geistes",
            lang="deu",
            section="B",
            text="haben haben fragen",
        ),
    ]
    import json

    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(tmp_path / "conc.sqlite")
    store.insert_chunks(conn, jsonl)

    seed = [
        # phdg-1: Geist×3, haben×1, geistig×1
        ("phdg-1", 0, "Geist", "Geist", "NOUN", "Case=Nom|Number=Sing|Gender=Masc"),
        ("phdg-1", 1, "Geist", "Geist", "NOUN", "Case=Acc|Number=Sing|Gender=Masc"),
        ("phdg-1", 2, "Geist", "Geist", "NOUN", "Case=Nom|Number=Sing|Gender=Masc"),
        ("phdg-1", 3, "haben", "haben", "VERB", ""),
        ("phdg-1", 4, "geistig", "geistig", "ADJ", ""),
        # phdg-2: Geist×1, geistig×1, haben×3
        ("phdg-2", 0, "Geist", "Geist", "NOUN", "Case=Nom|Number=Sing|Gender=Masc"),
        ("phdg-2", 1, "geistig", "geistig", "ADJ", ""),
        ("phdg-2", 2, "haben", "haben", "VERB", ""),
        ("phdg-2", 3, "haben", "haben", "VERB", ""),
        ("phdg-2", 4, "haben", "haben", "VERB", ""),
        # phdg-3: haben×2, fragen×1
        ("phdg-3", 0, "haben", "haben", "VERB", ""),
        ("phdg-3", 1, "haben", "haben", "VERB", ""),
        ("phdg-3", 2, "fragen", "fragen", "VERB", ""),
    ]
    for chunk_id, idx, surface, lemma, pos, feats in seed:
        _insert_lemma(
            conn,
            chunk_id=chunk_id,
            token_index=idx,
            surface=surface,
            lemma=lemma,
            pos=pos,
            feats=feats,
        )
    conn.commit()
    # The concordance read path queries ``lemma_counts`` (the
    # materialized aggregate, populated post-lemmatize in production).
    # Build it here so the tests exercise the real read path.
    from minerva.concordance import aggregate

    aggregate.build(conn)
    return conn


@pytest.fixture
def tie_concordance_db(tmp_path: Path) -> sqlite3.Connection:
    """A store whose rows TIE on the whole ``freq`` sort key.

    ``recht`` is seeded twice with the same count under two different parts of
    speech, so the two groups agree on ``(n, lemma_key)`` and differ only in
    ``pos`` — which is in the GROUP BY but was not in the ORDER BY. That makes
    the sort a partial order, and ``LIMIT/OFFSET`` over a partial order may put
    the same row on two pages and no page at all for its partner.

    Measured on the live index: 805 groups in the German corpus partition tie on
    the full sort key this way. No page boundary has been caught mis-serving one
    — this is the invariant, held on principle, rather than a reproduction.
    """

    chunks = [
        make_chunk(
            chunk_id="tie-1",
            corpus="hegel",
            author="Hegel",
            work="Phänomenologie des Geistes",
            lang="deu",
            section="A",
            text="recht recht recht recht Sache Sache Ding",
        ),
    ]
    import json

    jsonl = tmp_path / "tie_chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(tmp_path / "tie_conc.sqlite")
    store.insert_chunks(conn, jsonl)

    seed = [
        # `recht` twice as ADJ and twice as VERB — same lemma_key, same count.
        ("tie-1", 0, "recht", "recht", "ADJ", ""),
        ("tie-1", 1, "recht", "recht", "ADJ", ""),
        ("tie-1", 2, "recht", "recht", "VERB", ""),
        ("tie-1", 3, "recht", "recht", "VERB", ""),
        # Two more rows so a limit=1 walk has several pages to get wrong.
        ("tie-1", 4, "Sache", "Sache", "NOUN", ""),
        ("tie-1", 5, "Sache", "Sache", "NOUN", ""),
        ("tie-1", 6, "Ding", "Ding", "NOUN", ""),
    ]
    for chunk_id, idx, surface, lemma, pos, feats in seed:
        _insert_lemma(
            conn,
            chunk_id=chunk_id,
            token_index=idx,
            surface=surface,
            lemma=lemma,
            pos=pos,
            feats=feats,
        )
    conn.commit()
    from minerva.concordance import aggregate

    aggregate.build(conn)
    return conn


@pytest.fixture
def greek_concordance_db(tmp_path: Path) -> sqlite3.Connection:
    """SQLite store with one Greek chunk + polytonic lemma cache.

    The seeded lemmas all share the *base* leading letter alpha but
    carry different precomposed diacritics / case so the diacritic-fold
    letter filter has something to prove:

      * ἄνθρωπος — smooth + acute (ἄ)
      * ἀγαθός   — smooth breathing (ἀ)
      * Ἀθηνᾶ    — capital + smooth (Ἀ)
      * λόγος    — control, leading λ → must NOT match letter=Α

    Two of the seeds exist for ``merge_case`` rather than for the letter
    filter, and the fixture could not tell the two group keys apart
    without them (#366):

      * ἀρχή  NOUN — shares its folded initial *and* its POS with
        ἄνθρωπος, so a first-character group key merges them and a
        whole-lemma key does not. Every other lemma here has a unique
        (initial, pos) pair, which is exactly why the defect survived.
      * Λόγος NOUN — a capitalised variant of λόγος, so the fix cannot
        be "stop merging"; what ``merge_case`` exists for must still
        happen.
    """

    chunks = [
        make_chunk(
            chunk_id="rep-1",
            corpus="plato",
            author="Plato",
            work="Respublica",
            lang="grc",
            section="327a",
            text=("ἄνθρωπος ἄνθρωπος ἀγαθός ἀγαθός Ἀθηνᾶ Ἀθηνᾶ λόγος λόγος ἀρχή ἀρχή Λόγος"),
        ),
    ]
    import json

    jsonl = tmp_path / "grc_chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(tmp_path / "grc_conc.sqlite")
    store.insert_chunks(conn, jsonl)

    seed = [
        ("rep-1", 0, "ἄνθρωπος", "ἄνθρωπος", "NOUN", "Case=Nom|Number=Sing|Gender=Masc"),
        ("rep-1", 1, "ἄνθρωποι", "ἄνθρωπος", "NOUN", "Case=Nom|Number=Plur|Gender=Masc"),
        ("rep-1", 2, "ἀγαθός", "ἀγαθός", "ADJ", "Case=Nom|Number=Sing|Gender=Masc"),
        ("rep-1", 3, "ἀγαθοῖν", "ἀγαθός", "ADJ", "Case=Dat|Number=Dual|Gender=Masc"),
        ("rep-1", 4, "Ἀθηνᾶ", "Ἀθηνᾶ", "PROPN", "Case=Nom|Number=Sing|Gender=Fem"),
        ("rep-1", 5, "Ἀθηνᾶν", "Ἀθηνᾶ", "PROPN", "Case=Acc|Number=Sing|Gender=Fem"),
        ("rep-1", 6, "λόγος", "λόγος", "NOUN", "Case=Nom|Number=Sing|Gender=Masc"),
        ("rep-1", 7, "λόγον", "λόγος", "NOUN", "Case=Acc|Number=Sing|Gender=Masc"),
        ("rep-1", 8, "ἀρχή", "ἀρχή", "NOUN", "Case=Nom|Number=Sing|Gender=Fem"),
        ("rep-1", 9, "ἀρχῆς", "ἀρχή", "NOUN", "Case=Gen|Number=Sing|Gender=Fem"),
        ("rep-1", 10, "Λόγος", "Λόγος", "NOUN", "Case=Nom|Number=Sing|Gender=Masc"),
    ]
    for chunk_id, idx, surface, lemma, pos, feats in seed:
        _insert_lemma(
            conn,
            chunk_id=chunk_id,
            token_index=idx,
            surface=surface,
            lemma=lemma,
            pos=pos,
            feats=feats,
        )
    conn.commit()
    from minerva.concordance import aggregate

    aggregate.build(conn)
    return conn


# ──────────────────────────────────────────────────────────────────
#  Greek diacritic-folded letter filter
# ──────────────────────────────────────────────────────────────────


def test_greek_letter_folds_diacritics(
    greek_concordance_db: sqlite3.Connection,
) -> None:
    """``letter=Α`` for Greek matches lemmas whose first character folds
    to alpha regardless of breathing/accent/case (ἄ, ἀ, Ἀ) and excludes
    the λ-initial control. The Latin ``LIKE 'Α%'`` path would miss the
    precomposed forms entirely."""

    out = concordance_queries.lemma_index(
        greek_concordance_db,
        {"lang": "grc", "letter": "Α", "min_count": "1"},
    )
    lemmas = {r["lemma"] for r in out["rows"]}
    assert lemmas == {"ἄνθρωπος", "ἀγαθός", "Ἀθηνᾶ", "ἀρχή"}
    assert "λόγος" not in lemmas
    assert out["total_lemmas"] == 4


def test_greek_letter_lowercase_request_folds_too(
    greek_concordance_db: sqlite3.Connection,
) -> None:
    """A lowercase ``letter=α`` request folds the same way as ``Α`` — the
    rail emits capitals but a stale/bookmarked lowercase value must not
    silently zero the leaderboard."""

    lo = concordance_queries.lemma_index(
        greek_concordance_db,
        {"lang": "grc", "letter": "α", "min_count": "1"},
    )
    hi = concordance_queries.lemma_index(
        greek_concordance_db,
        {"lang": "grc", "letter": "Α", "min_count": "1"},
    )
    assert {r["lemma"] for r in lo["rows"]} == {r["lemma"] for r in hi["rows"]}


def test_greek_merge_case_keeps_lemmas_that_share_an_initial_apart(
    greek_concordance_db: sqlite3.Connection,
) -> None:
    """``merge_case`` groups whole lemmas, not leading letters (#366).

    ``ἄνθρωπος`` and ``ἀρχή`` are both NOUNs whose initial folds to Α.
    Grouping on ``fold_initial(lemma)`` made them one row, summing their
    counts under whichever label sorted first — on the live index that
    merged ``στηλογραφία`` into ``συλλογισμός`` and reported 65 Greek
    lemmas where there were 522."""

    out = concordance_queries.lemma_index(
        greek_concordance_db,
        {"lang": "grc", "merge_case": "1", "min_count": "1"},
    )
    by_lemma = {(r["lemma"], r["pos"]): r for r in out["rows"]}

    assert ("ἄνθρωπος", "NOUN") in by_lemma
    assert ("ἀρχή", "NOUN") in by_lemma
    assert by_lemma[("ἄνθρωπος", "NOUN")]["count"] == 2
    assert by_lemma[("ἀρχή", "NOUN")]["count"] == 2
    # Neither row may carry the other as a merged variant.
    assert by_lemma[("ἄνθρωπος", "NOUN")]["variants"] == ["ἄνθρωπος"]
    assert by_lemma[("ἀρχή", "NOUN")]["variants"] == ["ἀρχή"]


def test_greek_merge_case_still_merges_case_variants(
    greek_concordance_db: sqlite3.Connection,
) -> None:
    """The fix for #366 must not disable what ``merge_case`` is for.

    ``λόγος`` and ``Λόγος`` are one lemma in two typographic dresses and
    still belong in one row, with their counts summed."""

    out = concordance_queries.lemma_index(
        greek_concordance_db,
        {"lang": "grc", "merge_case": "1", "min_count": "1"},
    )
    logos = [r for r in out["rows"] if r["lemma"].lower() == "λόγος"]

    assert len(logos) == 1, f"λόγος/Λόγος did not merge: {logos}"
    assert logos[0]["count"] == 3
    assert sorted(logos[0]["variants"]) == ["Λόγος", "λόγος"]


def test_greek_letter_lambda_only(
    greek_concordance_db: sqlite3.Connection,
) -> None:
    """``letter=Λ`` isolates the λ-initial lemma and excludes the
    alpha cluster — the fold doesn't over-match."""

    out = concordance_queries.lemma_index(
        greek_concordance_db,
        {"lang": "grc", "letter": "Λ", "min_count": "1"},
    )
    assert {r["lemma"] for r in out["rows"]} == {"λόγος"}


# ──────────────────────────────────────────────────────────────────
#  letter is a LIKE prefix — SQL wildcards must not leak through
# ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("wildcard", ["%", "_"])
def test_letter_wildcards_do_not_bypass_the_filter(
    concordance_db: sqlite3.Connection,
    wildcard: str,
) -> None:
    """``letter`` is interpolated into a ``LIKE`` pattern. An unescaped
    ``%`` matched every lemma in the index and ``_`` every lemma of
    length >= 1, while the response still echoed the requested letter
    as though it had applied (#120).

    No seeded lemma starts with a literal ``%`` or ``_``, so a correctly
    escaped filter returns nothing.
    """

    out = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "letter": wildcard, "min_count": "1"},
    )

    assert out["rows"] == []
    assert out["total_lemmas"] == 0


def test_letter_prefix_still_matches(concordance_db: sqlite3.Connection) -> None:
    """Guard the fix: escaping wildcards must not break ordinary
    prefix matching."""

    out = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "letter": "g", "min_count": "1"},
    )

    assert {r["lemma"] for r in out["rows"]} == {"Geist", "geistig"}


def test_letter_backslash_is_literal(concordance_db: sqlite3.Connection) -> None:
    """A backslash must stay a literal, not consume the next character
    as an escape — the `ESCAPE '\\'` clause makes this load-bearing."""

    out = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "letter": "\\", "min_count": "1"},
    )

    assert out["rows"] == []


def test_morph_filter_wildcards_do_not_bypass_the_filter(
    concordance_db: sqlite3.Connection,
) -> None:
    """KWIC morph filters are matched as ``feats LIKE '%Key=Val%'``.
    ``morph`` comes off the query string with only a ``Key=Val`` shape
    check — no value whitelist — so an unescaped ``%`` turned
    ``Case=Nom`` into "any row with a Case feature" (#120).

    ``Case=Nom`` matches 3 of the 4 Geist occurrences; ``Case=%`` must
    match none, not all 4.
    """

    nom = concordance_queries.lemma_detail(
        concordance_db,
        {"lemma": "Geist", "lang": "deu", "morph": "Case=Nom"},
    )
    assert nom["total"] == 3

    wild = concordance_queries.lemma_detail(
        concordance_db,
        {"lemma": "Geist", "lang": "deu", "morph": "Case=%"},
    )
    assert wild["total"] == 0


def test_unknown_morph_feature_key_is_a_400_not_zero_rows(
    concordance_db: sqlite3.Connection,
) -> None:
    """A misspelt feature *key* must 400 rather than quietly return nothing.

    #120 escaped the key and value, which stopped ``Case=%`` widening the
    filter, but left every unknown key indistinguishable from a genuinely
    absent form: ``Casee=Nom`` (typo) and ``Case=Nomm`` (no such value)
    both returned zero rows, and so does "this lemma really has no
    nominative". A client bug and real data looked identical (#160).

    Only the key is validated. Values stay open-ended — they vary too much
    per language to whitelist.
    """

    with pytest.raises(BadRequestError) as exc:
        concordance_queries.lemma_detail(
            concordance_db,
            {"lemma": "Geist", "lang": "deu", "morph": "Casee=Nom"},
        )
    assert "Casee" in str(exc.value)

    # An unknown *value* on a known key is still a legitimate query that
    # happens to match nothing — it must NOT raise.
    empty = concordance_queries.lemma_detail(
        concordance_db,
        {"lemma": "Geist", "lang": "deu", "morph": "Case=Nomm"},
    )
    assert empty["total"] == 0


def test_morph_accepts_non_ud_keys_the_lemmatizers_actually_emit(
    concordance_db: sqlite3.Connection,
) -> None:
    """The whitelist is derived from the corpus, not the UD spec.

    ``HebBinyan`` (Hebrew Stanza) and ``ConjType`` / ``VerbType`` /
    ``AdpType`` (LatinCy) are absent from textbook UD feature tables but
    account for ~555k rows of ``chunk_lemmas.feats``. Validating against
    the spec instead of the data would 400 on real corpus features.

    These match no fixture rows, so the assertion is that they are
    *accepted* — zero results, not a BadRequestError.
    """

    for key in ("HebBinyan", "ConjType", "VerbType", "AdpType"):
        out = concordance_queries.lemma_detail(
            concordance_db,
            {"lemma": "Geist", "lang": "deu", "morph": f"{key}=Xyz"},
        )
        assert out["total"] == 0, f"{key} should be accepted, not rejected"


# ──────────────────────────────────────────────────────────────────
#  q (lemma substring search)
# ──────────────────────────────────────────────────────────────────


def test_q_substring_match(concordance_db: sqlite3.Connection) -> None:
    """``q=geist`` matches both ``Geist`` and ``geistig`` (case-insensitive,
    substring). Surfaces in the rows; total_lemmas reflects the narrowed set."""

    out = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "q": "geist"},
    )
    lemmas = {r["lemma"] for r in out["rows"]}
    assert lemmas == {"Geist", "geistig"}
    assert out["total_lemmas"] == 2


def test_q_case_insensitive(concordance_db: sqlite3.Connection) -> None:
    """A capitalised query string narrows the same way as lowercase."""

    lo = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "q": "geist"},
    )
    hi = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "q": "GEIST"},
    )
    assert {r["lemma"] for r in lo["rows"]} == {r["lemma"] for r in hi["rows"]}


def test_q_wildcards_are_escaped(concordance_db: sqlite3.Connection) -> None:
    """A literal ``%`` or ``_`` in the query must not act as a SQL LIKE
    wildcard — otherwise ``q=%`` would match every lemma."""

    out = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "q": "%"},
    )
    assert out["rows"] == []
    assert out["total_lemmas"] == 0

    # Same for underscore — there's no underscore in any seeded lemma.
    out_underscore = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "q": "_"},
    )
    assert out_underscore["rows"] == []


def test_q_empty_string_is_ignored(concordance_db: sqlite3.Connection) -> None:
    """A blank ``q`` (after strip) must NOT narrow — otherwise a
    cleared search field would return zero results until the user
    explicitly removed the param."""

    no_q = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu"},
    )
    blank = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "q": "   "},
    )
    assert no_q["total_lemmas"] == blank["total_lemmas"]


# ──────────────────────────────────────────────────────────────────
#  max_count (upper edge of the freq-range slider)
# ──────────────────────────────────────────────────────────────────


def test_max_count_caps_freq(concordance_db: sqlite3.Connection) -> None:
    """``max_count=4`` drops haben (count=6) but keeps Geist (count=4)
    and geistig (count=2)."""

    out = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "max_count": "4"},
    )
    lemmas = {r["lemma"] for r in out["rows"]}
    assert "haben" not in lemmas
    assert {"Geist", "geistig"}.issubset(lemmas)


def test_max_count_with_min_count(concordance_db: sqlite3.Connection) -> None:
    """min and max together carve a window — Geist (4) is in, haben (6)
    out, geistig (2) out, fragen (1) out."""

    out = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "min_count": "3", "max_count": "5"},
    )
    lemmas = {r["lemma"] for r in out["rows"]}
    assert lemmas == {"Geist"}


def test_inverted_range_returns_no_rows(concordance_db: sqlite3.Connection) -> None:
    """``max_count < min_count`` (a transient slider-drag state) must
    return zero rows rather than swap-or-error. The active-filter strip
    on the client surfaces the empty-result state to the user; an error
    here would just look like a network failure."""

    out = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "min_count": "10", "max_count": "5"},
    )
    assert out["rows"] == []


# ──────────────────────────────────────────────────────────────────
#  q × max_count interaction
# ──────────────────────────────────────────────────────────────────


def test_q_and_max_count_compose(concordance_db: sqlite3.Connection) -> None:
    """Both filters narrow independently — ``q=geist`` keeps {Geist,
    geistig}, then ``max_count=3`` drops Geist (count=4) leaving geistig."""

    out = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "q": "geist", "max_count": "3"},
    )
    assert [r["lemma"] for r in out["rows"]] == ["geistig"]


# ──────────────────────────────────────────────────────────────────
#  Header totals respect q but not freq
# ──────────────────────────────────────────────────────────────────


def test_totals_narrow_with_q(concordance_db: sqlite3.Connection) -> None:
    """``total_lemmas`` reflects the q narrowing — the F1 header would
    otherwise show ``122,965 lemmas`` alongside 2 results, which the
    redesign explicitly avoids."""

    no_q = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu"},
    )
    with_q = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "q": "geist"},
    )
    assert with_q["total_lemmas"] < no_q["total_lemmas"]
    assert with_q["total_lemmas"] == 2


def test_totals_ignore_freq_range(concordance_db: sqlite3.Connection) -> None:
    """``min_count``/``max_count`` shape which lemmas show, not the raw
    token total in scope. The header total stays stable as the user
    drags the freq slider — only the result rows change."""

    a = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu"},
    )
    b = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "max_count": "3"},
    )
    assert a["total_occurrences"] == b["total_occurrences"]


# ──────────────────────────────────────────────────────────────────
#  Aggregate rebuild transactionality
# ──────────────────────────────────────────────────────────────────


def test_aggregate_rebuild_is_all_or_nothing(
    concordance_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: `_bulk_insert` used to commit per scope, so a crash
    mid-rebuild left a half-built lemma_counts served as truth. The
    whole rebuild must now roll back to the prior contents."""

    from minerva.concordance import aggregate

    conn = concordance_db
    before = conn.execute(
        "SELECT lang, scope_kind, scope_value, lemma, pos, count "
        "FROM lemma_counts ORDER BY 1,2,3,4,5"
    ).fetchall()
    assert before  # fixture built the aggregate

    real_bulk_insert = aggregate._bulk_insert
    calls = {"n": 0}

    def flaky(conn_: sqlite3.Connection, rows: list) -> None:
        calls["n"] += 1
        if calls["n"] == 2:  # die after the corpus scope, before author
            raise RuntimeError("simulated crash mid-rebuild")
        real_bulk_insert(conn_, rows)

    monkeypatch.setattr(aggregate, "_bulk_insert", flaky)
    with pytest.raises(RuntimeError, match="mid-rebuild"):
        aggregate.build(conn)

    after = conn.execute(
        "SELECT lang, scope_kind, scope_value, lemma, pos, count "
        "FROM lemma_counts ORDER BY 1,2,3,4,5"
    ).fetchall()
    assert [tuple(r) for r in after] == [tuple(r) for r in before]


# ──────────────────────────────────────────────────────────────────
#  Multi-work scope (scope=work with several works)
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def two_work_db(tmp_path: Path) -> sqlite3.Connection:
    """Two German works sharing a lemma, each with a unique lemma, so
    multi-work selection can be checked for both summation and union."""
    import json

    chunks = [
        make_chunk(
            chunk_id="w1-1",
            corpus="schiller",
            author="Schiller",
            work="Über das Erhabene",
            lang="deu",
            section="¶1",
            text="Schönheit Schönheit Anmut",
        ),
        make_chunk(
            chunk_id="w2-1",
            corpus="schiller",
            author="Schiller",
            work="Vom Erhabenen",
            lang="deu",
            section="¶1",
            text="Schönheit Würde",
        ),
    ]
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(tmp_path / "mw.sqlite")
    store.insert_chunks(conn, jsonl)
    seed = [
        ("w1-1", 0, "Schönheit", "NOUN"),
        ("w1-1", 1, "Schönheit", "NOUN"),
        ("w1-1", 2, "Anmut", "NOUN"),  # unique to work 1
        ("w2-1", 0, "Schönheit", "NOUN"),
        ("w2-1", 1, "Würde", "NOUN"),  # unique to work 2
    ]
    for chunk_id, idx, lemma, pos in seed:
        _insert_lemma(conn, chunk_id=chunk_id, token_index=idx, surface=lemma, lemma=lemma, pos=pos)
    conn.commit()
    from minerva.concordance import aggregate

    aggregate.build(conn)
    return conn


def _count_of(res: dict, lemma: str) -> int:
    return next((r["count"] for r in res["rows"] if r["lemma"] == lemma), 0)


def test_multi_work_sums_shared_and_unions_unique(two_work_db: sqlite3.Connection) -> None:
    res = concordance_queries.lemma_index(
        two_work_db,
        # min_count=1 so the singletons (Anmut/Würde) show.
        {
            "lang": "deu",
            "scope": "work",
            "work": "Über das Erhabene\tVom Erhabenen",
            "min_count": "1",
        },
    )
    assert res["scope_label"] == "2 works"
    # Schönheit: 2 in work1 + 1 in work2 = 3 (summed across works).
    assert _count_of(res, "Schönheit") == 3
    # Both works' unique lemmas appear in the union.
    assert _count_of(res, "Anmut") == 1
    assert _count_of(res, "Würde") == 1
    # Header occurrences = all tokens across both works.
    assert res["total_occurrences"] == 5


def test_multi_work_equals_single_when_one_work(two_work_db: sqlite3.Connection) -> None:
    one = concordance_queries.lemma_index(
        two_work_db, {"lang": "deu", "scope": "work", "work": "Über das Erhabene", "min_count": "1"}
    )
    assert one["scope_label"] == "Über das Erhabene"
    assert _count_of(one, "Schönheit") == 2
    assert _count_of(one, "Würde") == 0  # not in work 1


def test_multi_work_kwic_spans_selected_works(two_work_db: sqlite3.Connection) -> None:
    res = concordance_queries.lemma_detail(
        two_work_db,
        {
            "lemma": "Schönheit",
            "lang": "deu",
            "scope": "work",
            "work": "Über das Erhabene\tVom Erhabenen",
        },
    )
    assert res["total"] == 3  # 2 + 1 across both works
    works = {r["work"] for r in res["rows"]}
    assert works == {"Über das Erhabene", "Vom Erhabenen"}


# ──────────────────────────────────────────────────────────────────
#  Multi-author scope (scope=author with several authors)
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def two_author_db(tmp_path: Path) -> sqlite3.Connection:
    """Two authors sharing a lemma, each with a unique lemma."""
    import json

    chunks = [
        make_chunk(
            chunk_id="h-1",
            corpus="hegel",
            author="Hegel",
            work="Phänomenologie",
            lang="deu",
            section="¶1",
            text="Geist Geist Dialektik",
        ),
        make_chunk(
            chunk_id="k-1",
            corpus="kant",
            author="Kant",
            work="Kritik",
            lang="deu",
            section="¶1",
            text="Geist Vernunft",
        ),
    ]
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(tmp_path / "ma.sqlite")
    store.insert_chunks(conn, jsonl)
    for chunk_id, idx, lemma in [
        ("h-1", 0, "Geist"),
        ("h-1", 1, "Geist"),
        ("h-1", 2, "Dialektik"),
        ("k-1", 0, "Geist"),
        ("k-1", 1, "Vernunft"),
    ]:
        _insert_lemma(
            conn, chunk_id=chunk_id, token_index=idx, surface=lemma, lemma=lemma, pos="NOUN"
        )
    conn.commit()
    from minerva.concordance import aggregate

    aggregate.build(conn)
    return conn


def test_multi_author_sums_shared_and_unions_unique(two_author_db: sqlite3.Connection) -> None:
    res = concordance_queries.lemma_index(
        two_author_db,
        {"lang": "deu", "scope": "author", "author": "Hegel\tKant", "min_count": "1"},
    )
    assert res["scope_label"] == "2 authors"
    assert _count_of(res, "Geist") == 3  # 2 (Hegel) + 1 (Kant)
    assert _count_of(res, "Dialektik") == 1  # Hegel only
    assert _count_of(res, "Vernunft") == 1  # Kant only
    assert res["total_occurrences"] == 5


def test_multi_author_kwic_spans_selected_authors(two_author_db: sqlite3.Connection) -> None:
    res = concordance_queries.lemma_detail(
        two_author_db,
        {"lemma": "Geist", "lang": "deu", "scope": "author", "author": "Hegel\tKant"},
    )
    assert res["total"] == 3
    assert {r["author"] for r in res["rows"]} == {"Hegel", "Kant"}


@pytest.fixture
def case_merge_db(tmp_path: Path) -> sqlite3.Connection:
    """German lemmas with case variants for merge_case pagination."""
    import json

    chunks = [
        make_chunk(
            chunk_id="c-1",
            corpus="hegel",
            author="Hegel",
            work="Phänomenologie",
            lang="deu",
            section="¶1",
            text="Gott GOtt haben",
        ),
    ]
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(tmp_path / "case.sqlite")
    store.insert_chunks(conn, jsonl)
    for chunk_id, idx, lemma, pos in [
        ("c-1", 0, "Gott", "NOUN"),
        ("c-1", 1, "GOtt", "NOUN"),
        ("c-1", 2, "haben", "VERB"),
        ("c-1", 3, "haben", "VERB"),
        ("c-1", 4, "haben", "VERB"),
    ]:
        _insert_lemma(conn, chunk_id=chunk_id, token_index=idx, surface=lemma, lemma=lemma, pos=pos)
    conn.commit()
    from minerva.concordance import aggregate

    aggregate.build(conn)
    return conn


@pytest.fixture
def unicode_case_merge_db(tmp_path: Path) -> sqlite3.Connection:
    """German lemmas whose case difference sits outside ASCII (#373).

    ``case_merge_db`` above seeds ``Gott``/``GOtt`` — the flourishes
    ``merge_case``'s docstring names, all ASCII, all handled by SQL
    ``LOWER()``. Nothing exercised a lemma with an umlaut until this,
    which is why the defect survived.

      * Übergehen / übergehen — one lemma, one POS, split by an
        ASCII-only ``LOWER()`` into two groups rendering the same label.
      * Abdruck / Abdrück — *different* lemmas that a diacritic-folding
        group key would wrongly merge. They are here to pin the choice
        of fold, not just the presence of one.
    """
    import json

    chunks = [
        make_chunk(
            chunk_id="u-1",
            corpus="hegel",
            author="Hegel",
            work="Phänomenologie",
            lang="deu",
            section="¶1",
            text="Übergehen übergehen übergehen Abdruck Abdrück",
        ),
    ]
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(tmp_path / "unicode_case.sqlite")
    store.insert_chunks(conn, jsonl)
    for chunk_id, idx, lemma, pos in [
        ("u-1", 0, "Übergehen", "NOUN"),
        ("u-1", 1, "übergehen", "NOUN"),
        ("u-1", 2, "übergehen", "NOUN"),
        ("u-1", 3, "Abdruck", "NOUN"),
        ("u-1", 4, "Abdrück", "NOUN"),
    ]:
        _insert_lemma(conn, chunk_id=chunk_id, token_index=idx, surface=lemma, lemma=lemma, pos=pos)
    conn.commit()
    from minerva.concordance import aggregate

    aggregate.build(conn)
    return conn


def test_merge_case_merges_variants_whose_case_leaves_ascii(
    unicode_case_merge_db: sqlite3.Connection,
) -> None:
    """``merge_case`` folds case for every script, not just ASCII (#373).

    SQLite's ``LOWER()`` leaves non-ASCII untouched — measured,
    ``lower('Übergehen')`` returns it unchanged — so ``Übergehen`` and
    ``übergehen`` stayed separate groups, then rendered the *same*
    display label at different ranks. On the live German index that is
    113 group pairs, and ``Übergehen`` NOUN appeared twice at 78 and 59
    where the truth is 137."""

    out = concordance_queries.lemma_index(
        unicode_case_merge_db,
        {"lang": "deu", "merge_case": "1", "min_count": "1"},
    )
    rows = [r for r in out["rows"] if r["lemma"].lower() == "übergehen"]

    assert len(rows) == 1, f"one lemma rendered as {len(rows)} rows: {rows}"
    assert rows[0]["count"] == 3
    assert sorted(rows[0]["variants"]) == ["Übergehen", "übergehen"]


def test_merge_case_does_not_merge_lemmas_that_differ_by_diacritic(
    unicode_case_merge_db: sqlite3.Connection,
) -> None:
    """The group key folds *case*, not diacritics.

    Both #366 and #373 proposed reusing ``_fold_text`` — right for the
    ``q`` search box, wrong here: it drops combining marks, so it would
    merge ``Abdruck`` with ``Abdrück``. Measured against the live index
    that is 2,206 further German groups, 5,499 French and 8,228 Greek
    (where accent is lexical) — 7,705 broken to fix 113."""

    out = concordance_queries.lemma_index(
        unicode_case_merge_db,
        {"lang": "deu", "merge_case": "1", "min_count": "1"},
    )
    lemmas = {r["lemma"] for r in out["rows"]}

    assert "Abdruck" in lemmas
    assert "Abdrück" in lemmas


def test_merge_case_off_keeps_every_variant_on_its_own_row(
    unicode_case_merge_db: sqlite3.Connection,
) -> None:
    """``merge_case=0`` groups on the bare lemma and installs no folding
    callback at all, so the variants the default collapses stay apart."""

    out = concordance_queries.lemma_index(
        unicode_case_merge_db,
        {"lang": "deu", "merge_case": "0", "min_count": "1"},
    )
    rows = {(r["lemma"], r["pos"]): r["count"] for r in out["rows"]}

    assert rows[("Übergehen", "NOUN")] == 1
    assert rows[("übergehen", "NOUN")] == 2


def test_merge_case_pagination_honors_offset(case_merge_db: sqlite3.Connection) -> None:
    first = concordance_queries.lemma_index(
        case_merge_db,
        {"lang": "deu", "scope": "corpus", "limit": "1", "offset": "0", "min_count": "1"},
    )
    second = concordance_queries.lemma_index(
        case_merge_db,
        {"lang": "deu", "scope": "corpus", "limit": "1", "offset": "1", "min_count": "1"},
    )
    assert len(first["rows"]) == 1
    assert len(second["rows"]) == 1
    assert first["rows"][0]["lemma"] == "haben"
    assert second["rows"][0]["lemma"] == "Gott"
    assert second["rows"][0]["count"] == 2


# ── q — diacritic + case folding (#363) ──────────────────────────────


def test_fold_text_folds_the_whole_string() -> None:
    """``_fold_text`` is ``_fold_initial`` without the first-character
    slice: NFD-decompose, drop combining marks, upper-case. Unlike SQL
    ``LOWER()`` it is Unicode-aware, which is what makes the ``q``
    filter work for every script in the corpus rather than Latin only."""

    assert (
        index_queries._fold_text("\u03bb\u03cc\u03b3\u03bf\u03c2")
        == "\u039b\u039f\u0393\u039f\u03a3"
    )
    assert (
        index_queries._fold_text("\u1f08\u03b8\u03b7\u03bd\u1fb6")
        == "\u0391\u0398\u0397\u039d\u0391"
    )
    # German eszett expands under upper-casing, so Strasse ↔ Straße fold
    # together. Surprising but wanted for a substring search field.
    assert index_queries._fold_text("Gr\u00f6\u00dfe") == "GROSSE"
    assert index_queries._fold_text("") == ""
    assert index_queries._fold_text(None) == ""


def test_fold_initial_still_folds_only_the_first_character() -> None:
    """The letter-rail folder keeps its contract while sharing the
    whole-string implementation. Guards the refactor, not new behaviour."""

    assert (
        index_queries._fold_initial("\u1f04\u03bd\u03b8\u03c1\u03c9\u03c0\u03bf\u03c2") == "\u0391"
    )
    assert index_queries._fold_initial("") == ""
    assert index_queries._fold_initial(None) == ""


def test_fold_initial_collapses_multi_character_upper_case_expansions() -> None:
    """``_fold_initial`` truncates to one character AFTER folding (#381).

    Not redundant: upper-casing expands some single characters, and a
    two-character bucket is not a key on a 26-letter rail — so without the
    trailing slice these lemmas would bucket under ``SS`` / ``FI`` and be
    unreachable from the rail entirely.
    """

    # German eszett expands to SS.
    assert index_queries._fold_text("\u00df") == "SS"
    assert index_queries._fold_initial("\u00dfeta") == "S"
    # Latin ligatures expand under upper-casing too. These are an OCR
    # artifact in the English-language editions (76 `ﬁ`-initial and 42
    # `ﬂ`-initial rows in the live index) and this is what makes them
    # reachable under F.
    assert index_queries._fold_initial("\ufb01nis") == "F"
    assert index_queries._fold_initial("\ufb02ower") == "F"


def test_fold_initial_does_not_transliterate_across_scripts() -> None:
    """The fold strips diacritics; it does not romanize.

    A Greek-script lemma keeps a Greek bucket even in an English-language
    partition, which is correct — ``Επιστήμη`` is not an English ``E`` — and
    is why folding alone does not make every row reachable from an A–Z rail.
    The residue is a cross-script problem, tracked separately.
    """

    assert (
        index_queries._fold_initial("\u0395\u03c0\u03b9\u03c3\u03c4\u03ae\u03bc\u03b7") == "\u0395"
    )
    assert index_queries._fold_initial("sibi") == "S"
    # `Œ` has no NFD decomposition, so it stays its own letter.
    assert index_queries._fold_initial("\u0152uvre") == "\u0152"


def test_q_folds_greek_diacritics(
    greek_concordance_db: sqlite3.Connection,
) -> None:
    """Unaccented input finds the accented lemma. The polytonic accents
    are the hardest part of a Greek word to type and carry no
    information the reader has before they start typing."""

    out = concordance_queries.lemma_index(
        greek_concordance_db,
        {"lang": "grc", "q": "\u03bb\u03bf\u03b3\u03bf\u03c2", "min_count": "1"},
    )
    assert {r["lemma"] for r in out["rows"]} == {"\u03bb\u03cc\u03b3\u03bf\u03c2"}


def test_q_accented_input_still_matches(
    greek_concordance_db: sqlite3.Connection,
) -> None:
    """Folding must not break the reader who *can* type the diacritics.
    Fails if only the column side is folded and the parameter is not."""

    out = concordance_queries.lemma_index(
        greek_concordance_db,
        {"lang": "grc", "q": "\u03bb\u03cc\u03b3\u03bf\u03c2", "min_count": "1"},
    )
    assert {r["lemma"] for r in out["rows"]} == {"\u03bb\u03cc\u03b3\u03bf\u03c2"}


def test_q_greek_uppercase_input_matches_lowercase_lemma(
    greek_concordance_db: sqlite3.Connection,
) -> None:
    """SQLite's ``LOWER()`` is ASCII-only — measured, ``SELECT
    lower('\u039b\u039f\u0393\u039f\u03a3')`` returns the string unchanged — so the docstring's
    promise of a case-insensitive filter was false for every non-Latin
    script in the corpus. Folding in Python fixes that as a side
    effect."""

    out = concordance_queries.lemma_index(
        greek_concordance_db,
        {"lang": "grc", "q": "\u039b\u039f\u0393\u039f\u03a3", "min_count": "1"},
    )
    assert {r["lemma"] for r in out["rows"]} == {"\u03bb\u03cc\u03b3\u03bf\u03c2"}


def test_q_totals_fold_too(
    greek_concordance_db: sqlite3.Connection,
) -> None:
    """The header totals are a second query over the same predicate
    builder. Folding one and not the other desyncs the "n of N" the page
    prints against the rows it shows."""

    out = concordance_queries.lemma_index(
        greek_concordance_db,
        {"lang": "grc", "q": "\u03bb\u03bf\u03b3\u03bf\u03c2", "min_count": "1"},
    )
    assert out["total_lemmas"] == 1


def test_q_folded_wildcards_do_not_bypass_the_filter(
    greek_concordance_db: sqlite3.Connection,
) -> None:
    """#120's guard, re-asserted through the fold. ``escape_like_substring``
    is applied *after* folding, so the escape cannot be undone by an
    NFD/upper-case pass — and an accented wildcard is the case only the
    ordering can break."""

    for pattern in ("%", "_", "\u03cc%"):
        out = concordance_queries.lemma_index(
            greek_concordance_db,
            {"lang": "grc", "q": pattern, "min_count": "1"},
        )
        assert out["rows"] == [], pattern
        assert out["total_lemmas"] == 0, pattern


# ── next_offset — the pagination cursor (#371) ────────────────────────


def test_next_offset_walks_then_stops(concordance_db: sqlite3.Connection) -> None:
    """A full page hands back the offset of the next one; a short page hands
    back ``None``. This is what lets the client page without consulting
    ``total_lemmas``, which cannot be trusted as a row count."""

    first = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "limit": "1", "offset": "0"},
    )
    assert len(first["rows"]) == 1
    assert first["next_offset"] == 1

    # Walk to the end and confirm the cursor terminates rather than running on.
    seen: list[str] = []
    params = {"lang": "deu", "limit": "1", "offset": "0"}
    for _ in range(20):
        page = concordance_queries.lemma_index(concordance_db, dict(params))
        seen.extend(r["lemma"] for r in page["rows"])
        if page["next_offset"] is None:
            break
        params["offset"] = str(page["next_offset"])
    else:  # pragma: no cover - only trips if the cursor never terminates
        raise AssertionError("next_offset never became None")

    # Every lemma seen exactly once — the cursor neither skipped nor repeated.
    assert len(seen) == len(set(seen))


def test_next_offset_is_derived_from_returned_rows_not_total_lemmas(
    concordance_db: sqlite3.Connection,
) -> None:
    """The crux, and the reason this is not modelled on the KWIC endpoint's
    ``offset + limit < total``.

    ``total_lemmas`` is computed *without* the frequency range applied (see the
    note above the totals query), so a ``max_count`` that excludes rows leaves
    it larger than anything the caller can actually page to. A cursor derived
    from it would keep asking for pages that come back empty."""

    filtered = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "max_count": "1", "min_count": "1", "limit": "50"},
    )
    # The freq range narrowed the rows but not the total — that mismatch is
    # exactly what a total-derived cursor would trip over.
    assert len(filtered["rows"]) < filtered["total_lemmas"]
    # Short page → the cursor stops, despite `total_lemmas` suggesting more.
    assert filtered["next_offset"] is None


# ── letter_counts — the A–Z rail's populations (#376) ────────────────


def test_letter_counts_describe_the_scope_not_the_page(
    concordance_db: sqlite3.Connection,
) -> None:
    """The rail's per-letter populations come from the server, over the whole
    filtered scope (#376).

    They used to be folded from the rows the client had already fetched, so a
    letter whose lemmas all sorted below the fetched window rendered as empty —
    measured on the live index, G holds 11,125 German lemmas and S holds
    15,366, and neither was visible on first paint unless one of them happened
    to rank in the top rows."""

    out = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "limit": "1", "min_count": "1"},
    )

    # One row fetched, but every letter present in scope is counted.
    assert len(out["rows"]) == 1
    assert out["letter_counts"]["G"] == 2  # Geist, geistig
    assert out["letter_counts"]["H"] == 1  # haben
    assert out["letter_counts"]["F"] == 1  # fragen
    assert "Z" not in out["letter_counts"]


def test_letter_counts_honour_the_other_filters(
    concordance_db: sqlite3.Connection,
) -> None:
    """A dot means "clicking this letter returns rows", so the counts sit under
    the same filters the rows do — including the frequency range, which
    ``total_lemmas`` deliberately ignores. ``fragen`` occurs once, so the
    default ``min_count=2`` must take F off the rail entirely."""

    out = concordance_queries.lemma_index(concordance_db, {"lang": "deu"})

    assert "F" not in out["letter_counts"]
    assert out["letter_counts"]["G"] == 2


def test_letter_counts_ignore_the_selected_letter(
    concordance_db: sqlite3.Connection,
) -> None:
    """Selecting a letter must not empty the rest of the rail — otherwise the
    reader has no way to see where else there is anything, and cannot move
    between letters without clearing first."""

    out = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "letter": "G", "min_count": "1"},
    )

    assert [r["lemma"] for r in out["rows"]] == ["Geist", "geistig"]
    assert out["letter_counts"]["H"] == 1
    assert out["letter_counts"]["G"] == 2


def test_greek_letter_counts_fold_diacritics(
    greek_concordance_db: sqlite3.Connection,
) -> None:
    """Greek buckets on the folded initial, the same key the letter filter
    uses — ἄνθρωπος, ἀγαθός and Ἀθηνᾶ all land under Α."""

    out = concordance_queries.lemma_index(
        greek_concordance_db,
        {"lang": "grc", "min_count": "1"},
    )

    # 4, not 3. #366's fix made the group key the whole lemma and added
    # ἀρχή NOUN to this fixture beside ἄνθρωπος NOUN; under the old
    # first-character key those two were a single group. Neither PR could
    # catch this on its own — each number was right on its own branch.
    assert out["letter_counts"]["Α"] == 4
    assert out["letter_counts"]["Λ"] == 1


# ── total_lemmas counts the unit the rows use (#377) ─────────────────


def test_total_lemmas_counts_lemma_pos_pairs_on_both_branches(
    concordance_db: sqlite3.Connection,
) -> None:
    """``total_lemmas`` counted ``DISTINCT lemma`` when case-merging was off,
    while the rows it sits above are per ``(lemma, pos)`` — so a lemma tagged
    both NOUN and VERB was one for the header and two for the list (#377).

    ``Geist`` is seeded as NOUN only here, so the fixture pins the invariant
    rather than the divergence: the two branches must agree on the unit."""

    merged = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "merge_case": "1", "min_count": "1"},
    )
    unmerged = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "merge_case": "0", "min_count": "1"},
    )

    # No case variants in this fixture, so merging changes nothing — and with
    # both branches counting the same unit, neither does the branch.
    assert unmerged["total_lemmas"] == merged["total_lemmas"]


def test_total_lemmas_splits_a_lemma_carrying_two_pos_tags(
    pos_split_db: sqlite3.Connection,
) -> None:
    """The divergence itself. ``recht`` is tagged ADJ and VERB, so it is two
    rows; the header must say two, not one."""

    out = concordance_queries.lemma_index(
        pos_split_db,
        {"lang": "deu", "merge_case": "0", "min_count": "1"},
    )

    assert [(r["lemma"], r["pos"]) for r in out["rows"]] == [
        ("recht", "ADJ"),
        ("recht", "VERB"),
    ]
    assert out["total_lemmas"] == 2


@pytest.fixture
def pos_split_db(tmp_path: Path) -> sqlite3.Connection:
    """One lemma carrying two POS tags — the shape ``COUNT(DISTINCT lemma)``
    under-counted (#377)."""
    import json

    chunks = [
        make_chunk(
            chunk_id="p-1",
            corpus="hegel",
            author="Hegel",
            work="Phänomenologie",
            lang="deu",
            section="¶1",
            text="recht recht",
        ),
    ]
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(tmp_path / "pos_split.sqlite")
    store.insert_chunks(conn, jsonl)
    for chunk_id, idx, lemma, pos in [
        ("p-1", 0, "recht", "ADJ"),
        ("p-1", 1, "recht", "VERB"),
    ]:
        _insert_lemma(conn, chunk_id=chunk_id, token_index=idx, surface=lemma, lemma=lemma, pos=pos)
    conn.commit()
    from minerva.concordance import aggregate

    aggregate.build(conn)
    return conn


def test_next_offset_survives_case_merging(
    concordance_db: sqlite3.Connection,
) -> None:
    """The aggregate branch pages in Python after a GROUP BY, so its row count
    is the merged one. Guards the cursor against being computed before the
    merge, which would over-report."""

    page = concordance_queries.lemma_index(
        concordance_db,
        {"lang": "deu", "limit": "1", "offset": "0", "merge_case": "1"},
    )
    assert page["next_offset"] == 1


def test_paging_one_row_at_a_time_visits_every_row_exactly_once(
    tie_concordance_db: sqlite3.Connection,
) -> None:
    """The invariant offset pagination rests on: the sort must be a TOTAL order.

    ``recht``/ADJ and ``recht``/VERB agree on ``(n, lemma_key)`` and differ only
    in ``pos``, which the ORDER BY omitted — so the two were interchangeable and
    ``LIMIT/OFFSET`` could serve one twice and the other never.

    805 groups in the live German index tie on the full sort key, so the risk is
    real; but neither this fixture nor a live 200-row walk has caught a boundary
    actually mis-serving one, and a four-row fixture is far too small to make
    SQLite's planner change its mind. So this is a net, not a reproduction —
    said plainly because an earlier draft of this test claimed a live duplicate
    as its evidence, and that duplicate was a different bug (ASCII-only
    ``LOWER()`` splitting ``merge_case`` groups)."""

    unpaged = concordance_queries.lemma_index(
        tie_concordance_db,
        {"lang": "deu", "limit": "50", "min_count": "1"},
    )
    expected = [(r["lemma"], r["pos"]) for r in unpaged["rows"]]
    assert len(expected) == len(set(expected)), "fixture itself has duplicate rows"

    walked: list[tuple[str, str]] = []
    offset: int | None = 0
    while offset is not None:
        page = concordance_queries.lemma_index(
            tie_concordance_db,
            {"lang": "deu", "limit": "1", "offset": str(offset), "min_count": "1"},
        )
        walked.extend((r["lemma"], r["pos"]) for r in page["rows"])
        offset = page["next_offset"]

    # Same rows, same order, each exactly once.
    assert walked == expected


def test_tied_rows_are_ordered_by_pos_so_the_sort_is_total(
    tie_concordance_db: sqlite3.Connection,
) -> None:
    """Names the tiebreaker, so a future ORDER BY edit that drops it fails here
    rather than silently reintroducing unstable paging."""

    out = concordance_queries.lemma_index(
        tie_concordance_db,
        {"lang": "deu", "limit": "50", "min_count": "1"},
    )
    tied = [(r["lemma"], r["pos"], r["count"]) for r in out["rows"] if r["lemma"] == "recht"]
    assert tied == [("recht", "ADJ", 2), ("recht", "VERB", 2)]


# ── the A–Z rail must be able to address every initial (#381) ─────────
#
# The rail offers 26 keys; the corpus has more initials than that. Measured
# over the whole live index when this was filed: 914 German rows, 1,344
# French and 571 English begin with a character that has no rail key, and
# `lemma LIKE 'A%'` cannot reach them because SQLite's LIKE is
# case-insensitive for ASCII only and folds nothing.
#
# Greek already had the fold (`fold_initial`), because polytonic forms made
# the gap impossible to miss. These tests hold every other language to the
# same rule.


@pytest.fixture
def umlaut_concordance_db(tmp_path: Path) -> sqlite3.Connection:
    """German chunks whose lemmas start with umlauts, both cases.

    ``Ähnlich`` / ``ähnlich`` are the pair that proves the fold: the
    frontend already buckets them under ``A`` for its alpha-sort section
    headers, so before this fix display and filter disagreed — a reader saw
    ``Ähnlich`` under an ``A`` heading, clicked ``A``, and did not get it.

    ``Apfel`` is the ASCII control that must keep working, and ``Bild`` is
    the negative control that ``A`` must never return.

    Every seeded lemma is a CONTENT word (NOUN/ADJ) on purpose. The
    leaderboard's default POS set strips function words — DET/ADP/CCONJ/
    SCONJ/PRON/AUX/PART/PUNCT/SYM/SPACE (``_scope.py:15``) — so seeding the
    umlaut cases as ``ADP`` (``über``) makes them vanish for a reason that
    has nothing to do with the letter fold, and the test then fails while
    the fold works.
    """

    import json

    chunks = [
        make_chunk(
            chunk_id="uml-1",
            corpus="hegel",
            author="Hegel",
            work="Test",
            lang="deu",
            section="A",
            text="Ähnlich ähnlich Übel übel Apfel Bild",
        ),
        make_chunk(
            chunk_id="uml-2",
            corpus="hegel",
            author="Hegel",
            work="Test",
            lang="deu",
            section="B",
            text="Ähnlich Übel Apfel Bild Öl",
        ),
    ]
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(tmp_path / "uml.sqlite")
    store.insert_chunks(conn, jsonl)

    seed = [
        ("uml-1", 0, "Ähnlich", "ADJ"),
        ("uml-1", 1, "ähnlich", "ADJ"),
        ("uml-1", 2, "Übel", "NOUN"),
        ("uml-1", 3, "übel", "ADJ"),
        ("uml-1", 4, "Apfel", "NOUN"),
        ("uml-1", 5, "Bild", "NOUN"),
        ("uml-2", 0, "Ähnlich", "ADJ"),
        ("uml-2", 1, "Übel", "NOUN"),
        ("uml-2", 2, "Apfel", "NOUN"),
        ("uml-2", 3, "Bild", "NOUN"),
        ("uml-2", 4, "Öl", "NOUN"),
    ]
    for chunk_id, idx, lemma, pos in seed:
        _insert_lemma(
            conn,
            chunk_id=chunk_id,
            token_index=idx,
            surface=lemma,
            lemma=lemma,
            pos=pos,
        )
    conn.commit()
    from minerva.concordance import aggregate

    aggregate.build(conn)
    return conn


def test_letter_A_reaches_umlaut_initial_german(
    umlaut_concordance_db: sqlite3.Connection,
) -> None:
    """``letter=A`` returns ``Ähnlich``, which is what the frontend's own
    alpha-sort headers already claim."""

    out = concordance_queries.lemma_index(
        umlaut_concordance_db,
        {"lang": "deu", "letter": "A", "min_count": "1"},
    )
    lemmas = {r["lemma"] for r in out["rows"]}
    assert "Ähnlich" in lemmas
    assert "Apfel" in lemmas, "the ASCII case must keep working"
    assert "Bild" not in lemmas, "the fold must not widen the filter to everything"


def test_letter_A_folds_both_cases_of_the_umlaut(
    umlaut_concordance_db: sqlite3.Connection,
) -> None:
    """``Ä`` and ``ä`` both belong to ``A``. With ``merge_case`` on they are
    one lemma anyway; this asserts the letter filter agrees."""

    out = concordance_queries.lemma_index(
        umlaut_concordance_db,
        {"lang": "deu", "letter": "A", "min_count": "1"},
    )
    assert any(r["lemma"].lower().startswith("ähnlich") for r in out["rows"])


def test_letter_U_reaches_umlaut_initial_german(
    umlaut_concordance_db: sqlite3.Connection,
) -> None:
    """Not just ``A``: ``Ü`` folds to ``U`` as well. ``ü`` was the largest
    off-rail bucket in the live index (610 rows)."""

    out = concordance_queries.lemma_index(
        umlaut_concordance_db,
        {"lang": "deu", "letter": "U", "min_count": "1"},
    )
    assert any(r["lemma"].lower().startswith("übel") for r in out["rows"])


def test_letter_O_reaches_umlaut_initial_german(
    umlaut_concordance_db: sqlite3.Connection,
) -> None:
    out = concordance_queries.lemma_index(
        umlaut_concordance_db,
        {"lang": "deu", "letter": "O", "min_count": "1"},
    )
    assert any(r["lemma"] == "Öl" for r in out["rows"])


def test_letter_counts_buckets_agree_with_what_the_letter_returns(
    umlaut_concordance_db: sqlite3.Connection,
) -> None:
    """The rail's own invariant, stated in ``_letter_key_expr``'s docstring:
    a dot on the rail means clicking there returns rows.

    This is what the pre-fix code could not honour for non-ASCII. The bucket
    key ran on ``lower_uni(lemma)`` while the filter ran ``LIKE`` on raw
    ``lemma``, so ``Ä``-initial rows bucketed under ``ä`` — a key not on the
    rail — while ``letter=Ä`` matched rows the rail said were zero.
    """

    out = concordance_queries.lemma_index(
        umlaut_concordance_db,
        {"lang": "deu", "min_count": "1"},
    )
    counts = out["letter_counts"]

    # Every bucket must be an A–Z key now: nothing off-rail is left.
    assert set(counts) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ"), (
        f"off-rail buckets remain: {sorted(set(counts) - set('ABCDEFGHIJKLMNOPQRSTUVWXYZ'))}"
    )

    # And each bucket's count matches what clicking it actually returns.
    for key, n in counts.items():
        clicked = concordance_queries.lemma_index(
            umlaut_concordance_db,
            {"lang": "deu", "letter": key, "min_count": "1", "limit": "500"},
        )
        assert clicked["total_lemmas"] == n, (
            f"rail says {key}={n} but clicking it returns {clicked['total_lemmas']}"
        )


# ── the stored folded initial (#425) ──────────────────────────────────
#
# #381's fold replaced an indexed prefix predicate with a Python callback, which
# cost a full scan of the language partition per letter click. The fold is now
# stored in `lemma_counts.lemma_initial` (migration 0031) and indexed, so the
# filter is an indexed equality and the rail's GROUP BY reads a column.
#
# That buys speed at the price of derived state, so these tests guard the
# coupling rather than the timing: timings move ~6x with page-cache state (see
# the correction on #425), the query PLAN does not.


def test_stored_lemma_initial_equals_the_fold_for_every_row(
    umlaut_concordance_db: sqlite3.Connection,
) -> None:
    """The stored column must equal what the request folds with.

    This is the invariant the whole optimisation rests on: `aggregate.build`
    writes `lemma_initial` and the read path compares a folded parameter against
    it. If the two ever disagree, the letter filter silently returns wrong rows
    — no error, no empty result, just a different answer. Same hazard class as
    `chunk_lemma_state`'s `text_hash`.
    """

    rows = umlaut_concordance_db.execute("SELECT lemma, lemma_initial FROM lemma_counts").fetchall()
    assert rows, "fixture built no aggregate rows"
    mismatched = [
        (r["lemma"], r["lemma_initial"], index_queries._fold_initial(r["lemma"]))
        for r in rows
        if r["lemma_initial"] != index_queries._fold_initial(r["lemma"])
    ]
    assert mismatched == []


def test_no_aggregate_row_is_left_without_an_initial(
    umlaut_concordance_db: sqlite3.Connection,
) -> None:
    """A NULL would be invisible rather than loud: `lemma_initial = ?` matches
    nothing against NULL, so the letter would return zero rows and look like a
    letter with no lemmas."""

    (n_null,) = umlaut_concordance_db.execute(
        "SELECT COUNT(*) FROM lemma_counts WHERE lemma_initial IS NULL"
    ).fetchone()
    assert n_null == 0


def test_letter_filter_seeks_the_initial_index_instead_of_scanning(
    umlaut_concordance_db: sqlite3.Connection,
) -> None:
    """The point of the column, asserted on the plan rather than the clock.

    Before #425 the plan for a letter-filtered read was

        SEARCH lemma_counts USING COVERING INDEX lemma_counts_by_alpha
          (lang=? AND scope_kind=? AND scope_value=?)

    — the partition prefix only, with `fold_initial(lemma)` applied to every row
    in it. With the stored column the equality is part of the index key.
    """

    plan = "\n".join(
        str(r[-1])
        for r in umlaut_concordance_db.execute(
            "EXPLAIN QUERY PLAN "
            "SELECT lemma FROM lemma_counts "
            "WHERE lang=? AND scope_kind=? AND scope_value IS NULL AND lemma_initial=?",
            ("deu", "corpus", "A"),
        )
    )
    assert "lemma_counts_by_initial" in plan, plan
    assert "lemma_initial=?" in plan.replace(" ", ""), plan
    assert "SCAN" not in plan, plan


def test_migration_0031_is_idempotent_and_fills_nulls(
    umlaut_concordance_db: sqlite3.Connection,
) -> None:
    """Re-applying is free, and it repairs a row whose initial went missing."""

    import importlib

    mod = importlib.import_module("minerva.migrations.0031_lemma_counts_initial")

    umlaut_concordance_db.execute(
        "UPDATE lemma_counts SET lemma_initial = NULL WHERE lemma LIKE 'Ä%'"
    )
    (n_null,) = umlaut_concordance_db.execute(
        "SELECT COUNT(*) FROM lemma_counts WHERE lemma_initial IS NULL"
    ).fetchone()
    assert n_null > 0, "fixture has no Ä-initial rows to null out"

    mod.apply(umlaut_concordance_db)

    (still_null,) = umlaut_concordance_db.execute(
        "SELECT COUNT(*) FROM lemma_counts WHERE lemma_initial IS NULL"
    ).fetchone()
    assert still_null == 0
    # And the repaired value is the fold, not a placeholder.
    (val,) = umlaut_concordance_db.execute(
        "SELECT DISTINCT lemma_initial FROM lemma_counts WHERE lemma LIKE 'Ä%'"
    ).fetchone()
    assert val == "A"


# ── the stored merge_case key (#655) ──────────────────────────────────
#
# The index page's load grouped every lemma of the language on
# `lower_uni(lemma)`, twice, through an index that covered neither the key nor
# the columns summed: ~230 ms for deu, each time the page opened. The key is
# now stored in `lemma_counts.lemma_key` (migration 0037) and a covering index
# leads with it, so both statements group straight off the index. Same shape
# of derived-state coupling as `lemma_initial`, guarded the same way.


def test_stored_lemma_key_equals_the_merge_case_fold_for_every_row(
    umlaut_concordance_db: sqlite3.Connection,
) -> None:
    """The grouping and the page's detail seeks both read the stored key, so a
    key that disagreed with `_lower_unicode` would split or merge variants
    differently from what `merge_case` claims, silently."""

    rows = umlaut_concordance_db.execute("SELECT lemma, lemma_key FROM lemma_counts").fetchall()
    assert rows, "fixture built no aggregate rows"
    mismatched = [
        (r["lemma"], r["lemma_key"])
        for r in rows
        if r["lemma_key"] != index_queries._lower_unicode(r["lemma"])
    ]
    assert mismatched == []


def _grouped_load_plans(conn: sqlite3.Connection, query: dict[str, str]) -> list[str]:
    """EXPLAIN every grouped `lemma_counts` statement a real `lemma_index` call
    issues — the shipped SQL, captured, not a restatement of it. The page's
    per-group detail seeks do not group and are left out."""

    issued: list[str] = []
    conn.set_trace_callback(issued.append)
    try:
        concordance_queries.lemma_index(conn, query)
    finally:
        conn.set_trace_callback(None)
    return [
        "\n".join(str(r[-1]) for r in conn.execute("EXPLAIN QUERY PLAN " + sql))
        for sql in issued
        if "lemma_counts" in sql and "GROUP BY" in sql
    ]


def test_index_page_load_groups_off_the_key_index(
    umlaut_concordance_db: sqlite3.Connection,
) -> None:
    """Asserted on the plan, not the clock, for the reason given above #425's
    tests. Before #655 each grouping read `lemma_counts_by_pos` and built a
    temp B-tree over the partition; now every grouped read comes from the
    covering index in key order. What remains are the rail's GROUP BY letter
    and the page's ORDER BY, over the grouped rows rather than the table."""

    grouped = _grouped_load_plans(umlaut_concordance_db, {"lang": "deu", "min_count": "1"})
    assert len(grouped) == 2, grouped  # the page's top-N and the rail/totals scan
    for plan in grouped:
        assert "COVERING INDEX lemma_counts_by_key" in plan, plan
    top_n, rail = grouped[0], grouped[1]
    assert "TEMP B-TREE FOR GROUP BY" not in top_n, top_n
    # One temp B-tree left in the rail: the outer GROUP BY letter.
    assert rail.count("TEMP B-TREE FOR GROUP BY") == 1, rail


def test_no_aggregate_row_is_left_without_a_key(
    umlaut_concordance_db: sqlite3.Connection,
) -> None:
    """A NULL key would drop the row out of every merged group — the page's
    detail seek matches on it."""

    (n_null,) = umlaut_concordance_db.execute(
        "SELECT COUNT(*) FROM lemma_counts WHERE lemma_key IS NULL"
    ).fetchone()
    assert n_null == 0


def test_migration_0037_is_idempotent_and_fills_nulls(
    umlaut_concordance_db: sqlite3.Connection,
) -> None:
    import importlib

    mod = importlib.import_module("minerva.migrations.0037_lemma_counts_key")

    umlaut_concordance_db.execute("UPDATE lemma_counts SET lemma_key = NULL WHERE lemma LIKE 'Ä%'")
    (n_null,) = umlaut_concordance_db.execute(
        "SELECT COUNT(*) FROM lemma_counts WHERE lemma_key IS NULL"
    ).fetchone()
    assert n_null > 0, "fixture has no Ä-initial rows to null out"

    mod.apply(umlaut_concordance_db)

    rows = umlaut_concordance_db.execute(
        "SELECT lemma, lemma_key FROM lemma_counts WHERE lemma LIKE 'Ä%'"
    ).fetchall()
    # Python's lower, not SQL's ASCII-only LOWER(): `Ä` must become `ä`.
    assert all(r["lemma_key"] == r["lemma"].lower() for r in rows), rows
    assert any(r["lemma_key"].startswith("ä") for r in rows), rows


# ──────────────────────────────────────────────────────────────────
#  Cross-script language partitioning (#644) + one-pass breakdowns (#643)
# ──────────────────────────────────────────────────────────────────


def _insert_lemma_lang(
    conn: sqlite3.Connection,
    *,
    chunk_id: str,
    token_index: int,
    surface: str,
    lemma: str,
    pos: str,
    feats: str = "",
    lang: str | None = None,
) -> None:
    """Seed one chunk_lemmas row carrying the token-level ``lang``
    override (migration 0032). ``lang`` is NULL for an ordinary
    same-script token and set only for a cross-script run."""

    conn.execute(
        """
        INSERT INTO chunk_lemmas
            (chunk_id, token_index, surface_form, surface_start, surface_end,
             lemma, lemma_fold, pos, feats, lang)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chunk_id,
            token_index,
            surface,
            token_index * 10,
            token_index * 10 + len(surface),
            lemma,
            lemma.lower(),
            pos,
            feats,
            lang,
        ),
    )


@pytest.fixture
def cross_script_db(tmp_path: Path) -> sqlite3.Connection:
    """A Latin run embedded in a Greek chunk, plus the same Latin lemma
    in an ordinary Latin chunk.

    Mirrors the corpus shape #430 introduced: ``chunk_lemmas.lang`` is
    NULL for a same-script token and 'lat' for the embedded run, while
    the chunk itself stays 'grc'. The leaderboard counts the run as
    Latin (``COALESCE(cl.lang, cf.lang)``); the KWIC panel behind it
    must reach the same rows.
    """

    import json

    chunks = [
        make_chunk(
            chunk_id="grc-1",
            corpus="plato",
            author="Plato",
            work="Republic",
            lang="grc",
            section="509d",
            text="λόγος ratio λόγος",
        ),
        make_chunk(
            chunk_id="lat-1",
            corpus="cicero",
            author="Cicero",
            work="De Officiis",
            lang="lat",
            section="I.1",
            text="ratio ratio",
        ),
    ]
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(tmp_path / "cross.sqlite")
    store.insert_chunks(conn, jsonl)

    # grc-1: two Greek tokens (no override) + one Latin token tagged 'lat'
    _insert_lemma_lang(
        conn,
        chunk_id="grc-1",
        token_index=0,
        surface="λόγος",
        lemma="λόγος",
        pos="NOUN",
        feats="Case=Nom|Number=Sing",
    )
    _insert_lemma_lang(
        conn,
        chunk_id="grc-1",
        token_index=1,
        surface="ratio",
        lemma="ratio",
        pos="NOUN",
        feats="Case=Nom|Number=Sing",
        lang="lat",
    )
    _insert_lemma_lang(
        conn,
        chunk_id="grc-1",
        token_index=2,
        surface="λόγου",
        lemma="λόγος",
        pos="NOUN",
        feats="Case=Gen|Number=Sing",
    )
    # lat-1: the same Latin lemma in an ordinary Latin chunk
    _insert_lemma_lang(
        conn,
        chunk_id="lat-1",
        token_index=0,
        surface="ratio",
        lemma="ratio",
        pos="NOUN",
        feats="Case=Nom|Number=Sing",
    )
    _insert_lemma_lang(
        conn,
        chunk_id="lat-1",
        token_index=1,
        surface="rationis",
        lemma="ratio",
        pos="NOUN",
        feats="Case=Gen|Number=Sing",
    )
    conn.commit()

    from minerva.concordance import aggregate

    aggregate.build(conn)
    return conn


def _board_count(conn: sqlite3.Connection, lemma: str, lang: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(count), 0) FROM lemma_counts "
        "WHERE scope_kind='corpus' AND lemma = ? AND lang = ?",
        (lemma, lang),
    ).fetchone()
    return int(row[0])


def test_the_leaderboard_lists_the_embedded_run_under_latin(
    cross_script_db: sqlite3.Connection,
) -> None:
    """Guards the premise: without this the KWIC assertions below would
    pass for the wrong reason. #430's COALESCE is what puts it here."""

    assert _board_count(cross_script_db, "ratio", "lat") == 3
    assert _board_count(cross_script_db, "ratio", "grc") == 0


def test_kwic_reaches_the_cross_script_run_the_leaderboard_counts(
    cross_script_db: sqlite3.Connection,
) -> None:
    """#644: clicking a leaderboard cell must return its rows. The
    embedded Latin token lives in a 'grc' chunk, so a ``cf.lang = 'lat'``
    rule never sees it."""

    res = concordance_queries.lemma_detail(cross_script_db, {"lemma": "ratio", "lang": "lat"})
    assert res["total"] == _board_count(cross_script_db, "ratio", "lat")
    assert res["total"] == 3
    chunks_seen = {r["chunk_id"] for r in res["rows"]}
    assert "grc-1" in chunks_seen, "the embedded Latin run is unreachable"


def test_kwic_does_not_serve_the_latin_run_under_greek(
    cross_script_db: sqlite3.Connection,
) -> None:
    """The other half of one rule: a token overridden to 'lat' is Latin
    vocabulary everywhere, so 'grc' must not serve it either (#427)."""

    res = concordance_queries.lemma_detail(cross_script_db, {"lemma": "ratio", "lang": "grc"})
    assert res["total"] == 0
    # The Greek tokens in the same chunk are untouched.
    greek = concordance_queries.lemma_detail(cross_script_db, {"lemma": "λόγος", "lang": "grc"})
    assert greek["total"] == 2


def test_cross_script_breakdowns_match_the_leaderboard_partition(
    cross_script_db: sqlite3.Connection,
) -> None:
    """The facet counts partition on the same rule as the total."""

    res = concordance_queries.lemma_detail(cross_script_db, {"lemma": "ratio", "lang": "lat"})
    assert {b["value"]: b["count"] for b in res["pos_breakdown"]} == {"NOUN": 3}
    assert {b["value"]: b["count"] for b in res["case_breakdown"]} == {
        "Nom": 2,
        "Gen": 1,
    }
    assert {b["value"]: b["count"] for b in res["work_breakdown"]} == {
        "Republic": 1,
        "De Officiis": 2,
    }


def _aggregate_scans(conn: sqlite3.Connection, fn) -> int:
    """Run ``fn`` and count the statements that scan ``chunk_lemmas``."""

    seen: list[str] = []
    conn.set_trace_callback(seen.append)
    try:
        fn()
    finally:
        conn.set_trace_callback(None)
    return sum(1 for s in seen if "chunk_lemmas" in s)


def test_lemma_detail_reads_chunk_lemmas_twice_not_six_times(
    concordance_db: sqlite3.Connection,
) -> None:
    """#643: the total and the four breakdowns are one grouped pass, so
    one request pays the lemma seek twice — once for the aggregates and
    once for the page — not six times.

    Three statements read `chunk_lemmas` since #656, and still two seeks:
    the aggregate, the page's walk of this fixture's one work (a page that
    spans k works seeks k times, each stopping at its share of `limit`),
    and a join of the chosen rows to `chunks_full` by rowid, which seeks no
    lemma at all.

    Asserted as a statement count rather than a duration: the 428k-chunk
    corpus is not in CI, where a timing assertion would be flaky, while
    the number of scans is what makes it slow and is stable at any row
    count. Same reasoning as #642 / #646's plan tests.
    """

    n = _aggregate_scans(
        concordance_db,
        lambda: concordance_queries.lemma_detail(concordance_db, {"lemma": "haben", "lang": "deu"}),
    )
    assert n == 3, f"expected 3 reads of chunk_lemmas, saw {n}"


def test_the_empty_result_path_also_reads_chunk_lemmas_once(
    concordance_db: sqlite3.Connection,
) -> None:
    """A zero-hit request still returns unfiltered breakdowns (the F6
    "drop filter X" affordance), and must not pay a second pass for them."""

    n = _aggregate_scans(
        concordance_db,
        lambda: concordance_queries.lemma_detail(
            concordance_db,
            {"lemma": "haben", "lang": "deu", "surface": "nonexistent"},
        ),
    )
    assert n == 1, f"expected 1 read of chunk_lemmas, saw {n}"


def test_filters_narrow_the_total_while_breakdowns_stay_unfiltered(
    concordance_db: sqlite3.Connection,
) -> None:
    """The trap in consolidating the five queries: the ``COUNT(*)`` is
    filtered by pos/surface/morph and the four breakdowns deliberately
    are not — they drive the "drop this filter for N hits" affordance.
    One grouped pass has to produce both, so summing every group would
    silently widen the total.
    """

    filtered = concordance_queries.lemma_detail(
        concordance_db,
        {"lemma": "Geist", "lang": "deu", "morph": "Case=Nom"},
    )
    unfiltered = concordance_queries.lemma_detail(concordance_db, {"lemma": "Geist", "lang": "deu"})
    assert unfiltered["total"] == 4
    assert filtered["total"] == 3, "Case=Nom must narrow the total"
    assert len(filtered["rows"]) == filtered["total"], "page must match total"
    # …while the facet counts keep describing the unfiltered scope.
    assert filtered["case_breakdown"] == unfiltered["case_breakdown"]
    assert {b["value"]: b["count"] for b in filtered["case_breakdown"]} == {
        "Nom": 3,
        "Acc": 1,
    }


def test_a_surface_filter_narrows_the_total_the_same_way(
    concordance_db: sqlite3.Connection,
) -> None:
    """The surface filter is an equality on a consolidated group key,
    so it exercises the same derivation as the morph filter above."""

    res = concordance_queries.lemma_detail(
        concordance_db, {"lemma": "Geist", "lang": "deu", "surface": "Geist"}
    )
    assert res["total"] == 4
    missing = concordance_queries.lemma_detail(
        concordance_db, {"lemma": "Geist", "lang": "deu", "surface": "Geistes"}
    )
    assert missing["total"] == 0
    assert missing["pos_breakdown"], "empty state keeps its broadening hints"


def test_breakdown_ties_are_ordered_deterministically(
    concordance_db: sqlite3.Connection,
) -> None:
    """Equal counts sort by value, so the top-N is a function of the data
    rather than of the order SQLite emitted the groups in."""

    res = concordance_queries.lemma_detail(concordance_db, {"lemma": "Geist", "lang": "deu"})
    cases = res["case_breakdown"]
    assert [b["value"] for b in cases] == ["Nom", "Acc"], "count order wins"
    surfaces = concordance_queries.lemma_detail(concordance_db, {"lemma": "haben", "lang": "deu"})[
        "work_breakdown"
    ]
    values = [b["value"] for b in surfaces]
    assert values == sorted(values), "ties fall back to the value"


@pytest.fixture
def untagged_lemma_db(tmp_path: Path) -> sqlite3.Connection:
    """A lemma whose rows carry no POS and no feats.

    Legacy rows from before migration 0008 look like this, and so does
    anything the lemmatizer declined to tag. The four separate breakdown
    queries excluded them with `IS NOT NULL AND != ''`; the consolidated
    pass has to exclude them in Python instead.
    """

    import json

    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text(
        json.dumps(
            make_chunk(
                chunk_id="u-1",
                corpus="hegel",
                author="Hegel",
                work="Wissenschaft der Logik",
                lang="deu",
                text="Sein Sein Sein",
            )
        )
    )
    conn = store.open_db(tmp_path / "untagged.sqlite")
    store.insert_chunks(conn, jsonl)
    # One tagged row, two untagged ones: NULL pos/feats and empty-string
    # pos/feats, the two shapes the old SQL predicates each excluded.
    _insert_lemma_lang(
        conn,
        chunk_id="u-1",
        token_index=0,
        surface="Sein",
        lemma="Sein",
        pos="NOUN",
        feats="Case=Nom|Number=Sing",
    )
    conn.execute(
        "INSERT INTO chunk_lemmas (chunk_id, token_index, surface_form, "
        "surface_start, surface_end, lemma, lemma_fold, pos, feats) "
        "VALUES ('u-1', 1, 'Sein', 10, 14, 'Sein', 'sein', NULL, NULL)"
    )
    conn.execute(
        "INSERT INTO chunk_lemmas (chunk_id, token_index, surface_form, "
        "surface_start, surface_end, lemma, lemma_fold, pos, feats) "
        "VALUES ('u-1', 2, 'Sein', 20, 24, 'Sein', 'sein', '', '')"
    )
    conn.commit()
    from minerva.concordance import aggregate

    aggregate.build(conn)
    return conn


def test_untagged_rows_count_toward_the_total_but_not_the_facets(
    untagged_lemma_db: sqlite3.Connection,
) -> None:
    """An untagged token is still an occurrence — it just isn't a POS or
    a morphology bucket of its own. Only the work breakdown, which has no
    such predicate, counts all three."""

    res = concordance_queries.lemma_detail(untagged_lemma_db, {"lemma": "Sein", "lang": "deu"})
    assert res["total"] == 3
    assert {b["value"]: b["count"] for b in res["pos_breakdown"]} == {"NOUN": 1}
    assert {b["value"]: b["count"] for b in res["case_breakdown"]} == {"Nom": 1}
    assert {b["value"]: b["count"] for b in res["number_breakdown"]} == {"Sing": 1}
    assert res["gender_breakdown"] == [], "no row carries a Gender feature"
    assert {b["value"]: b["count"] for b in res["work_breakdown"]} == {"Wissenschaft der Logik": 3}
    # The surface guard is the same shape; all three rows carry one here.
    assert {b["value"]: b["count"] for b in res["surface_breakdown"]} == {"Sein": 3}
