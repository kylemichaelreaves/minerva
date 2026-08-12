"""0030_chunks_work_id.py — denormalise `works.id` onto `chunks` (#339 part 2).

Migration 0029 indexed `chunks(edition_id, translation_id, ord)` and took the
Reader's work-range endpoint from ~365 ms to ~176 ms. Three statements did not
improve, because `chunks_full` reached `works` through

    JOIN works w ON w.id = COALESCE(e.work_id, t.work_id)

an expression join no index on `chunks` can serve. Measured against the live
428,606-chunk index with 0029 in place:

    1. resolve work_id (DISTINCT)      med   72.429 ms  ! SCAN c
    1b. _default_edition               med   80.380 ms  ! SCAN c
    2. meta + total (COUNT GROUP BY)   med    0.054 ms
    3. the page itself (LIMIT 80)      med    0.134 ms
    4. sibling editions                med   19.089 ms  ! SCAN c
    fetch_chunk_ids_in_window          med   79.943 ms  ! SCAN c

`_default_edition` is the largest of them and #339 does not account for it at
all — the issue predicted 0029 would fix it because it "filters on
edition_id/translation_id". It filters on `work_id` and `lang`. The correction
is recorded on the issue.

This migration adds the column, backfills it, indexes it, and points the view
at it. Measured on an APFS clone of snapshot
20260812T150320Z-pre-339-part2-workid-column:

                                       before      after
    1. resolve work_id                72.429 ms   0.016 ms
    1b. _default_edition              80.380 ms   0.031 ms
    4. sibling editions               19.089 ms   0.143 ms
    reader path total                172.09  ms   0.42  ms   (410x)
    fetch_chunk_ids_in_window         79.943 ms   0.045 ms  (1776x)

End-to-end over HTTP, one `minerva serve` per clone, Nietzsche *Zarathustra*,
median of 7: the Reader's three-fetch page load goes 357.9 ms → 13.8 ms.

WHY THE VIEW READS `c.work_id` AND NOT `w.id`
--------------------------------------------------------------------
They are equal — the join is an equality on exactly that column — so this
looks like a free choice, and it is not. `w.id` is reached through the join,
so a filter on it constrains `works` and leaves `chunks` to be scanned;
`c.work_id` is a real column on the filtered table and `idx_chunks_work_lang_ord`
serves it directly. #339 proposed instead rewriting the two offending SQL
statements in `reader/queries.py`. That turns out to be unnecessary — one line
in the view makes every caller indexable, including the two companion maps
the issue does not mention — and its suggested rewrite of `resolve work_id`
("via `works` alone", 0.002 ms) would have changed behaviour: it resolves a
same-titled work that has no chunks in the requested language, where the
current statement correctly skips it. Two Luther Bibles share every book
title and language, so that path is live.

WHY THE FTS TRIGGERS COME OFF FOR THE BACKFILL
--------------------------------------------------------------------
`chunks_au` fires on any UPDATE of `chunks` and rewrites both FTS indexes:

    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', ...);
    INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
    ...same for chunks_fts_norm...

The backfill touches neither `text` nor `text_norm`, so every one of those
writes is a no-op that costs real time and real disk. Measured on the live
corpus, triggers the only variable:

                                backfill   COMMIT   CREATE INDEX    total
    triggers left in place       21.06 s   10.95 s       3.93 s    35.9 s
    triggers dropped/recreated    4.72 s    2.82 s       0.26 s     7.8 s

    page_count       2,137,872 -> 2,158,170  with triggers (+83 MB)
                     2,137,872 -> 2,137,872  without
    chunks_fts_data     28,371 ->    47,789  with triggers
    chunks_fts_norm_data 48,150 ->    67,647  with triggers

`integrity-check` passes on both FTS tables either way and `MATCH
'Gerechtigkeit'` returns 1,182 hits either way, so the trigger path is
merely wasteful rather than wrong. #339's stated "22.3 s" backfill is the
trigger-on figure; the issue never mentions the triggers, and its
`CREATE INDEX` estimate of 84.5 s is 325x the measured 0.26 s. Both
corrections are recorded on the issue.

If this migration fails between the drop and the recreate, the database is
left without FTS triggers — but the version is not recorded, `open_db`
raises, and the retry drops (`IF EXISTS`) and recreates them. That is why
the trigger work is not guarded by a probe: re-entry must redo it.

WHY `work_id` IS NULLABLE, AND WHAT THAT COSTS
--------------------------------------------------------------------
Adding a NOT NULL column to an existing table needs a default, and there is
no correct default for a foreign key. So the constraint is not declarable
here without rebuilding a 428,606-row table, and the column stays nullable.

The exposure is worth naming, because it is silent: `chunks_full` inner-joins
`works` on this column, so a chunk whose `work_id` is NULL does not lose its
title — it vanishes from the view, and therefore from every reader, search
and refs query, with no error anywhere. `insert_chunks` sets it from the same
`_resolve_work_refs` call that produces `edition_id`/`translation_id`, and
`test_ingest_populates_work_id_for_every_chunk` plus
`test_every_ingested_chunk_is_still_visible_through_the_view` pin that.
"""

from __future__ import annotations

import sqlite3

from minerva.store.ddl import (
    chunks_fts_trigger_creates,
    chunks_fts_trigger_drops,
    recreate_chunks_full_view,
)

_ADD_COLUMN = "ALTER TABLE chunks ADD COLUMN work_id INTEGER REFERENCES works(id)"

# `WHERE work_id IS NULL` is the re-entrancy guard: a retry after a partially
# committed attempt fills only what is still missing, and on a fresh database
# this matches zero rows.
_BACKFILL = """
UPDATE chunks SET work_id = COALESCE(
    (SELECT e.work_id FROM editions e WHERE e.id = chunks.edition_id),
    (SELECT t.work_id FROM translations t WHERE t.id = chunks.translation_id))
WHERE work_id IS NULL
"""

# `lang` and `ord` trail the equality column for the same reason 0029's index
# is ordered the way it is: `fetch_chunk_ids_in_window` filters
# `work_id = ? AND lang = ?` and then wants `ORDER BY ord`, so one index
# serves the lookup and the sort and no temp B-tree is materialised.
_INDEX = """
CREATE INDEX IF NOT EXISTS idx_chunks_work_lang_ord
    ON chunks(work_id, lang, ord)
"""

# `works(title, author)` — the index #339 asked for, which 0029 deliberately
# left out as inert. Both of those were right, and this is not a reversal of
# either: 0029's correction measured `resolve work_id` at 1.0x with the index
# and concluded the cost was the `SCAN c` on chunks rather than the works
# lookup, noting that "the only access path it genuinely adds is
# title-without-author". Removing the `SCAN c` is what promotes that access
# path from unused to load-bearing, and `author` is optional on the reader
# route so the title-without-author shape is live for every legacy bookmark.
#
# Measured on the live corpus, author-less `resolve work_id`:
#
#     before part 2                        73.730 ms   SCAN c
#     part 2 alone                         31.639 ms   SCAN c USING INDEX
#                                                      idx_chunks_work_lang_ord
#     part 2 + this index                   0.533 ms   SEARCH w USING COVERING
#                                                      INDEX idx_works_title
#
# The author-ful shape the SPA actually sends is 0.420 ms either way; this
# index is worth 60x on the legacy path and nothing on the main one.
_WORKS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_works_title
    ON works(title, author)
"""


def apply(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(chunks)")}
    if "work_id" not in columns:
        conn.execute(_ADD_COLUMN)

    for stmt in chunks_fts_trigger_drops():
        conn.execute(stmt)
    try:
        conn.execute(_BACKFILL)
    finally:
        for stmt in chunks_fts_trigger_creates():
            conn.execute(stmt)

    conn.execute(_INDEX)
    conn.execute(_WORKS_INDEX)
    # The view is the half that makes the column reachable; `ddl.py` holds
    # its post-0030 shape, so this is also what upgrades a database whose
    # view was last written by 0022.
    recreate_chunks_full_view(conn)
