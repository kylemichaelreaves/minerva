"""0016_rtl_langs.py — admit `heb` and `ara` to every language-code CHECK.

The same four tables that needed widening for ``lat`` in 0009 now widen
again for Hebrew (Masoretic Text) and Arabic (Quran + Arabic
philosophy). The lite-rebuild dance is identical to 0009: rebuild each
table with the widened CHECK, copy rows, drop, rename, restore PRAGMAs.

What this enables: Hebrew MT (BCV-aligned with the existing LXX /
Vulgate), Quran, and Arabic-language philosophy can now land in
``works`` / ``editions`` / ``translations``, and Hebrew + Arabic terms
can be authored against ``terms.source_language``.

What this does NOT touch:
- ``works.citation_system`` — the Quran's ``surah_ayah`` system needs a
  separate migration (0017) that widens that CHECK. Hebrew MT reuses
  the existing ``bcv`` citation system.
- Frontend — RTL rendering of corpus text is handled in the Reader
  CSS / Lines component; this migration only opens the schema.
- Lemmatization — Hebrew + Arabic lemmatizers are deferred (see plan
  Phase G).
"""

from __future__ import annotations

import sqlite3


# Each entry: (table_name, full CREATE TABLE body using the __new
# suffix, list of CREATE INDEX statements to re-issue after the
# rename). The DDL bodies must match the original column order so
# ``INSERT INTO __new SELECT * FROM old`` copies cleanly.
_REBUILDS: list[tuple[str, str, list[str]]] = [
    (
        "works",
        """
        CREATE TABLE works__new (
            id                  INTEGER PRIMARY KEY,
            author              TEXT NOT NULL,
            title               TEXT NOT NULL,
            original_language   TEXT NOT NULL CHECK (original_language IN
                ('grc', 'fra', 'deu', 'eng', 'lat', 'heb', 'ara')),
            citation_system     TEXT NOT NULL CHECK (citation_system IN
                ('stephanus', 'bekker', 'kant_ab', 'sz_marginal', 'paragraph',
                 'augustine', 'aquinas', 'bcv', 'diels_kranz')),
            UNIQUE (author, title)
        );
        """,
        [],
    ),
    (
        "editions",
        """
        CREATE TABLE editions__new (
            id           INTEGER PRIMARY KEY,
            work_id      INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
            name         TEXT NOT NULL,
            language     TEXT NOT NULL CHECK (language IN
                ('grc', 'fra', 'deu', 'eng', 'lat', 'heb', 'ara')),
            year         INTEGER,
            notes        TEXT,
            is_canonical INTEGER NOT NULL DEFAULT 1
                CHECK (is_canonical IN (0, 1)),
            UNIQUE (work_id, name, year)
        );
        """,
        [
            "CREATE INDEX editions_by_work ON editions(work_id);",
            "CREATE UNIQUE INDEX editions_canonical_unique "
            "ON editions(work_id, language) WHERE is_canonical = 1;",
        ],
    ),
    (
        "translations",
        """
        CREATE TABLE translations__new (
            id                    INTEGER PRIMARY KEY,
            work_id               INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
            based_on_edition_id   INTEGER REFERENCES editions(id) ON DELETE SET NULL,
            translator_name       TEXT NOT NULL,
            year                  INTEGER,
            language              TEXT NOT NULL CHECK (language IN
                ('grc', 'fra', 'deu', 'eng', 'lat', 'heb', 'ara')),
            edition_notes         TEXT,
            UNIQUE (work_id, translator_name, year, language)
        );
        """,
        [
            "CREATE INDEX trans_by_work ON translations(work_id, language);",
        ],
    ),
    (
        "terms",
        """
        CREATE TABLE terms__new (
            id                INTEGER PRIMARY KEY,
            source_form       TEXT NOT NULL,
            source_language   TEXT NOT NULL CHECK (source_language IN
                ('grc', 'fra', 'deu', 'eng', 'lat', 'heb', 'ara')),
            transliteration   TEXT,
            lemma             TEXT,
            short_gloss       TEXT NOT NULL,
            long_description  TEXT NOT NULL,
            UNIQUE (source_form, source_language)
        );
        """,
        [],
    ),
]


def apply(conn: sqlite3.Connection) -> None:
    fk_prev = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    legacy_prev = conn.execute("PRAGMA legacy_alter_table").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA legacy_alter_table = ON")
    try:
        for table, ddl, indexes in _REBUILDS:
            conn.execute(ddl)
            conn.execute(f"INSERT INTO {table}__new SELECT * FROM {table}")
            conn.execute(f"DROP TABLE {table}")
            conn.execute(f"ALTER TABLE {table}__new RENAME TO {table}")
            for stmt in indexes:
                conn.execute(stmt)
        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise RuntimeError(f"0016 left dangling FKs after rebuild: {bad!r}")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.execute(f"PRAGMA legacy_alter_table = {legacy_prev}")
        conn.execute(f"PRAGMA foreign_keys = {'ON' if fk_prev else 'OFF'}")
