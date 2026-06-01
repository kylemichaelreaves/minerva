"""0014_bcv_citation_system.py — admit `bcv` to the
``works.citation_system`` CHECK list.

Biblical corpora (Septuagint, New Testament, Vulgate) cite by
book-chapter-verse — ``Gen 1:1``, ``Matt 5:3``, ``Rom 9:14`` — a
structurally novel locator vs. the existing values (Stephanus
pages, Bekker columns, KrV A/B-pages, paragraph numbers). It earns
its own ``works.citation_system`` value so that ``locations.py`` can
validate the payload and ``location_sort_key`` can order chunks
canonically across the three biblical corpora.

Same lite-rebuild pattern as 0010 / 0011: ``PRAGMA foreign_keys =
OFF`` + ``PRAGMA legacy_alter_table = ON`` (to keep the
``chunks_full`` view from blocking the RENAME), recreate the
``works`` table with the widened CHECK, copy rows, drop the
original, rename, restore PRAGMAs. PRAGMAs are flipped OUTSIDE the
implicit transaction — see [[sqlite_migration_pragma_dance]].

What this enables: ``bcv`` is now a valid value for
``works.citation_system`` alongside ``stephanus``, ``bekker``,
``kant_ab``, ``sz_marginal``, ``paragraph``, ``augustine``, and
``aquinas``.
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
         'augustine', 'aquinas', 'bcv')),
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
                f"0014 left dangling FKs after rebuild: {bad!r}"
            )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.execute(f"PRAGMA legacy_alter_table = {legacy_prev}")
        conn.execute(f"PRAGMA foreign_keys = {'ON' if fk_prev else 'OFF'}")
