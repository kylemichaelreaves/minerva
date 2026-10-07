"""Migration 0035 re-links `reference_targets` rows whose work is in
the corpus under a differently-cased title (#493, claim 3).

`ensure_target` resolves `(canonical_author, canonical_work)` onto a
`works` row by exact title match, and — deliberately — returns an
existing target row unchanged rather than re-resolving it ("do not
update — curator can edit via the CLI explicitly", `refs/schema.py`).
So a target created while its work was out of corpus stays
`in_corpus_work_id = NULL` forever, even once the corpus gains the work.

Four of migration 0012's `_OUT_OF_CORPUS_SEED` rows are in that state on
the live index: Cicero's *De republica*, *Tusculanae disputationes*, *De
finibus bonorum et malorum* and *De natura deorum*, all of which the
corpus now holds under title-cased spellings. `'Tusculanae
disputationes'` differs from the in-corpus title by one letter's case.

The fold added to `ensure_target` in the same change fixes targets
created from here on. It cannot reach rows that already exist, because
nothing re-resolves them — which is what this migration is for. These
tests use the 0012 seed rows themselves rather than inserting their own,
so the fixture is the production shape.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from conftest import make_chunk

from minerva import store

_SEEDED_CICERO_WORKS = [
    ("De Re Publica", "rep"),
    ("Tusculanae Disputationes", "tus"),
    ("De Natura Deorum", "nat"),
]


def _db_at_0034(tmp_path: Path, *, extra: str | None = None) -> Path:
    """An index holding Cicero works under their title-cased spellings,
    with migration 0035 unrecorded so the runner replays it."""

    path = tmp_path / "pre-0035.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    chunks = [
        make_chunk(chunk_id=cid, work=title, author="Cicero", text=f"text of {title}")
        for title, cid in _SEEDED_CICERO_WORKS
    ]
    jsonl.write_text("\n".join(json.dumps(c) for c in chunks))
    conn = store.open_db(path)
    store.insert_chunks(conn, jsonl)
    if extra is not None:
        conn.execute(
            "INSERT INTO works (author, title, original_language, citation_system) "
            "VALUES ('Cicero', ?, 'lat', 'paragraph')",
            (extra,),
        )
    # The state 0035 repairs: fold-linkable targets left NULL. Until #800
    # the index's exact-only rebind produced it by itself; the rebind now
    # shares 0035's folded resolver and links them at insert, so the
    # fixture has to put the NULLs back.
    conn.execute(
        "UPDATE reference_targets SET in_corpus_work_id = NULL WHERE canonical_author = 'Cicero'"
    )
    conn.execute("DELETE FROM schema_migrations WHERE version = 35")
    conn.commit()
    conn.close()
    return path


def _link(conn: sqlite3.Connection, work: str) -> int | None:
    return conn.execute(
        "SELECT in_corpus_work_id FROM reference_targets WHERE canonical_work = ?",
        (work,),
    ).fetchone()[0]


def _work_id(conn: sqlite3.Connection, title: str) -> int:
    return int(
        conn.execute(
            "SELECT id FROM works WHERE author = 'Cicero' AND title = ?", (title,)
        ).fetchone()[0]
    )


def test_case_drifted_seed_rows_are_relinked(tmp_path: Path):
    """The three seeded titles this fixture's corpus actually holds."""

    path = _db_at_0034(tmp_path)

    conn = store.open_db(path)  # applies 0035
    try:
        assert _link(conn, "De republica") == _work_id(conn, "De Re Publica")
        assert _link(conn, "Tusculanae disputationes") == _work_id(conn, "Tusculanae Disputationes")
        assert _link(conn, "De natura deorum") == _work_id(conn, "De Natura Deorum")
    finally:
        conn.close()


def test_genuinely_out_of_corpus_target_stays_null(tmp_path: Path):
    """`Hortensius` is a lost dialogue and is seeded as out-of-corpus on
    purpose; `De finibus bonorum et malorum` is simply not in this
    fixture's corpus. A repair that linked either would be worse than
    the drift it fixes."""

    path = _db_at_0034(tmp_path)

    conn = store.open_db(path)
    try:
        assert _link(conn, "Hortensius") is None
        assert _link(conn, "De finibus bonorum et malorum") is None
    finally:
        conn.close()


def test_already_linked_target_is_left_alone(tmp_path: Path):
    """Only a NULL link is this migration's business. A link that is
    non-NULL and wrong is #273's stale-id repair, and silently
    re-resolving one here would hide that."""

    path = _db_at_0034(tmp_path)
    conn = store.open_db(path)
    wrong = _work_id(conn, "Tusculanae Disputationes")
    conn.execute(
        "UPDATE reference_targets SET in_corpus_work_id = ? WHERE canonical_work = 'De republica'",
        (wrong,),
    )
    conn.execute("DELETE FROM schema_migrations WHERE version = 35")
    conn.commit()
    conn.close()

    conn = store.open_db(path)  # replays 0035
    try:
        assert _link(conn, "De republica") == wrong
    finally:
        conn.close()


def test_ambiguous_title_is_not_relinked(tmp_path: Path):
    """Two works folding to the same key: declining is the only
    non-arbitrary answer, and a NULL stays visibly unresolved."""

    path = _db_at_0034(tmp_path, extra="DE RE PUBLICA")

    conn = store.open_db(path)
    try:
        assert _link(conn, "De republica") is None
    finally:
        conn.close()
