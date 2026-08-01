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
from minerva.concordance import queries as concordance_queries

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
def greek_concordance_db(tmp_path: Path) -> sqlite3.Connection:
    """SQLite store with one Greek chunk + polytonic lemma cache.

    The seeded lemmas all share the *base* leading letter alpha but
    carry different precomposed diacritics / case so the diacritic-fold
    letter filter has something to prove:

      * ἄνθρωπος — smooth + acute (ἄ)
      * ἀγαθός   — smooth breathing (ἀ)
      * Ἀθηνᾶ    — capital + smooth (Ἀ)
      * λόγος    — control, leading λ → must NOT match letter=Α
    """

    chunks = [
        make_chunk(
            chunk_id="rep-1",
            corpus="plato",
            author="Plato",
            work="Respublica",
            lang="grc",
            section="327a",
            text="ἄνθρωπος ἄνθρωπος ἀγαθός ἀγαθός Ἀθηνᾶ Ἀθηνᾶ λόγος λόγος",
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
    assert lemmas == {"ἄνθρωπος", "ἀγαθός", "Ἀθηνᾶ"}
    assert "λόγος" not in lemmas
    assert out["total_lemmas"] == 3


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
