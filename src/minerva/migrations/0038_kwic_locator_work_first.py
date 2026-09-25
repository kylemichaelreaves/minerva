"""0038_kwic_locator_work_first.py — lead the KWIC page index with the work (#656).

#649 (migration 0036) built `chunk_lemmas_by_locator` as `(lemma_fold,
lang_resolved, chunk_ord, surface_start, work_id)`, and the page walked it in
that order. `chunk_ord` is a chunk's position *within its own work*, so on a
corpus- or author-scope page every work's paragraph 0 sorted together: page 1
of `der`/deu was 50 opening paragraphs from 47 works, and `der` has an `ord`-0
row in 132 of its 258 works. 197,561 of the 557,214 lemma/language pairs span
more than one work, and each of them read that way.

The page now reads works in the Reader's order (`reader.queries.work_sort_key`)
and each work in paragraph order. That order depends on `AUTHOR_ORDINAL`, a
Python table, so no index can hold it. Instead `kwic_queries` plans the page
from the per-work counts the aggregate pass already returns, then seeks each
work it needs. That seek wants `work_id` ahead of `chunk_ord`, which is this
index.

The definition lives in `store.ddl`, which the `--reset` restore also rebuilds
from, so it is rebuilt here only when the existing index has the old column
order. A database that 0036 created from the current definition is left alone.
"""

from __future__ import annotations

import sqlite3

from minerva.store.ddl import chunk_lemmas_kwic_index_creates

_NAME = "chunk_lemmas_by_locator"
_WANT = ["lemma_fold", "lang_resolved", "work_id", "chunk_ord", "surface_start"]


def apply(conn: sqlite3.Connection) -> None:
    have = [row[2] for row in conn.execute(f"PRAGMA index_info({_NAME})")]
    if have == _WANT:
        return
    conn.execute(f"DROP INDEX IF EXISTS {_NAME}")
    for stmt in chunk_lemmas_kwic_index_creates():
        conn.execute(stmt)
