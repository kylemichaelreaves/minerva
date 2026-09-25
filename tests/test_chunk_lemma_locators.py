"""`chunk_lemmas` carries its chunk's locators — `ord`, resolved language,
`work_id` — so the KWIC endpoint can answer from an index (#649).

Measured on the live index before this change: `lemma_detail` for `der`/deu
cost 1,627 ms, and a `COUNT(*)` over its page query's join cost the same as the
page query itself. The time was the per-row probe into `chunks` for `lang`,
`ord` and `work`, paid for all 671,411 matching rows before any was discarded,
not the sort #649 first blamed.

Copying the three values onto `chunk_lemmas` is a denormalisation, and the
danger it creates is specific: `index --reset` renumbers `chunks.ord` and
reassigns `works.id`, then bulk-restores `chunk_lemmas` by `chunk_id` from a
snapshot. A restored row keeps a valid `chunk_id` and stale locators, joins
fine, and silently returns KWIC rows in the wrong order, the wrong work, or not
at all. Most of these tests are about that path, not the fast one.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from conftest import make_chunk

from minerva import store
from minerva.cli.index_cmd import cmd_index
from minerva.concordance import queries as concordance_queries

_DRIFT_SQL = """
SELECT COUNT(*) FROM chunk_lemmas cl JOIN chunks c ON c.chunk_id = cl.chunk_id
WHERE cl.chunk_ord IS NOT c.ord
   OR cl.lang_resolved IS NOT COALESCE(cl.lang, c.lang)
   OR cl.work_id IS NOT c.work_id
"""


def _write_jsonl(path: Path, chunks: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(c) for c in chunks))
    return path


def _run_index(db: Path, jsonl: Path, *, reset: bool) -> None:
    assert cmd_index(argparse.Namespace(db=db, input=jsonl, reset=reset)) == 0


def _plant_lemmas(db: Path, rows: list[tuple[str, int, str]]) -> None:
    """Write `chunk_lemmas` the way every test fixture and the pre-#649
    lemmatize writer did: without naming the locator columns at all."""

    conn = store.open_db(db)
    try:
        conn.executemany(
            "INSERT INTO chunk_lemmas "
            "(chunk_id, token_index, surface_form, surface_start, surface_end, "
            " lemma, lemma_fold) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(cid, i, w, i * 10, i * 10 + len(w), w, w.lower()) for cid, i, w in rows],
        )
        conn.commit()
    finally:
        conn.close()


def _drift(db: Path) -> int:
    conn = store.open_db(db)
    try:
        return conn.execute(_DRIFT_SQL).fetchone()[0]
    finally:
        conn.close()


def test_a_lemma_row_inherits_its_chunks_locators(tmp_path: Path) -> None:
    db = tmp_path / "loc.sqlite"
    _run_index(
        db,
        _write_jsonl(
            tmp_path / "a.jsonl",
            [
                make_chunk(chunk_id="a", work="Republic", text="alpha beta"),
                make_chunk(chunk_id="b", work="Republic", text="gamma delta"),
            ],
        ),
        reset=False,
    )
    _plant_lemmas(db, [("a", 0, "alpha"), ("b", 0, "gamma")])

    conn = store.open_db(db)
    try:
        got = conn.execute(
            "SELECT cl.chunk_id, cl.chunk_ord, cl.lang_resolved, cl.work_id, "
            "       c.ord, c.lang, c.work_id "
            "FROM chunk_lemmas cl JOIN chunks c ON c.chunk_id = cl.chunk_id "
            "ORDER BY cl.chunk_id"
        ).fetchall()
    finally:
        conn.close()
    assert [tuple(r[1:4]) for r in got] == [tuple(r[4:7]) for r in got]
    assert all(r[1] is not None and r[3] is not None for r in got)


def test_a_cross_script_row_resolves_to_its_own_language(tmp_path: Path) -> None:
    """`chunk_lemmas.lang` is a sparse override (#430): a Latin phrase inside
    a Greek chunk carries `lat`, every ordinary row carries NULL. The resolved
    language is the override when there is one."""

    db = tmp_path / "xs.sqlite"
    _run_index(
        db,
        _write_jsonl(tmp_path / "x.jsonl", [make_chunk(chunk_id="g", lang="grc", text="λόγος et")]),
        reset=False,
    )
    conn = store.open_db(db)
    try:
        conn.executemany(
            "INSERT INTO chunk_lemmas (chunk_id, token_index, surface_form, "
            "surface_start, surface_end, lemma, lemma_fold, lang) VALUES (?,?,?,?,?,?,?,?)",
            [
                ("g", 0, "λόγος", 0, 5, "λόγος", "λόγος", None),
                ("g", 1, "et", 6, 8, "et", "et", "lat"),
            ],
        )
        conn.commit()
        got = conn.execute(
            "SELECT surface_form, lang_resolved FROM chunk_lemmas ORDER BY token_index"
        ).fetchall()
    finally:
        conn.close()
    assert [tuple(r) for r in got] == [("λόγος", "grc"), ("et", "lat")]


def test_locators_follow_a_reset_that_renumbers_ord_and_reassigns_work_ids(
    tmp_path: Path,
) -> None:
    """The failure this whole mechanism exists to prevent.

    The second ingest puts a new work first (so every `works.id` moves) and a
    new chunk at the front of the old work (so every `ord` moves). The planted
    lemma rows are restored from the pre-index snapshot with the values they
    had before, and must come out matching the new `chunks`."""

    db = tmp_path / "reset.sqlite"
    first = [
        make_chunk(chunk_id="r1", work="Republic", section="1", text="justice first"),
        make_chunk(chunk_id="r2", work="Republic", section="2", text="justice second"),
    ]
    _run_index(db, _write_jsonl(tmp_path / "1.jsonl", first), reset=False)
    _plant_lemmas(db, [("r1", 0, "justice"), ("r2", 0, "justice")])

    conn = store.open_db(db)
    before = dict(conn.execute("SELECT chunk_id, chunk_ord FROM chunk_lemmas").fetchall())
    before_work = conn.execute("SELECT DISTINCT work_id FROM chunk_lemmas").fetchone()[0]
    conn.close()

    second = [
        make_chunk(chunk_id="s1", work="Symposium", section="1", text="eros"),
        make_chunk(chunk_id="r0", work="Republic", section="0", text="a new opening"),
        *first,
    ]
    _run_index(db, _write_jsonl(tmp_path / "2.jsonl", second), reset=True)

    conn = store.open_db(db)
    try:
        after = dict(conn.execute("SELECT chunk_id, chunk_ord FROM chunk_lemmas").fetchall())
        after_work = conn.execute("SELECT DISTINCT work_id FROM chunk_lemmas").fetchone()[0]
    finally:
        conn.close()
    # Preconditions: the reset really did move both values, or this test
    # would pass against a trigger that never fires.
    assert after != before, "ord did not change; the fixture no longer exercises the reset"
    assert after_work != before_work, "work_id did not change; same"
    assert _drift(db) == 0


def test_locators_follow_an_incremental_reindex(tmp_path: Path) -> None:
    """`--corpora` re-inserts one corpus's chunks with `INSERT OR REPLACE`,
    which renumbers `ord` for that corpus without touching the lemma rows."""

    db = tmp_path / "inc.sqlite"
    first = [make_chunk(chunk_id="p1", section="1", text="one")]
    _run_index(db, _write_jsonl(tmp_path / "1.jsonl", first), reset=False)
    _plant_lemmas(db, [("p1", 0, "one")])

    second = [make_chunk(chunk_id="p0", section="0", text="zero"), *first]
    jsonl = _write_jsonl(tmp_path / "2.jsonl", second)
    assert (
        cmd_index(
            argparse.Namespace(db=db, input=jsonl, reset=False, incremental=True, corpora="plato")
        )
        == 0
    )
    assert _drift(db) == 0


def test_migration_backfills_rows_written_before_it(tmp_path: Path) -> None:
    """An established index gets its locators from the migration itself, not
    from the next ingest. Undo the migration, then let `open_db` redo it."""

    db = tmp_path / "mig.sqlite"
    _run_index(
        db,
        _write_jsonl(tmp_path / "m.jsonl", [make_chunk(chunk_id="m", text="mind")]),
        reset=False,
    )
    _plant_lemmas(db, [("m", 0, "mind")])

    conn = store.open_db(db)
    for kind, name in (
        ("TRIGGER", "chunk_lemmas_locators_ai"),
        ("TRIGGER", "chunk_lemmas_lang_au"),
        ("TRIGGER", "chunks_locators_ai"),
        ("TRIGGER", "chunks_locators_au"),
        ("INDEX", "chunk_lemmas_by_locator"),
        ("INDEX", "chunk_lemmas_by_facet"),
    ):
        conn.execute(f"DROP {kind} {name}")
    for col in ("chunk_ord", "lang_resolved", "work_id"):
        conn.execute(f"ALTER TABLE chunk_lemmas DROP COLUMN {col}")
    conn.execute("DELETE FROM schema_migrations WHERE version = ?", (36,))
    conn.commit()
    conn.close()

    # `open_db` re-runs the migration; the row planted before it must come
    # out populated, not merely not-drifted (a NULL on both sides would be).
    conn = store.open_db(db)
    try:
        assert conn.execute("SELECT chunk_ord FROM chunk_lemmas").fetchone()[0] is not None
        assert conn.execute(_DRIFT_SQL).fetchone()[0] == 0
    finally:
        conn.close()


# ── The read path ──────────────────────────────────────────────────


def _kwic_plans(conn: sqlite3.Connection, query: dict[str, str]) -> list[str]:
    """Run `lemma_detail` and return the query plan of every statement it
    issued against `chunk_lemmas`, one string per statement."""

    seen: list[str] = []
    conn.set_trace_callback(seen.append)
    try:
        concordance_queries.lemma_detail(conn, query)
    finally:
        conn.set_trace_callback(None)
    return [
        " | ".join(r[-1] for r in conn.execute("EXPLAIN QUERY PLAN " + sql).fetchall())
        for sql in seen
        if "chunk_lemmas" in sql
    ]


def _kwic_db(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "kwic.sqlite"
    _run_index(
        db,
        _write_jsonl(
            tmp_path / "k.jsonl",
            [
                make_chunk(chunk_id=f"k{i}", section=str(i), lang="deu", text="haben haben")
                for i in range(6)
            ],
        ),
        reset=False,
    )
    _plant_lemmas(db, [(f"k{i}", t, "haben") for i in range(6) for t in range(2)])
    return store.open_db(db)


def test_the_kwic_aggregate_never_probes_chunks(tmp_path: Path) -> None:
    """The breakdowns visit every matching row by design, so the per-row probe
    into `chunks` is the whole cost: 1,176 ms of `der`'s 1,627. Asserted on the
    plan rather than a duration, as #643's statement-count test is."""

    conn = _kwic_db(tmp_path)
    try:
        agg, _page = _kwic_plans(conn, {"lemma": "haben", "lang": "deu"})
    finally:
        conn.close()
    assert "COVERING INDEX" in agg, agg
    assert "chunks" not in agg.replace("chunk_lemmas", ""), agg


def test_the_kwic_page_walks_an_index_in_order(tmp_path: Path) -> None:
    """The walk that picks the page needs no sort, so it stops after `limit`
    index entries instead of visiting every matching row — for a work scope
    too. The plan's `CO-ROUTINE p` block is that walk; whatever follows
    `SCAN p` handles only the `limit` rows it produced, and re-sorting those
    is cheap and required (a subquery's row order is not guaranteed)."""

    conn = _kwic_db(tmp_path)
    try:
        for query in (
            {"lemma": "haben", "lang": "deu"},
            {"lemma": "haben", "lang": "deu", "scope": "work", "work": "Republic"},
        ):
            _agg, page = _kwic_plans(conn, {**query, "limit": "2"})
            walk = page.split("SCAN p")[0]
            assert "COVERING INDEX chunk_lemmas_by_locator" in walk, page
            assert "TEMP B-TREE" not in walk, page
    finally:
        conn.close()


def test_kwic_pages_are_a_total_order_across_works(tmp_path: Path) -> None:
    """`ord` restarts at 0 in every work, so `(ord, surface_start)` ties across
    works. The page order must break the tie deterministically, or an offset
    boundary can serve one row twice and its partner never (#371's reasoning)."""

    db = tmp_path / "ties.sqlite"
    _run_index(
        db,
        _write_jsonl(
            tmp_path / "t.jsonl",
            [
                make_chunk(chunk_id=f"{w}{i}", work=w, section=str(i), lang="deu", text="sein")
                for w in ("A", "B", "C")
                for i in range(2)
            ],
        ),
        reset=False,
    )
    _plant_lemmas(db, [(f"{w}{i}", 0, "sein") for w in ("A", "B", "C") for i in range(2)])
    conn = store.open_db(db)
    try:
        whole = [
            r["chunk_id"]
            for r in concordance_queries.lemma_detail(
                conn, {"lemma": "sein", "lang": "deu", "limit": "6"}
            )["rows"]
        ]
        paged = [
            r["chunk_id"]
            for off in range(6)
            for r in concordance_queries.lemma_detail(
                conn, {"lemma": "sein", "lang": "deu", "limit": "1", "offset": str(off)}
            )["rows"]
        ]
    finally:
        conn.close()
    assert sorted(whole) == sorted(f"{w}{i}" for w in "ABC" for i in range(2))
    assert paged == whole


def test_the_reset_restore_writes_locators_itself(tmp_path: Path) -> None:
    """The restore must not lean on the `chunks` triggers.

    It used to run before `insert_chunks`, so every restored row arrived with
    the snapshot's locators and every chunk insert then rewrote its lemma rows
    — 26.1M rows whose `work_id` and `ord` sit in two indexes. Measured on a
    clone, rewriting `work_id` alone under those indexes was stopped after
    more than five minutes, on a `--reset` main completes in 8 m 31 s.
    Restoring after the insert, joined to the new `chunks`, writes each row
    once with the right values.

    Proven here with the triggers gone: if the restore relied on them, the
    locators would come back stale."""

    from minerva.store.preserved_state import restore_chunk_lemmas_from_snapshot

    db = tmp_path / "restore.sqlite"
    first = [make_chunk(chunk_id="r1", work="Republic", section="1", text="justice")]
    _run_index(db, _write_jsonl(tmp_path / "1.jsonl", first), reset=False)
    _plant_lemmas(db, [("r1", 0, "justice")])
    backup = db.with_suffix(db.suffix + ".bak.pre-index")
    src = sqlite3.connect(db)
    dst = sqlite3.connect(backup)
    src.backup(dst)
    src.close()
    dst.close()

    conn = store.open_db(db)
    try:
        conn.execute("DELETE FROM chunk_lemmas")
        for name in ("chunk_lemmas_locators_ai", "chunks_locators_ai", "chunks_locators_au"):
            conn.execute(f"DROP TRIGGER {name}")
        # A new work ahead of the old one moves its `works.id`; a new first
        # chunk moves its `ord`. Written straight to the tables, as
        # `insert_chunks` would, with nothing to propagate them.
        conn.execute(
            "INSERT INTO works (id, author, title, original_language, citation_system) "
            "SELECT id + 7, author, title || ' (moved)', original_language, citation_system "
            "FROM works"
        )
        conn.execute("UPDATE chunks SET ord = ord + 5, work_id = work_id + 7")
        conn.commit()

        restored = restore_chunk_lemmas_from_snapshot(conn, db)
        drift = conn.execute(_DRIFT_SQL).fetchone()[0]
        n = conn.execute("SELECT COUNT(*) FROM chunk_lemmas").fetchone()[0]
    finally:
        conn.close()
    assert (restored, n, drift) == (1, 1, 0)


def test_the_reset_restore_leaves_both_kwic_indexes_in_place(tmp_path: Path) -> None:
    """The restore drops the two KWIC indexes for its bulk copy and rebuilds
    them afterwards, because 26.1M inserts in `chunk_id` order into two
    lemma-keyed B-trees took a full `--reset` from 8 m 31 s to 26 m 01 s on a
    clone. A restore that forgot the rebuild would leave the endpoint on a
    full scan with every test of its results still green — so the indexes
    are asserted here, by name and by the plan that needs them."""

    db = tmp_path / "rebuild.sqlite"
    first = [make_chunk(chunk_id="i1", lang="deu", text="haben")]
    _run_index(db, _write_jsonl(tmp_path / "1.jsonl", first), reset=False)
    _plant_lemmas(db, [("i1", 0, "haben")])
    _run_index(db, _write_jsonl(tmp_path / "1.jsonl", first), reset=True)

    conn = store.open_db(db)
    try:
        names = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'chunk_lemmas'"
            )
        }
        agg, page = _kwic_plans(conn, {"lemma": "haben", "lang": "deu"})
    finally:
        conn.close()
    assert {"chunk_lemmas_by_locator", "chunk_lemmas_by_facet"} <= names
    assert "COVERING INDEX chunk_lemmas_by_facet" in agg, agg
    assert "COVERING INDEX chunk_lemmas_by_locator" in page, page
