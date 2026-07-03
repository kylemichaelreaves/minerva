"""0013_xref_relax_cascade.py — relax the ``cross_references`` cascade
behavior so re-ingest stops wiping the table.

The shadow-address scheme (mirrors term_occurrences via migration
0005) was designed so cross-references survive re-ingest: the
combination of source_edition_id + source_sort_key +
source_form_snapshot + source_instance_index uniquely identifies a
row even when the underlying edition/chunk get re-inserted with new
surrogate IDs. The 0012 schema declared the three source-side FKs
with ``ON DELETE CASCADE`` (and one with no cascade clause, which
defaults to NO ACTION). When ``store.insert_chunks`` runs the
re-ingest DELETE chain, the editions / translations DELETEs
cascade and wipe every cross_references row before the rebind
logic has a chance to run.

This migration rebuilds ``cross_references`` with:

* ``source_chunk_id``       → no cascade (default NO ACTION).
    The store.insert_chunks pass disables FK enforcement during the
    destructive sequence so the dangling reference is tolerated;
    after re-insert chunk_ids are content-stable (the new chunks
    have the same chunk_ids as the old ones) so the FK is satisfied
    again. Orphans (source_chunk_id present in xref but not in the
    new chunks) are deleted explicitly by the rebind step.

* ``source_edition_id``     → ``ON DELETE SET NULL``.
    Re-ingest gives the edition a new id; store.insert_chunks
    rebinds the new id via a chunk-id pivot:
    UPDATE cross_references SET source_edition_id =
        (SELECT c.edition_id FROM chunks c WHERE c.chunk_id =
         cross_references.source_chunk_id).

* ``source_translation_id`` → ``ON DELETE SET NULL``. Same logic
    as source_edition_id; rebound via the chunk pivot.

target_chunk_id and target_id are unchanged — target_chunk_id was
already ``ON DELETE SET NULL`` in 0012; target_id points at
reference_targets which is never touched by re-ingest.

PRAGMA dance pattern (foreign_keys = OFF + legacy_alter_table = ON)
because two views — ``chunks_full`` and the existing FTS triggers —
reference cross_references columns indirectly. See
[[sqlite_migration_pragma_dance]].
"""

from __future__ import annotations

import sqlite3


# New table layout. Only the three source-side FK clauses differ from
# the 0012 CREATE; everything else is byte-identical so future schema
# diffs are easy to read.
_REBUILD_XREF = """
CREATE TABLE cross_references__new (
    id                       INTEGER PRIMARY KEY,
    source_chunk_id          TEXT NOT NULL REFERENCES chunks(chunk_id),
    source_span_start        INTEGER,
    source_span_end          INTEGER,
    source_form_snapshot     TEXT,
    quoted_phrase            TEXT,
    target_id                INTEGER NOT NULL REFERENCES reference_targets(id),
    target_chunk_id          TEXT REFERENCES chunks(chunk_id) ON DELETE SET NULL,
    target_locator           TEXT,
    target_locator_payload   TEXT,
    target_sort_key          TEXT,
    reference_type           TEXT NOT NULL CHECK (reference_type IN
        ('cites', 'quotes', 'paraphrases', 'alludes',
         'comments_on', 'translates', 'disputes', 'corrects')),
    confidence               REAL NOT NULL DEFAULT 1.0
                             CHECK (confidence BETWEEN 0 AND 1),
    source_method            TEXT NOT NULL DEFAULT 'manual'
                             CHECK (source_method IN
        ('manual', 'rule_strong', 'rule_weak', 'rule+embed',
         'rule+embed+llm', 'embed_only')),
    curator_status           TEXT NOT NULL DEFAULT 'manual'
                             CHECK (curator_status IN
        ('auto', 'approved', 'rejected', 'manual')),
    curator_note             TEXT,
    source_edition_id        INTEGER REFERENCES editions(id) ON DELETE SET NULL,
    source_translation_id    INTEGER REFERENCES translations(id) ON DELETE SET NULL,
    source_sort_key          TEXT,
    source_instance_index    INTEGER CHECK (source_instance_index IS NULL OR source_instance_index >= 1),
    UNIQUE (source_edition_id, source_sort_key, source_form_snapshot, source_instance_index),
    CHECK (source_span_start IS NULL OR source_span_end IS NULL OR source_span_end > source_span_start)
);
"""

# Indexes are dropped with the old table; we re-create them under the
# original names so existing query plans don't surprise. Names match
# the 0012 migration's CREATE INDEX statements exactly. One statement
# per element — run via `execute`, NOT `executescript`, whose implicit
# COMMITs would persist a half-done rebuild (see migrations/__init__).
_REBUILD_INDEXES = (
    "CREATE INDEX xref_by_source_chunk ON cross_references(source_chunk_id)",
    "CREATE INDEX xref_by_target_chunk ON cross_references(target_chunk_id)",
    "CREATE INDEX xref_by_target_id    ON cross_references(target_id)",
    "CREATE INDEX xref_by_status       ON cross_references(curator_status)",
    "CREATE INDEX xref_by_shadow       ON cross_references(source_edition_id, source_sort_key, source_form_snapshot)",
)


def apply(conn: sqlite3.Connection) -> None:
    # PRAGMAs must be set BEFORE the explicit BEGIN — they're silent
    # no-ops inside an open transaction. The BEGIN must be explicit
    # because CREATE/DROP/ALTER are DDL, which doesn't auto-begin a
    # transaction in Python's legacy isolation mode — without it a
    # mid-rebuild failure would leave cross_references__new committed
    # and the retry would fail on "table already exists".
    fk_prev = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    legacy_prev = conn.execute("PRAGMA legacy_alter_table").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA legacy_alter_table = ON")
    try:
        if not conn.in_transaction:
            conn.execute("BEGIN")
        conn.execute(_REBUILD_XREF)
        # Column order is identical, so a bare INSERT ... SELECT works.
        conn.execute(
            "INSERT INTO cross_references__new SELECT * FROM cross_references"
        )
        conn.execute("DROP TABLE cross_references")
        conn.execute("ALTER TABLE cross_references__new RENAME TO cross_references")
        for stmt in _REBUILD_INDEXES:
            conn.execute(stmt)
        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise RuntimeError(
                f"0013 left dangling FKs after rebuild: {bad!r}"
            )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.execute(f"PRAGMA legacy_alter_table = {legacy_prev}")
        conn.execute(f"PRAGMA foreign_keys = {'ON' if fk_prev else 'OFF'}")
