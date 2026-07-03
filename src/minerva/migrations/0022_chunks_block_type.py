"""0022_chunks_block_type.py — structural block label for chunks.

Adds a nullable ``chunks.block_type`` column tagging each chunk's role
within its work: ``NULL`` (≡ "body") for ordinary section/paragraph
prose, ``'remark'`` (Hegel *Anmerkung* / Spinoza *Scholium*),
``'addition'`` (Hegel *Zusatz*), ``'note'`` (footnote), ``'blockquote'``
(set-apart quotation).

Phase 0 of the block-structure remediation (see
``docs/block-structure-remediation-plan.md``): pure plumbing. Every
existing chunk reads back as ``NULL``, so there is no behavior change
until the structure-aware extractors populate the column.

Also recreates the ``chunks_full`` view to surface the new column — a
SQLite view is fixed at creation, so the ``ALTER TABLE`` alone would not
expose ``block_type`` to the reader/query layer (which reads through the
view, not the base table).

Idempotent: a fresh DB already has the column from ``store/schema.py``,
so the ``ALTER`` is guarded; the view is dropped + recreated either way.

Each statement runs via a separate ``conn.execute`` — NOT
``executescript``, whose implicit COMMIT would break the migration
runner's per-version transaction (see ``migrations/__init__.apply``).
"""

from __future__ import annotations

import sqlite3

from minerva.store.ddl import recreate_chunks_full_view


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def apply(conn: sqlite3.Connection) -> None:
    # 1. Column (guarded — schema.py already adds it on fresh DBs).
    if not _has_column(conn, "chunks", "block_type"):
        conn.execute("ALTER TABLE chunks ADD COLUMN block_type TEXT")

    # 2. Recreate the convenience view so block_type is selectable through
    #    it. Safe to drop — it's a pure view, and the migrations that read
    #    chunks_full all ran at their own apply time.
    recreate_chunks_full_view(conn)
