"""0017_surah_ayah_citation.py — admit `surah_ayah` to the
``works.citation_system`` CHECK list.

The Quran is cited by ``Surah:Ayah`` — e.g., ``2:255`` (Al-Baqarah,
Throne Verse) — structurally novel vs. ``bcv`` because the unit
above the ayah is a fixed-position surah (1..114), not a book name
that needs SBL-style abbreviation lookup. It earns its own
``works.citation_system`` value so ``locations.py`` can validate the
payload and ``location_sort_key`` can order ayahs canonically.

Same lite-rebuild pattern as 0010 / 0011 / 0014 / 0015: ``PRAGMA
foreign_keys = OFF`` + ``PRAGMA legacy_alter_table = ON`` (to keep
the ``chunks_full`` view from blocking the RENAME), recreate the
``works`` table with the widened CHECK, copy rows, drop the
original, rename, restore PRAGMAs. PRAGMAs are flipped OUTSIDE the
implicit transaction — see [[sqlite_migration_pragma_dance]].

Note: Hebrew MT reuses the existing ``bcv`` citation_system (same
book-chapter-verse shape as LXX / Vulgate / NT), so this migration
adds only one new value rather than two.
"""

from __future__ import annotations

import sqlite3


_REBUILD_WORKS = """
CREATE TABLE works__new (
    id                  INTEGER PRIMARY KEY,
    author              TEXT NOT NULL,
    title               TEXT NOT NULL,
    original_language   TEXT NOT NULL CHECK (original_language IN
        ('grc', 'fra', 'deu', 'eng', 'lat', 'heb', 'ara')),
    citation_system     TEXT NOT NULL CHECK (citation_system IN
        ('stephanus', 'bekker', 'kant_ab', 'sz_marginal', 'paragraph',
         'augustine', 'aquinas', 'bcv', 'diels_kranz', 'surah_ayah')),
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
            raise RuntimeError(f"0017 left dangling FKs after rebuild: {bad!r}")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.execute(f"PRAGMA legacy_alter_table = {legacy_prev}")
        conn.execute(f"PRAGMA foreign_keys = {'ON' if fk_prev else 'OFF'}")
