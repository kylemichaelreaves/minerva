"""0026_syntax_upos_correction.py — admit ``upos`` to the
``chunk_syntax_corrections.kind`` CHECK list.

A token's part of speech was displayed by the syntax inspector and read by
three layout consumers — row wrapping breaks after ``PUNCT``, the topological
field bands split around it, and ``isFiniteVerb`` (``VERBAL.has(upos)``) is
what places LINKE KLAMMER — while being the one part of the parse a curator
could not correct. Only ``head`` and ``deprel`` were admitted. See #253.

Same lite-rebuild pattern as 0010 / 0014 / 0015 / 0017, because SQLite cannot
ALTER a CHECK constraint: recreate the table with the widened list, copy rows,
drop, rename. PRAGMAs are read and restored around the rebuild and flipped
OUTSIDE the implicit transaction — see [[sqlite_migration_pragma_dance]].

Two things make this rebuild cheaper than its predecessors, and both are worth
stating because they will not hold next time:

* ``chunk_syntax_corrections`` carries **no foreign key** — deliberately, so
  the log survives a re-ingest that churns ``chunk_id`` — so nothing dangles.
* No view selects from it (contrast ``works``, which ``chunks_full`` wraps and
  which is why ``legacy_alter_table`` is in the dance at all). It is kept here
  anyway: the cost is one PRAGMA and the alternative is re-deriving that
  argument the next time someone copies this file.

The table is empty at the time of writing (0 rows), so no curatorial data is
at risk in this particular run. The INSERT..SELECT is still here because the
migration has to be correct on a populated database, not just on this one.
"""

from __future__ import annotations

import sqlite3

_REBUILD = """
CREATE TABLE chunk_syntax_corrections__new (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id   TEXT    NOT NULL,
    sent_ord   INTEGER NOT NULL,
    tok_id     INTEGER NOT NULL,
    kind       TEXT    NOT NULL CHECK (kind IN ('head', 'deprel', 'upos')),
    -- The value at the time of the edit, for provenance and for
    -- detecting that the underlying parse moved beneath a patch.
    -- Stored as TEXT for every kind; 'head' round-trips through int().
    from_val   TEXT,
    to_val     TEXT    NOT NULL,
    created_at REAL    NOT NULL
);
"""


def apply(conn: sqlite3.Connection) -> None:
    fk_prev = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    legacy_prev = conn.execute("PRAGMA legacy_alter_table").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA legacy_alter_table = ON")
    try:
        conn.execute(_REBUILD)
        # Column list spelled out rather than `SELECT *`: the id is an
        # AUTOINCREMENT and it is also the replay order, so it has to carry
        # over verbatim rather than be reassigned.
        conn.execute(
            "INSERT INTO chunk_syntax_corrections__new "
            "(id, chunk_id, sent_ord, tok_id, kind, from_val, to_val, created_at) "
            "SELECT id, chunk_id, sent_ord, tok_id, kind, from_val, to_val, created_at "
            "FROM chunk_syntax_corrections"
        )
        conn.execute("DROP TABLE chunk_syntax_corrections")
        conn.execute("ALTER TABLE chunk_syntax_corrections__new RENAME TO chunk_syntax_corrections")
        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise RuntimeError(f"0026 left dangling FKs after rebuild: {bad!r}")
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.execute(f"PRAGMA legacy_alter_table = {legacy_prev}")
        conn.execute(f"PRAGMA foreign_keys = {'ON' if fk_prev else 'OFF'}")
