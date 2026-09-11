"""0035_relink_targets.py — re-link targets held out of the corpus by
title casing (#493, claim 3).

`ensure_target` resolves `(canonical_author, canonical_work)` onto a
`works` row by exact title match, and returns an existing target row
unchanged rather than re-resolving it — deliberately, so a curator's
edit is not overwritten by the next rules pass. The two together mean a
target created while its work was out of corpus keeps
`in_corpus_work_id = NULL` for good, and an exact-match miss is silent:
the row simply reads as out-of-corpus and nothing says why.

Migration 0012 seeded twenty "out-of-corpus" targets so the obvious ones
were "available without typo drift on day one". Cicero has since been
ingested, and four of those rows now name works the corpus holds, missing
only on capitalization — `'Tusculanae disputationes'` against
`'Tusculanae Disputationes'` differs by one letter. All four carry zero
`cross_references` today, so nothing is being repaired retroactively;
what this prevents is the next Augustine or Aquinas cite landing on a
target that reads out-of-corpus while the text is right there.

Scope, deliberately narrow:

* Only rows with a **NULL** `in_corpus_work_id`. A link that is non-NULL
  and wrong is a different defect with its own repair (#273's stale-id
  path); re-resolving one here would hide it.
* Only when the fold matches **exactly one** work of that author.
  Picking among several would be arbitrary, and a NULL is visibly
  unresolved where a wrong id reads as resolved.

Idempotent: re-running finds nothing left to link.
"""

from __future__ import annotations

import sqlite3

from minerva.refs.schema import find_work_by_title_key


def apply(conn: sqlite3.Connection) -> None:
    unlinked = conn.execute(
        "SELECT id, canonical_author, canonical_work FROM reference_targets "
        "WHERE in_corpus_work_id IS NULL AND canonical_work <> '*'"
    ).fetchall()
    for target_id, author, work in unlinked:
        match = find_work_by_title_key(conn, author=str(author), title=str(work))
        if match is None:
            continue
        conn.execute(
            "UPDATE reference_targets SET in_corpus_work_id = ? WHERE id = ?",
            (match[0], target_id),
        )
