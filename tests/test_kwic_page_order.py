"""KWIC page order and access path across works (#656, #657).

#656: a corpus- or author-scope page was ordered by `chunk_ord`, the chunk's
position *within its own work*, so page 1 of `der`/deu was the opening
paragraph of 47 unrelated works interleaved. The page now reads works in the
Reader's order (author chronology, then canon or title) and each work in its
own paragraph order.

#657: a selective `pos`/`surface`/`morph` filter walked every index entry for
the lemma, checking each on its table row, until it found `limit` matches —
361 ms for 37 matches of `der`. The filtered total is known before the page
query runs, so the page switches to `chunk_lemmas_by_facet` when the walk
would be long.

Every ordering test checks against `_oracle`, a brute-force sort of the lemma
rows in Python, so the SQL is tested against an independent statement of the
order rather than against itself.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pytest
from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index
from minerva.concordance import kwic_queries
from minerva.concordance import queries as concordance_queries
from minerva.reader.queries import work_sort_key

# Hegel (910) comes after Plato (400) chronologically but `Hegel` < `Plato`
# alphabetically, and within Luther Bibel 1912 the canon puts Genesis before
# Exodus although `Exodus` < `Genesis` — so each tie-break the order relies on
# is one alphabetical or id order would get wrong.
_WORKS = [
    ("Hegel", "Logik", 3),
    ("Plato", "Politeia", 3),
    ("Luther Bibel 1912", "Exodus", 2),
    ("Luther Bibel 1912", "Genesis", 2),
]


# Registered corpus ids: the ingest write path rejects an unknown one (#498).
_CORPUS = {"Hegel": "hegel", "Plato": "plato", "Luther Bibel 1912": "luther_1912"}


def _build(tmp_path: Path, rows_per_chunk: int = 2) -> sqlite3.Connection:
    """One German chunk per (work, i), each carrying `rows_per_chunk` tokens
    of lemma `der`: token 0 is DET, token 1 is PRON (Case=Gen)."""

    chunks = [
        make_chunk(
            chunk_id=f"{work}-{i}",
            corpus=_CORPUS[author],
            author=author,
            work=work,
            lang="deu",
            section=str(i),
            text="der der",
        )
        for author, work, n in _WORKS
        for i in range(n)
    ]
    db = tmp_path / "order.sqlite"
    jsonl = tmp_path / "order.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    assert cmd_index(argparse.Namespace(db=db, input=jsonl, reset=False)) == 0
    conn = store.open_db(db)
    conn.executemany(
        "INSERT INTO chunk_lemmas (chunk_id, token_index, surface_form, surface_start, "
        " surface_end, lemma, lemma_fold, pos, feats) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (c["chunk_id"], t, "der", t * 4, t * 4 + 3, "der", "der", pos, feats)
            for c in chunks
            for t, (pos, feats) in enumerate(
                [("DET", "Case=Nom"), ("PRON", "Case=Gen")][:rows_per_chunk]
            )
        ],
    )
    conn.commit()
    return conn


def _oracle(conn: sqlite3.Connection, where: str = "1=1") -> list[tuple[str, str]]:
    """Every matching row, as (chunk_id, pos) — unique per row in these
    fixtures — in the order #656 asks for: the Reader's work order, then
    paragraph order, then position in the paragraph."""

    rows = conn.execute(
        f"""SELECT cl.chunk_id, cl.surface_start, cl.chunk_ord, cl.rowid, w.author, w.title,
                   cl.pos
            FROM chunk_lemmas cl JOIN works w ON w.id = cl.work_id
            WHERE cl.lemma_fold = 'der' AND {where}"""
    ).fetchall()
    rows.sort(key=lambda r: (work_sort_key(r[4], r[5]), r[2], r[1], r[3]))
    return [(r[0], r[6]) for r in rows]


def _page_ids(conn: sqlite3.Connection, **extra: str) -> list[str]:
    out = concordance_queries.lemma_detail(conn, {"lemma": "der", "lang": "deu", **extra})
    return [r["chunk_id"] for r in out["rows"]]


# ── #656: the order ─────────────────────────────────────────────────


def test_corpus_page_reads_works_in_reader_order(tmp_path: Path) -> None:
    conn = _build(tmp_path)
    try:
        got = _page_ids(conn, limit="200")
        want = [cid for cid, _ in _oracle(conn)]
    finally:
        conn.close()
    assert got == want
    # Spelled out once, so the oracle is not the only statement of it.
    assert got[0].startswith("Politeia-0")
    assert [c.split("-")[0] for c in got[::2]] == (
        ["Politeia"] * 3 + ["Genesis"] * 2 + ["Exodus"] * 2 + ["Logik"] * 3
    )


def test_page_one_is_not_every_works_opening_paragraph(tmp_path: Path) -> None:
    """The symptom #656 was filed on: page 1 of `der` was 50 `ord`-0 rows from
    47 works. With four works of 2-3 paragraphs, a 4-row page used to be four
    opening paragraphs; now it is the first work's first two paragraphs."""

    conn = _build(tmp_path)
    try:
        got = _page_ids(conn, limit="4")
    finally:
        conn.close()
    assert got == ["Politeia-0", "Politeia-0", "Politeia-1", "Politeia-1"]


@pytest.mark.parametrize("limit", [1, 3, 4, 7])
def test_paging_crosses_work_boundaries_without_loss_or_repeat(tmp_path: Path, limit: int) -> None:
    conn = _build(tmp_path)
    try:
        want = _oracle(conn)
        pages: list[tuple[str, str]] = []
        offset = 0
        while True:
            out = concordance_queries.lemma_detail(
                conn,
                {"lemma": "der", "lang": "deu", "limit": str(limit), "offset": str(offset)},
            )
            pages += [(r["chunk_id"], r["pos"]) for r in out["rows"]]
            if out["next_offset"] is None:
                break
            offset = out["next_offset"]
    finally:
        conn.close()
    assert pages == want


def test_author_scope_keeps_its_works_in_canon_order(tmp_path: Path) -> None:
    conn = _build(tmp_path)
    try:
        got = _page_ids(conn, scope="author", author="Luther Bibel 1912", limit="50")
    finally:
        conn.close()
    assert [c.split("-")[0] for c in got[::2]] == ["Genesis"] * 2 + ["Exodus"] * 2


def test_filtered_page_keeps_the_order(tmp_path: Path) -> None:
    conn = _build(tmp_path)
    try:
        got = _page_ids(conn, pos="PRON", limit="200", offset="2")
        want = [cid for cid, _ in _oracle(conn, "cl.pos = 'PRON'")][2:]
    finally:
        conn.close()
    assert got == want


# ── #657: the access path ───────────────────────────────────────────


def _page_plans(conn: sqlite3.Connection, query: dict[str, str]) -> list[str]:
    """Plans of the statements that choose the page's rows — every statement
    after the aggregate pass that reads `chunk_lemmas` without joining it."""

    seen: list[str] = []
    conn.set_trace_callback(seen.append)
    try:
        concordance_queries.lemma_detail(conn, query)
    finally:
        conn.set_trace_callback(None)
    chooser = [s for s in seen[1:] if "chunk_lemmas" in s and "chunks_full" not in s]
    return [
        " | ".join(r[-1] for r in conn.execute("EXPLAIN QUERY PLAN " + s).fetchall())
        for s in chooser
    ]


def _build_skewed(tmp_path: Path) -> sqlite3.Connection:
    """`der` 600 times as DET across one long work, 3 times as NOUN near its
    end — #657's shape, where the walk visits almost everything to find a
    handful of matches."""

    chunks = [
        make_chunk(
            chunk_id=f"s{i}",
            work="Lang",
            author="Hegel",
            lang="deu",
            section=str(i),
            text="der " * 3,
        )
        for i in range(200)
    ]
    db = tmp_path / "skew.sqlite"
    jsonl = tmp_path / "skew.jsonl"
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    assert cmd_index(argparse.Namespace(db=db, input=jsonl, reset=False)) == 0
    conn = store.open_db(db)
    rows = [(f"s{i}", t, "DET") for i in range(200) for t in range(3)]
    rows[-3:] = [(cid, t, "NOUN") for cid, t, _ in rows[-3:]]
    conn.executemany(
        "INSERT INTO chunk_lemmas (chunk_id, token_index, surface_form, surface_start, "
        " surface_end, lemma, lemma_fold, pos, feats) VALUES (?, ?, 'der', ?, ?, 'der', 'der', ?, '')",
        [(cid, t, t * 4, t * 4 + 3, pos) for cid, t, pos in rows],
    )
    conn.commit()
    return conn


def test_a_rare_filter_is_answered_from_the_facet_index(tmp_path: Path) -> None:
    conn = _build_skewed(tmp_path)
    try:
        plans = _page_plans(conn, {"lemma": "der", "lang": "deu", "pos": "NOUN"})
        got = _page_ids(conn, pos="NOUN")
        want = [cid for cid, _ in _oracle(conn, "cl.pos = 'NOUN'")]
    finally:
        conn.close()
    assert len(plans) == 1, plans
    assert "chunk_lemmas_by_facet" in plans[0] and "pos=?" in plans[0], plans
    assert got == want == ["s199"] * 3


def test_a_common_filter_still_walks_the_locator_index(tmp_path: Path) -> None:
    conn = _build_skewed(tmp_path)
    try:
        plans = _page_plans(conn, {"lemma": "der", "lang": "deu", "pos": "DET", "limit": "5"})
        got = _page_ids(conn, pos="DET", limit="5")
        want = [cid for cid, _ in _oracle(conn, "cl.pos = 'DET'")][:5]
    finally:
        conn.close()
    assert plans and all("chunk_lemmas_by_locator" in p for p in plans), plans
    assert got == want


def _build_skewed_counted(tmp_path: Path) -> sqlite3.Connection:
    """`_build_skewed`, with `lemma_counts` built over it as `lemmatize` does."""

    from minerva.concordance import aggregate

    conn = _build_skewed(tmp_path)
    aggregate.build(conn)
    return conn


@pytest.mark.parametrize(
    "scope", [{"scope": "author", "author": "Hegel"}, {"scope": "work", "work": "Lang"}]
)
def test_a_scoped_rare_filter_is_answered_from_the_facet_index(
    tmp_path: Path, scope: dict[str, str]
) -> None:
    """#665: a scoped request's groups count only in-scope rows, so they cannot
    size a facet range that spans every work, and a scoped rare filter always
    walked. The corpus-wide size is in `lemma_counts`."""

    conn = _build_skewed_counted(tmp_path)
    try:
        query = {"lemma": "der", "lang": "deu", "pos": "NOUN", **scope}
        plans = _page_plans(conn, query)
        got = _page_ids(conn, pos="NOUN", **scope)
    finally:
        conn.close()
    assert len(plans) == 1, plans
    assert "chunk_lemmas_by_facet" in plans[0] and "pos=?" in plans[0], plans
    assert got == ["s199"] * 3


def test_a_scoped_common_filter_still_walks(tmp_path: Path) -> None:
    conn = _build_skewed_counted(tmp_path)
    try:
        query = {
            "lemma": "der",
            "lang": "deu",
            "pos": "DET",
            "limit": "5",
            "scope": "author",
            "author": "Hegel",
        }
        plans = _page_plans(conn, query)
    finally:
        conn.close()
    assert plans and all("chunk_lemmas_by_locator" in p for p in plans), plans


def test_the_corpus_facet_range_is_sized_from_lemma_counts(tmp_path: Path) -> None:
    """Sized to the row, under the KWIC match's own fold: SQL `LOWER` is
    ASCII-only, so `Der` joins `der`'s range and an `Ä`-variant would not."""

    conn = _build_skewed_counted(tmp_path)
    try:
        size = kwic_queries._corpus_facet_range
        assert size(conn, "deu", "der", pos=None) == 600
        assert size(conn, "deu", "DER", pos="NOUN") == 3
        assert size(conn, "deu", "der", pos="VERB") == 0
        assert size(conn, "grc", "der", pos=None) == 0
    finally:
        conn.close()


def test_a_scoped_filter_without_lemma_counts_still_answers(tmp_path: Path) -> None:
    """Before the first `aggregate.build` the table is empty. The range is then
    sized from the scope's own groups, a lower bound, and the rows are right
    whichever path that picks."""

    conn = _build_skewed(tmp_path)
    try:
        got = _page_ids(conn, pos="NOUN", scope="author", author="Hegel")
    finally:
        conn.close()
    assert got == ["s199"] * 3


def test_the_facet_path_honours_offset_and_morph(tmp_path: Path) -> None:
    conn = _build(tmp_path)
    try:
        got = _page_ids(conn, morph="Case=Gen", offset="3", limit="4")
        want = [cid for cid, _ in _oracle(conn, "cl.feats LIKE '%Case=Gen%'")][3:7]
        # And the same rows when the path is forced either way.
        forced = {
            use_facet: _forced(conn, use_facet, morph="Case=Gen", offset="3", limit="4")
            for use_facet in (True, False)
        }
    finally:
        conn.close()
    assert got == want
    assert forced[True] == forced[False] == want


def _forced(conn: sqlite3.Connection, use_facet: bool, **extra: str) -> list[str]:
    original = kwic_queries._prefer_facet
    kwic_queries._prefer_facet = lambda *a, **k: use_facet  # type: ignore[assignment]
    try:
        return _page_ids(conn, **extra)
    finally:
        kwic_queries._prefer_facet = original  # type: ignore[assignment]


@pytest.mark.parametrize(
    ("matches", "walked", "scanned", "expected"),
    [
        # #657's case, measured on the live index: 37 of 671,411 → facet.
        (37, 671_411, 37, True),
        # `surface=Der`: 10,438 matches walk ~3.2k entries → keep walking.
        (10_438, 3_216, 671_411, False),
        # `pos=PRON`: 85,934 matches, a 390-entry walk → keep walking.
        (85_934, 390, 85_934, False),
        # `Case=Gen`: 149,225 matches, a 225-entry walk → keep walking.
        (149_225, 225, 671_411, False),
    ],
)
def test_the_cost_rule_on_measured_shapes(
    matches: int, walked: int, scanned: int, expected: bool
) -> None:
    assert kwic_queries._prefer_facet(matches=matches, walked=walked, scanned=scanned) is expected


# ── migration 0038 ──────────────────────────────────────────────────


def _index_columns(conn: sqlite3.Connection) -> list[str]:
    return [r[2] for r in conn.execute("PRAGMA index_info(chunk_lemmas_by_locator)")]


def test_migration_0038_rebuilds_the_0036_column_order(tmp_path: Path) -> None:
    """An index built by #649's migration has `chunk_ord` ahead of `work_id`;
    0038 must rebuild it, or the per-work walk seeks nothing and every page
    falls back to a scan with its results still correct — green and slow."""

    import importlib

    mod = importlib.import_module("minerva.migrations.0038_kwic_locator_work_first")
    conn = _build(tmp_path)
    try:
        conn.execute("DROP INDEX chunk_lemmas_by_locator")
        conn.execute(
            "CREATE INDEX chunk_lemmas_by_locator ON chunk_lemmas"
            "(lemma_fold, lang_resolved, chunk_ord, surface_start, work_id)"
        )
        mod.apply(conn)
        assert _index_columns(conn) == [
            "lemma_fold",
            "lang_resolved",
            "work_id",
            "chunk_ord",
            "surface_start",
        ]
        # And re-running over the new shape leaves it alone.
        root = conn.execute(
            "SELECT rootpage FROM sqlite_master WHERE name = 'chunk_lemmas_by_locator'"
        ).fetchone()[0]
        mod.apply(conn)
        assert (
            conn.execute(
                "SELECT rootpage FROM sqlite_master WHERE name = 'chunk_lemmas_by_locator'"
            ).fetchone()[0]
            == root
        )
    finally:
        conn.close()


def test_an_offset_past_the_end_returns_no_rows(tmp_path: Path) -> None:
    conn = _build(tmp_path)
    try:
        out = concordance_queries.lemma_detail(
            conn, {"lemma": "der", "lang": "deu", "offset": "999"}
        )
    finally:
        conn.close()
    assert out["total"] == 20
    assert out["rows"] == []
    assert out["next_offset"] is None


# ── the shared work order ───────────────────────────────────────────


def test_work_sort_key_orders_each_canon_by_its_own_sequence() -> None:
    """The Reader's order, now also the KWIC page's: chronology first, then
    each scripture's own canon, then titles for everyone else."""

    ordered = [
        ("Hebrew Bible", "Genesis"),
        ("Hebrew Bible", "Exodus"),  # Tanakh canon, not alphabetical
        ("Plato", "Politeia"),
        ("Quran", "Al-Fatiha"),  # unmatched surah name → after the matched ones
        ("Luther Bibel 1912", "Genesis"),
        ("Luther Bibel 1912", "Exodus"),  # BCV canon
        ("Hegel", "Logik"),
        ("Unlisted A", "Same"),  # unlisted authors tie on ordinal and title...
        ("Unlisted B", "Same"),  # ...and the author name breaks it
    ]
    quran = [("Quran", "Aal-Imran"), ("Quran", "Abasa")]  # surah 3, surah 80
    everything = ordered + quran
    got = sorted(everything, key=lambda aw: work_sort_key(*aw))
    assert got.index(("Hebrew Bible", "Genesis")) < got.index(("Hebrew Bible", "Exodus"))
    assert got.index(("Luther Bibel 1912", "Genesis")) < got.index(("Luther Bibel 1912", "Exodus"))
    assert got.index(("Quran", "Aal-Imran")) < got.index(("Quran", "Abasa"))
    assert got.index(("Quran", "Abasa")) < got.index(("Quran", "Al-Fatiha"))
    assert got.index(("Plato", "Politeia")) < got.index(("Quran", "Aal-Imran"))
    assert got.index(("Hegel", "Logik")) < got.index(("Unlisted A", "Same"))
    assert got.index(("Unlisted A", "Same")) < got.index(("Unlisted B", "Same"))
