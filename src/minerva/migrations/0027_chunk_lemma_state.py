"""0027_chunk_lemma_state.py — attempt marker for `terms lemmatize`.

`chunk_lemmas` was serving as both the output table and the
"already processed" marker for the incremental lemmatize pass. A chunk
that yields no *valid* lemma (``is_valid_lemma`` rejects punctuation,
digits, OCR debris) writes no row, so nothing recorded that it had ever
been attempted. 859 chunks — 419 eng / 299 fra / 126 deu / 15 grc —
were therefore re-tokenized on every incremental run forever, and the
completion line counted them as done (#263).

`chunk_lemma_state` separates the two. One row per chunk we have run
the lemmatizer over, whatever came out.

WHY THE `chunk_syntax_state` PRECEDENT, NOT `refs_scan_state`
--------------------------------------------------------------------
Both are skip caches, and `refs_scan_state` is the closer analogue by
purpose — but it carries no foreign key, and that is precisely what
#264 is about: 31,629 of its 460,235 rows point at chunks that no
longer exist, and because `chunk_id` is content-derived, a chunk
deleted and later re-created inherits its own stale marker. Declaring
`REFERENCES chunks(chunk_id) ON DELETE CASCADE` — as
`chunk_syntax_state` does (migration 0024) — gets orphan reaping for
free.

WHY A `text_hash` COLUMN WHEN `chunk_id` IS ALREADY CONTENT-DERIVED
--------------------------------------------------------------------
`tei._make_chunk_id` hashes `text[:120]`, not the whole text. A chunk
edited past character 120 keeps its id, so the FK above never fires and
the marker would claim "done at this text" about text that has since
changed. The hash is compared against the chunk's *current* text, so
that case re-lemmatizes.

THE BACKFILL, AND WHY THIS IS A `.py` MIGRATION
--------------------------------------------------------------------
Creating the table empty would be worse than not creating it: the very
next incremental pass would see no state rows anywhere and re-lemmatize
the entire corpus — 26M tokens, hours. Every chunk that already has
`chunk_lemmas` rows has demonstrably been through the lemmatizer, so it
is seeded here as attempted, with the token count it produced. That
needs `sha1` over `chunks.text`, which SQLite has no builtin for; hence
Python, and `register_text_hash` (same shape as 0021's canonicalizer).

The seed cannot recover the zero-lemma chunks — they left no trace, by
definition. They get one final pass, after which they are recorded.
"""

from __future__ import annotations

import sqlite3

from minerva.sqlite_util import register_text_hash

_CREATE = """
CREATE TABLE IF NOT EXISTS chunk_lemma_state (
    chunk_id      TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    text_hash     TEXT NOT NULL,
    -- Valid lemmas written to chunk_lemmas by that attempt. 0 means
    -- "the lemmatizer ran and produced nothing", which is what makes
    -- the zero-lemma population queryable instead of inferred.
    token_count   INTEGER NOT NULL,
    lemmatized_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

# Rows whose token_count is 0 are the interesting ones to a curator
# chasing "why does this clean German prose produce no lemmas".
_INDEX = """
CREATE INDEX IF NOT EXISTS chunk_lemma_state_barren
    ON chunk_lemma_state(token_count) WHERE token_count = 0
"""

_BACKFILL = """
INSERT OR IGNORE INTO chunk_lemma_state (chunk_id, text_hash, token_count)
SELECT c.chunk_id, text_hash(c.text), COUNT(*)
FROM chunks c
JOIN chunk_lemmas cl ON cl.chunk_id = c.chunk_id
GROUP BY c.chunk_id
"""


def apply(conn: sqlite3.Connection) -> None:
    conn.execute(_CREATE)
    conn.execute(_INDEX)
    register_text_hash(conn)
    conn.execute(_BACKFILL)
