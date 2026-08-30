"""0033_embeddings_text_hash.py — text_hash column for embeddings (#285).

`tei._make_chunk_id` hashes only `text[:120]`, so a chunk edited past
that point keeps its `chunk_id`. `iter_chunks_without_embeddings`'s skip
predicate used to check only `(chunk_id, model)` existence, so a chunk
edited past character 120 kept its stale vector forever — the edit
never triggered a re-encode, and retrieval kept scoring the chunk
against the old wording. `chunk_lemma_state` already carries this
treatment (migration 0027); this gives `embeddings` the same one, which
is #285's cheapest suggested fix (option 1).

Backfilled here — not left for the next `minerva embed` run to discover
one row at a time — so a corpus whose embeddings already exist doesn't
read every row as unhashed and re-encode everything for nothing.

Idempotent: guards the `ALTER TABLE`, the same way 0021/0022 do, against
a partially-committed prior attempt (see `migrations/__init__.py`'s
module docstring on why `.py` migrations must tolerate that).
"""

from __future__ import annotations

import sqlite3

from minerva.sqlite_util import register_text_hash

_BACKFILL = """
UPDATE embeddings
SET text_hash = (
    SELECT text_hash(c.text) FROM chunks c WHERE c.chunk_id = embeddings.chunk_id
)
WHERE text_hash IS NULL
"""


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def apply(conn: sqlite3.Connection) -> None:
    if not _has_column(conn, "embeddings", "text_hash"):
        conn.execute("ALTER TABLE embeddings ADD COLUMN text_hash TEXT")
    register_text_hash(conn)
    conn.execute(_BACKFILL)
