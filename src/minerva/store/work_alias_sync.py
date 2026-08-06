"""Materialize ``authors/work_aliases.py`` into the ``work_aliases`` table.

Runs on every ``minerva index``, after the chunk insert has built
``works``. The table is derived state, never curated: the declaration in
code is keyed on ``(author, works.title)`` — a natural key — and this
step resolves it to the surrogate ``works.id`` the DB needs. That
resolution has to happen after every re-ingest, because ``--reset``
reassigns those ids (#193).

Because it is derived, the sync is a full replace rather than an upsert:
an alias deleted from the code table must disappear from the DB, and the
only way to notice that is to rebuild the set.
"""

from __future__ import annotations

import sqlite3
import sys

from ..authors.work_aliases import ALIASES


def sync_work_aliases(conn: sqlite3.Connection) -> int:
    """Replace ``work_aliases`` from the code declaration.

    Returns the number of alias rows written. Aliases naming a work that
    is not in this index — the normal case for a partial corpus — are
    skipped silently; an author whose works are simply not ingested is
    not an error.
    """

    rows: list[tuple[int, str]] = []
    unresolved: list[tuple[str, str]] = []
    for (author, title), names in ALIASES.items():
        found = conn.execute(
            "SELECT id FROM works WHERE author = ? AND title = ?", (author, title)
        ).fetchone()
        if found is None:
            unresolved.append((author, title))
            continue
        rows.extend((int(found[0]), name) for name in names)

    conn.execute("DELETE FROM work_aliases")
    conn.executemany("INSERT OR IGNORE INTO work_aliases (work_id, alias) VALUES (?, ?)", rows)
    conn.commit()

    # Worth a line, because the usual cause of a work not resolving is
    # that its title changed under the alias table — which silently
    # un-does the fix the alias existed to make.
    if unresolved and rows:
        shown = ", ".join(f"{a} — {t!r}" for a, t in unresolved[:5])
        more = f" (+{len(unresolved) - 5} more)" if len(unresolved) > 5 else ""
        print(
            f"work_aliases: {len(unresolved)} entries name a work not in this index: {shown}{more}",
            file=sys.stderr,
        )
    return len(rows)
