"""0011_aquinas_citation_system.py — admit `aquinas` to the
``works.citation_system`` CHECK list.

The Aquinas ingest writes Summa Theologiae and Summa contra Gentiles
chunks with a per-Work ``citation_system='aquinas'`` override (see
``aquinas_works.WORKS``). Without this migration the INSERT into
``works`` fails with a CHECK violation the first time an Aquinas
chunk lands.

Same lite-rebuild pattern as 0009 / 0010: ``PRAGMA foreign_keys =
OFF`` + ``PRAGMA legacy_alter_table = ON`` (to keep the
``chunks_full`` view from blocking the RENAME), recreate the
``works`` table with the widened CHECK, copy rows, drop the
original, rename, restore PRAGMAs. PRAGMAs are flipped OUTSIDE the
implicit transaction — see [[sqlite_migration_pragma_dance]].

What this enables: ``aquinas`` is now a valid value for
``works.citation_system`` alongside the values added by earlier
migrations (``stephanus``, ``bekker``, ``kant_ab``, ``sz_marginal``,
``paragraph``, ``augustine``).
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
         'augustine', 'aquinas')),
    UNIQUE (author, title)
);
"""


def apply(conn: sqlite3.Connection) -> None:
    fk_prev = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    legacy_prev = conn.execute("PRAGMA legacy_alter_table").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA legacy_alter_table = ON")
    try:
        conn.execute(_REBUILD_WORKS)
        conn.execute("INSERT INTO works__new SELECT * FROM works")
        conn.execute("DROP TABLE works")
        conn.execute("ALTER TABLE works__new RENAME TO works")
        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise RuntimeError(
                f"0011 left dangling FKs after rebuild: {bad!r}"
            )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.execute(f"PRAGMA legacy_alter_table = {legacy_prev}")
        conn.execute(f"PRAGMA foreign_keys = {'ON' if fk_prev else 'OFF'}")
