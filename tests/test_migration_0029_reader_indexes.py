"""Migration 0029 must give the Reader's queries an access path (#339).

Asserting the indexes exist is not enough — an index the planner declines to
use is exactly the kind of inert guard that looks like a fix and isn't. These
tests check the query plan instead: the statements `reader.queries.work_range`
issues must SEARCH, not SCAN.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from minerva import store

# The two statements that dominated the measured 365 ms: the total/meta
# aggregate and the page fetch. Both filter on the edition pair, and the
# second also wants `ord` order — which is why `ord` is the trailing column.
META_SQL = (
    "SELECT work_id, corpus, author, work, lang, COUNT(*) AS n FROM chunks_full "
    "WHERE edition_id IS ? AND translation_id IS ? "
    "GROUP BY work_id, corpus, author, work, lang"
)
PAGE_SQL = (
    "SELECT chunk_id, section, book, page, speaker, text, ord, block_type "
    "FROM chunks_full WHERE edition_id IS ? AND translation_id IS ? "
    "ORDER BY ord LIMIT 80 OFFSET 0"
)


def _plan(conn: sqlite3.Connection, sql: str, params: tuple) -> str:
    rows = conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
    return " / ".join(str(r[-1]) for r in rows)


def test_reader_index_exists(tmp_path: Path):
    conn = store.open_db(tmp_path / "fresh.sqlite")
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}

    assert "idx_chunks_edition_ord" in names


def test_the_page_query_no_longer_scans_chunks(populated_db: sqlite3.Connection):
    """The LIMIT 80 used to scan all 428,606 rows and sort them in a temp
    B-tree to return 80, which is why limit=1 cost the same as limit=80."""

    row = populated_db.execute(
        "SELECT edition_id, translation_id FROM chunks_full LIMIT 1"
    ).fetchone()
    params = (row["edition_id"], row["translation_id"])

    plan = _plan(populated_db, PAGE_SQL, params)

    assert "idx_chunks_edition_ord" in plan, plan
    assert "SCAN c" not in plan, plan
    # The index supplies the ordering, so no sort is materialised.
    assert "TEMP B-TREE FOR ORDER BY" not in plan, plan


def test_the_total_count_no_longer_scans_chunks(populated_db: sqlite3.Connection):
    row = populated_db.execute(
        "SELECT edition_id, translation_id FROM chunks_full LIMIT 1"
    ).fetchone()
    params = (row["edition_id"], row["translation_id"])

    plan = _plan(populated_db, META_SQL, params)

    assert "idx_chunks_edition_ord" in plan, plan
    assert "SCAN c" not in plan, plan


def test_work_lookup_already_had_an_index(populated_db: sqlite3.Connection):
    """Why 0029 does not add `works(title, author)`, as #339 proposed.

    The UNIQUE (author, title) constraint already yields a covering index,
    and SQLite was already choosing it — measured at 1.0x with #339's index
    added, because the statement's cost was the `SCAN c` on chunks.

    Corrected 2026-08-12: this test used to say it "keeps the next person
    from re-adding a duplicate", and **migration 0030 adds that index.**
    Nothing above is wrong — the index is genuinely inert while chunks is
    scanned, and it is not a duplicate of this autoindex either (leading
    column `title`, not `author`). What changed is the premise: 0030's
    denormalised `chunks.work_id` removes the `SCAN c`, which promotes the
    title-without-author access path from unused to load-bearing and takes
    the author-less `resolve work_id` from 31.6 ms to 0.53 ms. What this
    test pins is the narrower and still-true claim it actually asserts —
    that the author-ful lookup needs no new index. See
    `test_migration_0030_chunks_work_id.py` for the other half.
    """

    plan = _plan(
        populated_db, "SELECT id FROM works WHERE title=? AND author=?", ("Republic", "Plato")
    )

    assert "SEARCH works USING COVERING INDEX" in plan, plan
    assert "SCAN" not in plan, plan
