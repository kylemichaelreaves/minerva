"""Pre-index snapshot and preserved-state restore for ``minerva index``."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from .. import store
from ..sqlite_util import foreign_keys_disabled, table_exists


def _maybe_snapshot_pre_index(db_path: Path, *, incremental: bool = False) -> None:
    """Back up ``db_path`` to ``<db_path>.bak.pre-index`` when the DB
    carries cross_references, chunk_lemmas, OR embeddings rows.

    Three pieces of expensive state need to survive a ``--reset``:
    LLM-verified cross_references (hours to regenerate), chunk_lemmas
    (~10 min via LatinCy across grc+lat), and embeddings (~20 min to
    re-encode the full corpus). The snapshot is
    overwritten on each subsequent re-index — one snapshot, not a tower
    of them. No-op for fresh DBs (where neither table exists yet) and
    for fully-empty DBs.

    The copy goes through SQLite's backup API, NOT a filesystem copy:
    the DB runs in WAL mode, and a plain ``cp``/``copy2`` grabs the
    main file without the -wal sibling — silently dropping every
    not-yet-checkpointed commit (exactly the rows this snapshot exists
    to protect) and risking a torn copy if a checkpoint runs
    concurrently.

    Skipped for incremental runs: they only delete/reinsert the scoped
    corpora (the preserved tables aren't wiped), and a full backup of
    a multi-GB DB before every 1.5 s incremental index costs ~50× the
    operation it would guard.
    """

    if not db_path.exists():
        return
    if incremental:
        return
    # Read counts via a brand-new connection so we don't entangle with
    # the index pass's connection lifecycle. Closed immediately so the
    # file lock is free for the actual index run.
    probe = sqlite3.connect(db_path)
    try:
        xref_count = _count_or_zero(probe, "cross_references")
        lemma_count = _count_or_zero(probe, "chunk_lemmas")
        emb_count = _count_or_zero(probe, "embeddings")
        if xref_count == 0 and lemma_count == 0 and emb_count == 0:
            return
        backup = db_path.with_suffix(db_path.suffix + ".bak.pre-index")
        # Clear any prior snapshot (and its own WAL siblings) so the
        # backup lands in a fresh file rather than on top of stale pages.
        store.reset_db(backup)
        dest = sqlite3.connect(backup)
        try:
            probe.backup(dest)
        finally:
            dest.close()
    finally:
        probe.close()
    bits = []
    if xref_count:
        bits.append(f"{xref_count} cross_references")
    if lemma_count:
        bits.append(f"{lemma_count:,} chunk_lemmas")
    if emb_count:
        bits.append(f"{emb_count:,} embeddings")
    print(
        f"Snapshotted {' + '.join(bits)} to {backup} before re-index.",
        file=sys.stderr,
    )


def _count_or_zero(conn: sqlite3.Connection, table: str) -> int:
    """``SELECT COUNT(*) FROM <table>`` if the table exists; else 0."""

    if not table_exists(conn, table):
        return 0
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _maybe_restore_preserved_state_from_snapshot(
    conn: sqlite3.Connection, db_path: Path
) -> None:
    """Restore preserved xref/lemma/embedding rows from the pre-index snapshot."""

    backup = db_path.with_suffix(db_path.suffix + ".bak.pre-index")
    if not backup.exists():
        return
    for table in ("cross_references", "chunk_lemmas", "embeddings", "chunk_syntax_corrections"):
        if _count_or_zero(conn, table):
            return
    probe = sqlite3.connect(backup)
    try:
        xref_count = _count_or_zero(probe, "cross_references")
        lemma_count = _count_or_zero(probe, "chunk_lemmas")
        emb_count = _count_or_zero(probe, "embeddings")
        # Hand corrections to dependency trees. Unlike everything else
        # here these are not recomputable at any price — they are a
        # scholar's judgement about a sentence. `chunk_syntax_corrections`
        # carries no foreign key for the same reason (migration 0024).
        syntax_count = _count_or_zero(probe, "chunk_syntax_corrections")
    finally:
        probe.close()
    if xref_count == 0 and lemma_count == 0 and emb_count == 0 and syntax_count == 0:
        return

    with foreign_keys_disabled(conn):
        conn.execute("ATTACH DATABASE ? AS snap", (str(backup),))
        try:
            try:
                xref_restored = 0
                target_restored = 0
                if xref_count:
                    conn.execute("DELETE FROM cross_references")
                    conn.execute("DELETE FROM reference_targets")
                    target_restored = _restore_from_snap(conn, "reference_targets")
                    xref_restored = _restore_from_snap(conn, "cross_references")
                lemma_restored = 0
                if lemma_count:
                    lemma_restored = _restore_from_snap(conn, "chunk_lemmas")
                syntax_restored = 0
                if syntax_count:
                    syntax_restored = _restore_from_snap(conn, "chunk_syntax_corrections")
                emb_restored = 0
                if emb_count:
                    emb_restored = _restore_from_snap(conn, "embeddings")
                    from .embeddings import bump_embedding_generation

                    bump_embedding_generation(conn)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            if xref_restored or target_restored:
                print(
                    f"Restored {xref_restored} cross_references + "
                    f"{target_restored} reference_targets from {backup}; "
                    f"rebind will rebind to the new chunks.",
                    file=sys.stderr,
                )
            if syntax_restored:
                print(
                    f"Restored {syntax_restored:,} chunk_syntax_corrections "
                    f"from {backup}.",
                    file=sys.stderr,
                )
            if lemma_restored:
                print(
                    f"Restored {lemma_restored:,} chunk_lemmas from {backup}; "
                    f"orphan sweep will drop rows whose chunk text changed.",
                    file=sys.stderr,
                )
            if emb_restored:
                print(
                    f"Restored {emb_restored:,} embeddings from {backup}; "
                    f"orphan sweep will drop rows whose chunk text changed.",
                    file=sys.stderr,
                )
        finally:
            conn.execute("DETACH DATABASE snap")


def _restore_from_snap(conn: sqlite3.Connection, table: str) -> int:
    """Bulk-copy ``snap.<table>`` into the live ``<table>``."""

    cols = ", ".join(
        row[1] for row in conn.execute(f"PRAGMA table_info({table})")
    )
    conn.execute(
        f"INSERT INTO {table} ({cols}) SELECT {cols} FROM snap.{table}"
    )
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
