"""0031_lemma_counts_initial.py — store the rail's folded initial (#425).

#381 made the A–Z letter filter fold diacritics for every language, which took
914 German rows, 1,344 French and 571 English from "unreachable from the rail"
to reachable. It did that by replacing an indexed prefix predicate with a
function call:

    -- before: lemma LIKE 'A%' ESCAPE '\\'
    -- after:  fold_initial(lemma) = ?

`fold_initial` is a Python callback registered per connection, so SQLite cannot
use `lemma_counts_by_alpha`'s `lemma` column for it. The plan loses exactly its
range bounds and the query degrades to a full scan of the language partition:

    before: SEARCH lemma_counts USING COVERING INDEX lemma_counts_by_alpha
              (lang=? AND scope_kind=? AND scope_value=? AND lemma>? AND lemma<?)
    after:  SEARCH lemma_counts USING COVERING INDEX lemma_counts_by_alpha
              (lang=? AND scope_kind=? AND scope_value=?)

Measured on the live index, deu corpus partition (164,850 rows), same process,
back to back — the ONLY comparison worth quoting, because these figures move by
~6x with page-cache state and the ratio moves with them (the numbers first filed
on #425 were taken warm; the correction on that issue has the working):

    LIKE 'A%'              median    2.75 ms
    fold_initial(lemma)='A' median   56.88 ms

~0.35 us/row is SQLite -> Python boundary crossing, not folding work:
`_fold_initial_cached` is an `lru_cache` whose hit rate is ~100% after the first
few dozen rows, because the key space is the 26-key rail plus a short tail. So
the fix is to stop calling it per row, not to make it faster.

This stores the fold once, at aggregate time, and indexes it. The filter becomes
an indexed equality, and the rail's `GROUP BY letter` becomes a covering-index
group with no callback at all — which also removes the ~24 ms the fold added to
the *unfiltered* page load, since that query groups every row in the partition.

WHY THE MIGRATION BACKFILLS RATHER THAN LEAVING IT TO THE NEXT REBUILD
--------------------------------------------------------------------
`aggregate.build` replaces this table wholesale, so one `minerva index` after
this lands populates every row. But between the two, `lemma_initial` would be
NULL everywhere — and an equality predicate against NULL matches nothing, so
every letter on the rail would return zero rows and the leaderboard's letter
filter would appear to work while silently answering empty. A migration that
opens a window in which a user-facing filter is broken is not acceptable, and
the window would last until whenever the operator next reindexed.

So the backfill happens here, in Python, with `fold_initial` registered on the
connection — the same function `aggregate.build` and the read path use. A plain
`.sql` migration could not have done this: the fold is not expressible in
SQLite's own functions (that is the whole reason #373, #366 and #381 exist —
`UPPER`/`LOWER` are ASCII-only).

WHY NOT A GENERATED COLUMN
--------------------------------------------------------------------
`GENERATED ALWAYS AS` needs a deterministic *SQL* expression. `fold_initial` is
a registered Python callback, so it is not available to one — and a SQL
expression that approximated it would reintroduce the ASCII-only bug the fold
exists to fix.

THE COUPLING THIS INTRODUCES, STATED PLAINLY
--------------------------------------------------------------------
The stored value must stay equal to what the request folds its parameter with.
Change `_fold_initial` without reindexing and the filter silently mismatches —
the same class of stale-derived-state hazard as `chunk_lemma_state`'s
`text_hash`. Two things guard it: `aggregate.build` writes the column with the
identical function (not a copy of its logic), and
`tests/test_concordance_queries.py` asserts the stored column equals
`_fold_initial(lemma)` for every row it builds, so a divergence fails the suite
rather than the rail.

ADD COLUMN, NOT A REBUILD
--------------------------------------------------------------------
`lemma_counts` carries no foreign key and no view reads it, and the column is
nullable with no default — a pure catalogue edit, none of the PRAGMA/view-drop
dance a table rebuild needs (see 0013).
"""

from __future__ import annotations

import sqlite3

from minerva.concordance.index_queries import _fold_initial

_ADD_COLUMN = "ALTER TABLE lemma_counts ADD COLUMN lemma_initial TEXT"

# `(lang, scope_kind, scope_value, lemma_initial)` mirrors the partition prefix
# every other index on this table uses, so a letter-filtered read seeks straight
# to its slice. `lemma` is carried as the last column so the index still covers
# the alphabetical ordering the letter-filtered page applies on top.
_INDEX = """
CREATE INDEX IF NOT EXISTS lemma_counts_by_initial
    ON lemma_counts(lang, scope_kind, scope_value, lemma_initial, lemma COLLATE NOCASE)
"""


def apply(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(lemma_counts)")}
    if "lemma_initial" not in columns:
        conn.execute(_ADD_COLUMN)

    # Same function the read path folds its parameter with, and the same one
    # `aggregate.build` writes with — deliberately imported rather than
    # reimplemented, so the three cannot drift.
    conn.create_function("fold_initial", 1, _fold_initial, deterministic=True)
    # Only rows that need it, so re-running the migration on an already-built
    # table is free rather than a full rewrite.
    conn.execute(
        "UPDATE lemma_counts SET lemma_initial = fold_initial(lemma) "
        "WHERE lemma_initial IS NULL"
    )

    conn.execute(_INDEX)
