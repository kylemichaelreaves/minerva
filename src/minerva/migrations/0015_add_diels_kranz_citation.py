"""0015_add_diels_kranz_citation.py — admit `diels_kranz` to the
``works.citation_system`` CHECK list.

Pre-Socratic fragments are cited by ``<DK-chapter> <fragment-letter>
<number>`` — e.g., ``22 B 1`` for Heraclitus's first surviving B-
fragment. Universal scholarly convention since Kranz's 6th edition
(1951). Distinct from the existing systems (which all assume a
linear page or section number on a single work) because the
"chapter" here is the philosopher's editorial slot in DK rather than
a chapter inside one author's work.

Same table-rebuild pattern as 0010 / 0011 / 0014: ``PRAGMA
foreign_keys = OFF`` + ``PRAGMA legacy_alter_table = ON`` (to keep
the ``chunks_full`` view from blocking the RENAME), recreate the
``works`` table with the widened CHECK, copy rows, drop the original,
rename, restore PRAGMAs. PRAGMAs are flipped OUTSIDE the implicit
transaction — see [[sqlite_migration_pragma_dance]].
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
         'augustine', 'aquinas', 'bcv', 'diels_kranz')),
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
                f"0015 left dangling FKs after rebuild: {bad!r}"
            )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.execute(f"PRAGMA legacy_alter_table = {legacy_prev}")
        conn.execute(f"PRAGMA foreign_keys = {'ON' if fk_prev else 'OFF'}")
