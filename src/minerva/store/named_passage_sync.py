"""Materialize ``authors/named_passages.py`` into the ``named_passages`` table.

Runs on every ``minerva index``, after the chunk insert has built
``works`` — same reasoning as ``work_alias_sync`` (#195), which this
mirrors: the declaration in code is keyed on the natural key
``(author, works.title)``, and this step resolves it to the surrogate
``works.id`` the DB needs, because ``--reset`` reassigns those ids
(#193).

Because it is derived, the sync is a full replace rather than an
upsert: a label removed from the code table must disappear from the DB.
"""

from __future__ import annotations

import sqlite3
import sys

from ..authors.named_passages import NAMED_PASSAGES


def sync_named_passages(conn: sqlite3.Connection) -> int:
    """Replace ``named_passages`` from the code declaration.

    Returns the number of rows written. A label naming a work that is
    not in this index — the normal case for a partial corpus — is
    skipped silently.
    """

    rows: list[tuple[int, str, str | None, str | None, str]] = []
    unresolved: list[tuple[str, str]] = []
    for (author, title), passages in NAMED_PASSAGES.items():
        found = conn.execute(
            "SELECT id FROM works WHERE author = ? AND title = ?", (author, title)
        ).fetchone()
        if found is None:
            unresolved.append((author, title))
            continue
        work_id = int(found[0])
        rows.extend(
            (work_id, p.label, p.section_start, p.section_end, p.tradition) for p in passages
        )

    conn.execute("DELETE FROM named_passages")
    conn.executemany(
        "INSERT OR IGNORE INTO named_passages "
        "(work_id, label, section_start, section_end, tradition) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()

    if unresolved and rows:
        shown = ", ".join(f"{a} — {t!r}" for a, t in unresolved[:5])
        more = f" (+{len(unresolved) - 5} more)" if len(unresolved) > 5 else ""
        print(
            f"named_passages: {len(unresolved)} entries name a work not in this "
            f"index: {shown}{more}",
            file=sys.stderr,
        )
    return len(rows)
