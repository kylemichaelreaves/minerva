"""Migration 0030 denormalises `works.id` onto `chunks` (#339 part 2).

Migration 0029 gave the Reader an access path keyed on the edition pair, but
three statements still full-scanned `chunks` because `chunks_full` reached
`works` through `JOIN works w ON w.id = COALESCE(e.work_id, t.work_id)` — an
expression join no index on `chunks` can serve. Measured on the live index
with 0029 in place: `resolve work_id` 72.4 ms, `_default_edition` 80.4 ms,
`sibling editions` 19.1 ms.

As in 0029's tests, asserting the column and index exist is not enough — an
index the planner declines to use is the inert-guard failure mode. These
check the query plan, the row-level correctness of the backfill, and the two
properties that are easy to get wrong and invisible afterwards:

* the migration must not churn the FTS index (the `chunks_au` trigger fires
  on an UPDATE that touches neither `text` nor `text_norm`), and
* the ingest path must populate the column, because `chunks_full` now joins
  `works` on it — a chunk with a NULL `work_id` does not merely lose its
  title, it disappears from every reader and search query.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from minerva import migrations, store

# The pre-0030 view, reconstructed so a test can undo the migration and watch
# it run again. Differs from today's only in the last line.
_PRE_0030_VIEW = """
CREATE VIEW chunks_full AS
SELECT
    c.chunk_id, c.lang, c.section, c.book, c.page, c.speaker,
    c.source_file, c.text, c.ord, c.block_type,
    c.edition_id, c.translation_id,
    w.id      AS work_id,
    w.author  AS author,
    w.title   AS work,
    LOWER(w.author) AS corpus,
    COALESCE(e.name, t.translator_name) AS translator,
    COALESCE(e.year, t.year)            AS edition_year,
    CASE WHEN c.edition_id IS NOT NULL THEN 1 ELSE 0 END AS is_original
FROM chunks c
LEFT JOIN editions     e ON e.id = c.edition_id
LEFT JOIN translations t ON t.id = c.translation_id
JOIN works w ON w.id = COALESCE(e.work_id, t.work_id)
"""

# `reader.window.fetch_chunk_ids_in_window` — the query both companion maps
# issue, measured at 79.9 ms with 0029 alone.
WINDOW_SQL = (
    "SELECT chunk_id FROM chunks_full WHERE work_id = ? AND lang = ? ORDER BY ord LIMIT ? OFFSET ?"
)

# `reader.queries._default_edition` — the most expensive statement left on
# the reader path at 80.4 ms, and the one #339 predicted 0029 would fix.
DEFAULT_EDITION_SQL = (
    "SELECT cf.edition_id, cf.translation_id, cf.edition_year AS yr, "
    "       COALESCE(e.is_canonical, 0) AS canon "
    "FROM chunks_full cf "
    "LEFT JOIN editions e ON e.id = cf.edition_id "
    "WHERE cf.work_id = ? AND cf.lang = ? "
    "GROUP BY cf.edition_id, cf.translation_id"
)

# `reader.queries.work_range`'s first statement.
#
# It has two shapes, and they behave differently: `author` is optional on the
# reader route ("so pre-existing bookmarks keep working", routing.ts), and
# without it the planner cannot pin a single `works` row from the unique
# (author, title) autoindex.
RESOLVE_WORK_SQL = (
    "SELECT DISTINCT work_id FROM chunks_full WHERE work=? AND lang=? AND author=? ORDER BY work_id"
)
RESOLVE_WORK_NO_AUTHOR_SQL = (
    "SELECT DISTINCT work_id FROM chunks_full WHERE work=? AND lang=? ORDER BY work_id"
)

INDEX_NAME = "idx_chunks_work_lang_ord"
WORKS_INDEX_NAME = "idx_works_title"


def _plan(conn: sqlite3.Connection, sql: str, params: tuple) -> str:
    rows = conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
    return " / ".join(str(r[-1]) for r in rows)


def _fts_rows(conn: sqlite3.Connection) -> tuple[int, int]:
    return (
        conn.execute("SELECT COUNT(*) FROM chunks_fts_data").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM chunks_fts_norm_data").fetchone()[0],
    )


def _apply_0030_again(conn: sqlite3.Connection) -> None:
    """Run 0030's `apply` directly, bypassing the already-applied check."""

    discovered = migrations._discover()
    for version, _stem, _kind, runner in discovered:
        if version == 30:
            runner(conn)
            conn.commit()
            return
    raise AssertionError(f"migration 0030 not found among {[v for v, *_ in discovered]}")


def _undo_0030(conn: sqlite3.Connection) -> None:
    """Return a migrated DB to its pre-0030 shape, keeping its rows."""

    conn.execute("DROP VIEW IF EXISTS chunks_full")
    conn.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
    conn.execute("ALTER TABLE chunks DROP COLUMN work_id")
    conn.execute(_PRE_0030_VIEW.strip())
    conn.execute("DELETE FROM schema_migrations WHERE version = 30")
    conn.commit()


def test_chunks_carries_a_denormalised_work_id(tmp_path: Path):
    conn = store.open_db(tmp_path / "fresh.sqlite")

    cols = {row[1] for row in conn.execute("PRAGMA table_info(chunks)")}

    assert "work_id" in cols


def test_the_companion_map_window_no_longer_scans_chunks(populated_db: sqlite3.Connection):
    """Both companion maps go through this one query, at 79.9 ms before."""

    row = populated_db.execute("SELECT work_id, lang FROM chunks_full LIMIT 1").fetchone()

    plan = _plan(populated_db, WINDOW_SQL, (row["work_id"], row["lang"], 200, 0))

    assert INDEX_NAME in plan, plan
    assert "SCAN c" not in plan, plan
    # `ord` trails the two equality columns, so the index supplies the order.
    assert "TEMP B-TREE FOR ORDER BY" not in plan, plan


def test_default_edition_no_longer_scans_chunks(populated_db: sqlite3.Connection):
    """#339 predicted 0029 would fix this because it "filters on
    edition_id/translation_id". It filters on work_id, and 0029 did not."""

    row = populated_db.execute("SELECT work_id, lang FROM chunks_full LIMIT 1").fetchone()

    plan = _plan(populated_db, DEFAULT_EDITION_SQL, (row["work_id"], row["lang"]))

    assert INDEX_NAME in plan, plan
    assert "SCAN c" not in plan, plan


def test_resolve_work_id_no_longer_scans_chunks(populated_db: sqlite3.Connection):
    """The shape the SPA sends, which carries `author` for disambiguation."""

    plan = _plan(populated_db, RESOLVE_WORK_SQL, ("Republic", "eng", "Plato"))

    assert INDEX_NAME in plan, plan
    assert "SCAN c" not in plan, plan


def test_resolve_work_id_without_an_author_no_longer_scans_chunks(
    populated_db: sqlite3.Connection,
):
    """The legacy-bookmark shape, and the reason 0030 adds `works(title, author)`
    after 0029 deliberately left it out.

    #339 proposed that index; the correction on the issue removed it from 0029
    as inert, having measured `resolve work_id` at 1.0x with it. That
    measurement was right, and so was the reasoning: the statement's cost was
    the `SCAN c` on chunks, so pinning the `works` row bought nothing. Part 2
    removes the `SCAN c` — which is exactly what makes the works lookup the
    remaining cost, and the index no longer inert. Measured on the live corpus,
    author-less: 73.7 ms before part 2, 31.6 ms with part 2 alone (a full scan
    of the new chunks index), 0.53 ms with both.
    """

    plan = _plan(populated_db, RESOLVE_WORK_NO_AUTHOR_SQL, ("Republic", "eng"))

    assert "SCAN c" not in plan, plan


def test_ingest_populates_work_id_for_every_chunk(populated_db: sqlite3.Connection):
    """The insert path, not the backfill: `populated_db` migrates an empty
    DB and then ingests, so every value here was written by `insert_chunks`.

    A NULL here does not degrade a row, it deletes it — `chunks_full` inner-
    joins `works` on this column."""

    missing = populated_db.execute("SELECT COUNT(*) FROM chunks WHERE work_id IS NULL").fetchone()[
        0
    ]
    disagreeing = populated_db.execute(
        "SELECT COUNT(*) FROM chunks c "
        "LEFT JOIN editions e ON e.id = c.edition_id "
        "LEFT JOIN translations t ON t.id = c.translation_id "
        "WHERE c.work_id IS NOT COALESCE(e.work_id, t.work_id)"
    ).fetchone()[0]

    assert (missing, disagreeing) == (0, 0)


def test_every_ingested_chunk_is_still_visible_through_the_view(
    populated_db: sqlite3.Connection,
):
    """The failure mode the column introduces: the view's `JOIN works` is
    inner, so an unpopulated `work_id` silently drops the row from every
    reader, search and refs query rather than raising."""

    in_table = populated_db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    in_view = populated_db.execute("SELECT COUNT(*) FROM chunks_full").fetchone()[0]

    assert in_view == in_table


def test_the_backfill_reaches_rows_that_predate_the_migration(
    populated_db: sqlite3.Connection,
):
    _undo_0030(populated_db)
    assert populated_db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] > 0, (
        "fixture must have rows for the backfill to reach"
    )

    migrations.apply(populated_db)

    missing = populated_db.execute("SELECT COUNT(*) FROM chunks WHERE work_id IS NULL").fetchone()[
        0
    ]
    disagreeing = populated_db.execute(
        "SELECT COUNT(*) FROM chunks c "
        "LEFT JOIN editions e ON e.id = c.edition_id "
        "LEFT JOIN translations t ON t.id = c.translation_id "
        "WHERE c.work_id IS NOT COALESCE(e.work_id, t.work_id)"
    ).fetchone()[0]

    assert (missing, disagreeing) == (0, 0)


def test_the_backfill_does_not_churn_the_fts_index(populated_db: sqlite3.Connection):
    """`chunks_au` fires on any UPDATE and rewrites both FTS indexes, though
    the backfill touches neither `text` nor `text_norm`. Measured on the live
    corpus: leaving the triggers in place cost 21.1 s instead of 4.7 s and
    added 19,418 + 19,497 segment rows — ~83 MB — for no content change.
    """

    _undo_0030(populated_db)
    before = _fts_rows(populated_db)

    migrations.apply(populated_db)

    assert _fts_rows(populated_db) == before


def test_the_backfill_leaves_the_fts_triggers_in_place(populated_db: sqlite3.Connection):
    """Dropping them is how the churn is avoided; failing to put them back
    would silently stop the FTS index tracking every later ingest."""

    _undo_0030(populated_db)

    migrations.apply(populated_db)

    triggers = {
        row[0]
        for row in populated_db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='chunks'"
        )
    }
    assert triggers == {"chunks_ai", "chunks_ad", "chunks_au"}


def test_applying_twice_is_a_no_op(populated_db: sqlite3.Connection):
    """The runner rolls back and leaves the version unrecorded when a
    migration raises, so the next `open_db` runs it again — which the module
    docstring requires every `.py` migration to survive. Deleting the
    `"work_id" not in columns` guard makes this raise `duplicate column
    name: work_id`; dropping `WHERE work_id IS NULL` from the backfill makes
    it rewrite every row through the FTS triggers a second time.
    """

    _undo_0030(populated_db)
    migrations.apply(populated_db)
    expected_fts = _fts_rows(populated_db)
    expected_rows = populated_db.execute("SELECT COUNT(*) FROM chunks_full").fetchone()[0]

    # Re-run the migration itself, not `apply` (which would skip it now).
    _apply_0030_again(populated_db)

    assert _fts_rows(populated_db) == expected_fts
    assert populated_db.execute("SELECT COUNT(*) FROM chunks_full").fetchone()[0] == expected_rows
    assert (
        populated_db.execute("SELECT COUNT(*) FROM chunks WHERE work_id IS NULL").fetchone()[0] == 0
    )


def test_search_still_matches_after_the_migration(populated_db: sqlite3.Connection):
    """The end the triggers serve. Pins that dropping and recreating them
    around the backfill leaves the index answering the same question."""

    before = populated_db.execute(
        "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH 'divided'"
    ).fetchone()[0]
    assert before > 0, "fixture must have a matching row for this to mean anything"
    _undo_0030(populated_db)

    migrations.apply(populated_db)

    after = populated_db.execute(
        "SELECT COUNT(*) FROM chunks_fts WHERE chunks_fts MATCH 'divided'"
    ).fetchone()[0]
    assert after == before
