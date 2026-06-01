"""0009_latin_support.py — admit `lat` to every language-code CHECK.

Four tables carry a CHECK list of allowed language codes from
migration 0001 (`works.original_language`, `editions.language`,
`translations.language`, `terms.source_language`). SQLite can't alter
a CHECK in place, so each is rebuilt via the canonical 12-step
lite-rebuild dance: PRAGMA foreign_keys OFF → recreate with new
constraint → copy rows → drop original → rename → check FKs → ON.

What this enables: Descartes (Latin originals + French translations)
and any future Latin-source author can now land in `works` /
`editions` / `translations`, and Latin terms can be authored against
`terms.source_language='lat'`.

What this does NOT touch:
- `term_occurrences.location_kind` — Descartes ships initially with
  `paragraph` (the Gutenberg/ABU plaintext doesn't carry AT page
  markers). A later migration will add `at` when an AT-tagged source
  is sourced.
- `fra` — already in every CHECK list since 0001.
- Anything outside the four tables; the column definitions are
  preserved byte-for-byte except for the CHECK clause.
- `editions.is_canonical` and its dependent unique-index — kept
  intact since this migration only widens the language CHECK list.
"""

from __future__ import annotations

import sqlite3

# Each entry: (table_name, full CREATE TABLE body using the __new
# suffix, list of CREATE INDEX statements to re-issue after the
# rename). The DDL bodies must match the original column order
# (including any columns added by later migrations like 0004's
# `is_canonical`) so `INSERT INTO __new SELECT * FROM old` copies
# cleanly.
_REBUILDS: list[tuple[str, str, list[str]]] = [
    (
        "works",
        """
        CREATE TABLE works__new (
            id                  INTEGER PRIMARY KEY,
            author              TEXT NOT NULL,
            title               TEXT NOT NULL,
            original_language   TEXT NOT NULL CHECK (original_language IN
                ('grc', 'fra', 'deu', 'eng', 'lat')),
            citation_system     TEXT NOT NULL CHECK (citation_system IN
                ('stephanus', 'bekker', 'kant_ab', 'sz_marginal', 'paragraph')),
            UNIQUE (author, title)
        );
        """,
        [],  # no extra indexes on works
    ),
    (
        "editions",
        """
        CREATE TABLE editions__new (
            id           INTEGER PRIMARY KEY,
            work_id      INTEGER NOT NULL REFERENCES works(id) ON DELETE CASCADE,
            name         TEXT NOT NULL,
            language     TEXT NOT NULL CHECK (language IN
                ('grc', 'fra', 'deu', 'eng', 'lat')),
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
                ('grc', 'fra', 'deu', 'eng', 'lat')),
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
                ('grc', 'fra', 'deu', 'eng', 'lat')),
            transliteration   TEXT,
            lemma             TEXT,
            short_gloss       TEXT NOT NULL,
            long_description  TEXT NOT NULL,
            UNIQUE (source_form, source_language)
        );
        """,
        [],  # term indexes from 0001 are on dependent tables, not on terms itself
    ),
]


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
        for table, ddl, indexes in _REBUILDS:
            # Use `execute`, NOT `executescript` — the latter does an
            # implicit COMMIT before running, which would prematurely
            # close the runner's transaction. The DDL strings are
            # carefully single-statement so a plain `execute` is fine.
            conn.execute(ddl)
            conn.execute(
                f"INSERT INTO {table}__new SELECT * FROM {table}"
            )
            conn.execute(f"DROP TABLE {table}")
            conn.execute(f"ALTER TABLE {table}__new RENAME TO {table}")
            for stmt in indexes:
                conn.execute(stmt)
        # Sanity: any FK that would have been broken by the rebuild
        # surfaces here. An empty list means every reference still
        # resolves to a real row.
        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise RuntimeError(
                f"0009 left dangling FKs after rebuild: {bad!r}"
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
