"""0041_chunks_attributed_to.py — who wrote an apparatus chunk (#710).

Adds ``chunks.attributed_to``: the real author of a ``note`` / ``editorial``
/ ``cast`` / ``spurious`` chunk (an editor, a translator, a transcriber, or
"<author> (doubtful or spurious)"), NULL for the work author's own text.
Refs reads ``COALESCE(c.attributed_to, works.author)`` wherever it credits a
citation to a source author, so 1,161 editors' citations stop counting as
Plato's, Aristotle's, Hegel's and Cicero's (measured 2026-10-07).

The value is derived by :func:`minerva.apparatus_attribution.attribute_chunk`
from columns the database already holds, so this backfill and
``insert_chunks`` agree by construction. The one thing the database stores
differently from the ingest is an original-language edition with no named
editor: ``_resolve_work_refs`` names that edition after the *work*
("Fragments (DK 22)"), and a work title is not a person, so it is passed as
None here exactly as the ingest's "(Original)" is.

The FTS triggers come off for the UPDATE for 0030's reason: ``chunks_au``
fires on any UPDATE and rewrites both FTS indexes, and this one touches
neither ``text`` nor ``text_norm``. Re-entry is safe — the backfill only
fills NULLs, and the trigger drops are ``IF EXISTS``.
"""

from __future__ import annotations

import sqlite3

from minerva.apparatus_attribution import attribute_chunk
from minerva.block_types import APPARATUS_TYPES
from minerva.store.ddl import chunks_fts_trigger_creates, chunks_fts_trigger_drops

_SELECT = f"""
SELECT c.chunk_id, c.block_type, c.source_file, w.author,
       COALESCE(t.translator_name, NULLIF(e.name, w.title)) AS responsible
FROM chunks c
JOIN works w ON w.id = c.work_id
LEFT JOIN editions e ON e.id = c.edition_id
LEFT JOIN translations t ON t.id = c.translation_id
WHERE c.attributed_to IS NULL
  AND c.block_type IN ({",".join("?" * len(APPARATUS_TYPES))})
"""


def apply(conn: sqlite3.Connection) -> int:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(chunks)")}
    if "attributed_to" not in columns:
        conn.execute("ALTER TABLE chunks ADD COLUMN attributed_to TEXT")

    updates = [
        (
            attribute_chunk(
                block_type=block_type,
                author=author,
                source_file=source_file,
                responsible=responsible,
            ),
            chunk_id,
        )
        for chunk_id, block_type, source_file, author, responsible in conn.execute(
            _SELECT, APPARATUS_TYPES
        )
    ]
    for stmt in chunks_fts_trigger_drops():
        conn.execute(stmt)
    try:
        conn.executemany("UPDATE chunks SET attributed_to = ? WHERE chunk_id = ?", updates)
    finally:
        for stmt in chunks_fts_trigger_creates():
            conn.execute(stmt)
    return len(updates)
