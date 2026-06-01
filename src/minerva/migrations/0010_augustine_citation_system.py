"""0010_augustine_citation_system.py — admit `augustine` to the
``works.citation_system`` CHECK list.

The Augustine ingest writes Confessiones / De civitate Dei /
De Trinitate chunks with a per-Work ``citation_system='augustine'``
override (see ``augustine_works.WORKS``). Without this migration the
INSERT into ``works`` fails with a CHECK violation the first time an
Augustine chunk lands.

SQLite can't ALTER a CHECK constraint in place, so the ``works``
table is rebuilt via the same 12-step lite-rebuild dance used by
0009: ``PRAGMA foreign_keys = OFF`` + ``PRAGMA legacy_alter_table =
ON`` (to keep the chunks_full view from blocking the RENAME), recreate
with the widened CHECK, copy rows, drop the original, rename, restore
PRAGMAs. PRAGMAs are flipped OUTSIDE the implicit transaction
(SQLite treats ``PRAGMA foreign_keys = ...`` as a no-op while a
transaction is open) — that's the trap that bit 0009 and is
documented in the project's auto-memory under
[[sqlite_migration_pragma_dance]].

What this enables: ``augustine`` is now a valid value for
``works.citation_system`` alongside ``stephanus``, ``bekker``,
``kant_ab``, ``sz_marginal``, and ``paragraph``.

What this does NOT touch: ``original_language``, ``editions.language``,
``translations.language`` already admitted ``lat`` in 0009; the
Augustine pass is Latin-only so no language CHECK widening is
needed.
"""

from __future__ import annotations

import sqlite3


_REBUILD_WORKS = """
CREATE TABLE works__new (
    id                  INTEGER PRIMARY KEY,
    author              TEXT NOT NULL,
    title               TEXT NOT NULL,
    original_language   TEXT NOT NULL CHECK (original_language IN
        ('grc', 'fra', 'deu', 'eng', 'lat')),
    citation_system     TEXT NOT NULL CHECK (citation_system IN
        ('stephanus', 'bekker', 'kant_ab', 'sz_marginal', 'paragraph',
         'augustine')),
    UNIQUE (author, title)
);
"""


def apply(conn: sqlite3.Connection) -> None:
    # FK enforcement during a table-rebuild trips on the brief window
    # between DROP TABLE and RENAME — referring rows look orphaned.
    # Record the prior state so callers see the same pragma value
    # they had on entry.
    fk_prev = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    # `legacy_alter_table = ON` tells SQLite to skip RENAME-TO's
    # validation of triggers and views that reference the affected
    # table — without it, the `chunks_full` view (which JOINs against
    # works / editions / translations) blocks the rename mid-rebuild
    # with "no such table: main.works". The view is automatically
    # re-bound to the renamed table once the rebuild settles.
    legacy_prev = conn.execute("PRAGMA legacy_alter_table").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA legacy_alter_table = ON")
    try:
        # Use `execute`, NOT `executescript` — the latter does an
        # implicit COMMIT before running, which would prematurely
        # close the runner's transaction. The DDL is single-statement
        # so a plain `execute` is fine.
        conn.execute(_REBUILD_WORKS)
        conn.execute("INSERT INTO works__new SELECT * FROM works")
        conn.execute("DROP TABLE works")
        conn.execute("ALTER TABLE works__new RENAME TO works")
        # Sanity: any FK that would have been broken by the rebuild
        # surfaces here. An empty list means every reference still
        # resolves to a real row.
        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise RuntimeError(
                f"0010 left dangling FKs after rebuild: {bad!r}"
            )
        # Close the in-flight transaction explicitly. SQLite treats
        # `PRAGMA foreign_keys = ...` as a silent no-op while a
        # transaction is open, so the restoration in `finally` only
        # sticks if we commit (or roll back) first.
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.execute(f"PRAGMA legacy_alter_table = {legacy_prev}")
        conn.execute(f"PRAGMA foreign_keys = {'ON' if fk_prev else 'OFF'}")
