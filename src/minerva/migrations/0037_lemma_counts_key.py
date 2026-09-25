"""0037_lemma_counts_key.py — store the merge_case group key and index it (#655).

The Concordance index page's own load request (`GET /api/concordance/index`,
all defaults) groups every lemma of the language on `lower_uni(lemma)` twice:
once for the leaderboard page, once for the rail and header totals. Measured on
an APFS clone of the live index (warm, median of 9):

    lang  total     page     rail/totals
    deu   230.2 ms  86.2 ms  141.1 ms
    fra   203.7     58.7     144.1
    eng   197.9     76.9     116.9
    grc   169.5     59.0     112.2

#655 blamed the temp B-tree grouping. The larger half of the rail was actually
the table: `lemma_counts_by_pos` covers neither the key nor the summed columns,
so each of ~142k index entries fetched its row. A covering index alone, with
the SQL unchanged, took deu's rail 141.1 → 76.7 ms, and the grouping was still
a temp B-tree. Streaming the GROUP BY off a stored key took it to 61.7.

The page needs the stored key for a different reason. It cannot be covered,
since it concatenates `per_work_json`, so `index_queries` now picks the top
`limit` groups off this index and seeks the details for just those groups by
`(…, lemma_key, pos)`. That seek needs the key in the index. Without it the 200
seeks each scanned the partition: 3,185 ms, against 94 ms before and 38 ms with
the column. Every page and every rail compared identical to the shipped query,
for all seven languages.

Cost on the live table: ~16 s to backfill 4.4M rows and ~12 s to build the
index, 272 MB.

WHY THE MIGRATION BACKFILLS, AND IN PYTHON
--------------------------------------------------------------------
Both reasons are 0031's. A NULL key would drop its row out of every merged
group until the next `aggregate.build`, and the key is Python's `str.lower`
because SQL `LOWER()` is ASCII-only (#373). So `_lower_unicode` is registered
here, the same function `aggregate.build` writes with, imported rather than
restated.

THE COUPLING
--------------------------------------------------------------------
The stored key must equal `_lower_unicode(lemma)`.
`tests/test_concordance_queries.py` asserts that for every row it builds, the
same guard `lemma_initial` has.
"""

from __future__ import annotations

import sqlite3

from minerva.concordance.index_queries import _lower_unicode

_ADD_COLUMN = "ALTER TABLE lemma_counts ADD COLUMN lemma_key TEXT"

# The partition prefix every index on this table leads with, then the group key
# in the order the GROUP BY wants it. `count`, `lemma_initial` and `lemma`
# trail so the rail and the page's top-N never leave the index: `count` is
# summed, `lemma_initial` is the rail bucket, and `lemma` carries the validity
# guard in `_counts_where`.
_INDEX = """
CREATE INDEX IF NOT EXISTS lemma_counts_by_key
    ON lemma_counts(lang, scope_kind, scope_value, lemma_key, pos,
                    count, lemma_initial, lemma)
"""


def apply(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(lemma_counts)")}
    if "lemma_key" not in columns:
        conn.execute(_ADD_COLUMN)

    conn.create_function("lower_uni", 1, _lower_unicode, deterministic=True)
    # Only rows that need it: re-running over a built table is free.
    conn.execute("UPDATE lemma_counts SET lemma_key = lower_uni(lemma) WHERE lemma_key IS NULL")

    conn.execute(_INDEX)
