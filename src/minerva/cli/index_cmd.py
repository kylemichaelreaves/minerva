"""``minerva index`` — load chunks JSONL into ``data/index.sqlite``.

Also exposes the pre-index DB snapshot helper so re-indexes don't
silently lose cross_references rows on a partial write.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

from .. import store
from ._shared import (
    DEFAULT_CHUNKS,
    Timer,
    add_common_db_arg,
    fmt_elapsed,
    record_timing,
)


def cmd_index(args: argparse.Namespace) -> int:
    # Resolve the corpus scope for incremental mode. --from-ingest-only
    # reads the most recent `minerva ingest --only X` invocation from
    # the meta table; --corpora gives an explicit CSV slug list. They
    # can be combined; the union wins.
    #
    # Library-style callers (tests, scripted reindex helpers) may build
    # a Namespace without these attrs; getattr-with-default keeps the
    # legacy ``--reset``-only call shape working.
    scope = _resolve_incremental_scope(args)
    incremental = bool(
        getattr(args, "incremental", False)
        or getattr(args, "corpora", "")
        or getattr(args, "from_ingest_only", False)
    )
    if incremental and not scope:
        print(
            "index --incremental needs a scope: pass --corpora a,b OR "
            "--from-ingest-only after a prior `minerva ingest --only X`.",
            file=sys.stderr,
        )
        return 2
    if incremental and args.reset:
        print(
            "index --incremental is incompatible with --reset (the whole "
            "point of incremental is to NOT wipe the DB).",
            file=sys.stderr,
        )
        return 2

    # Pre-index safeguard: re-ingest rebuilds chunks/editions/works/
    # translations from scratch, and the cross_references rows have to
    # be rebound to the freshly-inserted FK targets (see store.py). If
    # anything goes wrong mid-rebind, we want a one-`cp` recovery path.
    # Snapshot the DB whenever it carries non-trivial cross-reference
    # state (LLM-verified rows can take hours to regenerate). MUST run
    # BEFORE `--reset` unlinks the existing DB — otherwise the snapshot
    # finds no file and silently no-ops, taking all xrefs with the
    # re-index. (That's how 21,751 cross_references got wiped on the
    # 2026-05-29 Hegel-Preface rechunk re-ingest.)
    _maybe_snapshot_pre_index(args.db)
    if args.reset and args.db.exists():
        args.db.unlink()
    conn = store.open_db(args.db)
    # If `--reset` just deleted the DB, the fresh schema has no
    # cross_references / chunk_lemmas rows — meaning the rebind step
    # in ``insert_chunks`` (xrefs) and the lemmatize ``NOT EXISTS``
    # skip (lemmas) would both have nothing to work with. Pre-seed
    # both tables from the ``.bak.pre-index`` snapshot so the
    # downstream paths reconnect to the rows naturally. Idempotent /
    # no-op when the snapshot is missing or already-empty.
    with Timer() as overall:
        _maybe_restore_preserved_state_from_snapshot(conn, args.db)
        with Timer() as t_insert:
            if incremental:
                print(
                    f"Incremental index: corpora={sorted(scope)!r}",
                    file=sys.stderr,
                )
                n = store.insert_chunks(
                    conn,
                    args.input,
                    mode="incremental",
                    corpora=scope,
                )
            else:
                n = store.insert_chunks(conn, args.input)
        # Post-insert orphan sweep for chunk_lemmas. Chunks whose text
        # genuinely changed get a fresh chunk_id (content-hashed);
        # their pre-restored lemma rows now point at a non-existent
        # chunk. With FK enforcement re-enabled by ``insert_chunks``,
        # leaving orphans would block subsequent writes. Idempotent —
        # no-op when the lemmas table is empty or all chunk_ids
        # survived.
        _sweep_orphan_chunk_lemmas(conn)

    print(f"Loaded {n} chunks into {args.db}")
    print(json.dumps(store.stats(conn), indent=2, default=str))
    # ``getattr`` so library-style callers building their own Namespace
    # (tests, scripted reindex helpers) don't have to set --timing.
    if getattr(args, "timing", False):
        print(
            f"timing: index:insert  {fmt_elapsed(t_insert.elapsed)}",
            file=sys.stderr,
        )
        print(f"timing: index  {fmt_elapsed(overall.elapsed)}", file=sys.stderr)
    record_timing(args.db, "index", overall.elapsed)
    return 0


def _maybe_snapshot_pre_index(db_path: Path) -> None:
    """Copy ``db_path`` to ``<db_path>.bak.pre-index`` when the DB
    carries cross_references OR chunk_lemmas rows.

    Two pieces of expensive state need to survive a ``--reset``:
    LLM-verified cross_references (hours to regenerate) and
    chunk_lemmas (~10 min via LatinCy across grc+lat). The snapshot is
    overwritten on each subsequent re-index — one snapshot, not a tower
    of them. No-op for fresh DBs (where neither table exists yet) and
    for fully-empty DBs.
    """

    if not db_path.exists():
        return
    # Read counts via a brand-new connection so we don't entangle with
    # the index pass's connection lifecycle. Closed immediately so the
    # file lock is free for the actual index run.
    probe = sqlite3.connect(db_path)
    try:
        xref_count = _count_or_zero(probe, "cross_references")
        lemma_count = _count_or_zero(probe, "chunk_lemmas")
    finally:
        probe.close()
    if xref_count == 0 and lemma_count == 0:
        return
    backup = db_path.with_suffix(db_path.suffix + ".bak.pre-index")
    shutil.copy2(db_path, backup)
    bits = []
    if xref_count:
        bits.append(f"{xref_count} cross_references")
    if lemma_count:
        bits.append(f"{lemma_count:,} chunk_lemmas")
    print(
        f"Snapshotted {' + '.join(bits)} to {backup} before re-index.",
        file=sys.stderr,
    )


def _count_or_zero(conn: sqlite3.Connection, table: str) -> int:
    """``SELECT COUNT(*) FROM <table>`` if the table exists; else 0.
    Used by ``_maybe_snapshot_pre_index`` so a fresh DB (which may
    have either or both tables before any rows are inserted) doesn't
    crash on missing schema."""

    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if row is None:
        return 0
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _maybe_restore_preserved_state_from_snapshot(
    conn: sqlite3.Connection, db_path: Path
) -> None:
    """Restore ``reference_targets`` + ``cross_references`` AND
    ``chunk_lemmas`` rows from ``<db_path>.bak.pre-index`` into the
    freshly-opened ``conn``.

    The auto-snapshot pre-``--reset`` (``_maybe_snapshot_pre_index``)
    is a backup, not a restore. When the user passes ``--reset``,
    the DB file is unlinked and the new schema starts empty — so
    the cross_references rebind in ``store.insert_chunks`` and the
    ``terms lemmatize`` ``NOT EXISTS`` skip both have nothing to work
    with. This helper closes the loop for both: ATTACH the snapshot,
    INSERT the preserved rows, then let ``insert_chunks`` (xrefs)
    and ``_sweep_orphan_chunk_lemmas`` (lemmas) re-anchor them
    against the new chunks.

    Why preserving lemmas matters: ``chunk_lemmas`` is recomputed by
    ``terms lemmatize``, which is ~5-10 minutes per language with
    LatinCy spaCy backends (Greek + Latin together = ~10 min). Most
    re-ingests change one or two corpora, leaving the other ~40
    untouched — and chunk_ids are content-hashed, so unchanged
    chunks keep the same id. Preserving lemmas keyed by chunk_id
    means a content-stable re-ingest skips lemmatize entirely.

    No-op when the snapshot file is missing, when both preserved
    tables are empty in the snapshot, or when the live DB already
    carries those rows (i.e. ``--reset`` wasn't used).
    """

    backup = db_path.with_suffix(db_path.suffix + ".bak.pre-index")
    if not backup.exists():
        return
    # If the live DB already carries xref rows, the regular rebind path
    # (and the existing lemmas) will handle things; skip to avoid
    # double-inserting.
    existing = conn.execute("SELECT COUNT(*) FROM cross_references").fetchone()[0]
    if existing:
        return
    # Probe the snapshot for what it has.
    probe = sqlite3.connect(backup)
    try:
        has_xrefs = probe.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='cross_references'"
        ).fetchone() is not None
        xref_count = (
            probe.execute("SELECT COUNT(*) FROM cross_references").fetchone()[0]
            if has_xrefs else 0
        )
        has_lemmas = probe.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='chunk_lemmas'"
        ).fetchone() is not None
        lemma_count = (
            probe.execute("SELECT COUNT(*) FROM chunk_lemmas").fetchone()[0]
            if has_lemmas else 0
        )
        has_emb = probe.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='embeddings'"
        ).fetchone() is not None
        emb_count = (
            probe.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
            if has_emb else 0
        )
    finally:
        probe.close()
    if xref_count == 0 and lemma_count == 0 and emb_count == 0:
        return

    # ATTACH the snapshot and copy rows. FK enforcement is temporarily
    # disabled because the source/target edition/translation surrogate
    # ids point at the OLD ingest's rows (which will be re-inserted
    # moments later by ``insert_chunks``), and chunk_lemmas.chunk_id
    # FK-references a chunks table that's still empty at this point.
    # The xref FK integrity check after rebind catches genuine breakage;
    # the post-insert ``_sweep_orphan_chunk_lemmas`` handles lemma
    # orphans.
    fk_prev = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute(f"ATTACH DATABASE '{backup}' AS snap")
        try:
            xref_restored = 0
            target_restored = 0
            if xref_count:
                # A fresh-DB ``open_db`` already seeds out-of-corpus
                # reference_targets (Celsus, etc.) from migrations. Clear
                # both tables before re-populating from the snapshot so
                # the bulk INSERT doesn't collide on the PK. order matters
                # — cross_references FK-references reference_targets, so
                # delete the child first.
                conn.execute("DELETE FROM cross_references")
                conn.execute("DELETE FROM reference_targets")
                conn.execute(
                    "INSERT INTO reference_targets SELECT * FROM snap.reference_targets"
                )
                conn.execute(
                    "INSERT INTO cross_references SELECT * FROM snap.cross_references"
                )
                xref_restored = conn.execute(
                    "SELECT COUNT(*) FROM cross_references"
                ).fetchone()[0]
                target_restored = conn.execute(
                    "SELECT COUNT(*) FROM reference_targets"
                ).fetchone()[0]
            lemma_restored = 0
            if lemma_count:
                # chunk_lemmas is empty in a fresh DB; just bulk-insert.
                conn.execute(
                    "INSERT INTO chunk_lemmas SELECT * FROM snap.chunk_lemmas"
                )
                lemma_restored = conn.execute(
                    "SELECT COUNT(*) FROM chunk_lemmas"
                ).fetchone()[0]
            emb_restored = 0
            if emb_count:
                # ``embeddings.chunk_id`` is a PK with CASCADE-on-delete to
                # ``chunks``; a fresh DB has zero rows. Bulk-insert from
                # snapshot; the post-insert orphan sweep handles
                # chunk_ids that changed text. Without this, every
                # ``index --reset`` re-encodes the entire corpus —
                # ~20 min on 344K chunks — even when only a single
                # source's content changed.
                conn.execute(
                    "INSERT INTO embeddings SELECT * FROM snap.embeddings"
                )
                emb_restored = conn.execute(
                    "SELECT COUNT(*) FROM embeddings"
                ).fetchone()[0]
            # Commit before DETACH — SQLite refuses to detach a
            # database with open writes pending on the connection.
            conn.commit()
            if xref_restored or target_restored:
                print(
                    f"Restored {xref_restored} cross_references + "
                    f"{target_restored} reference_targets from {backup}; "
                    f"rebind will rebind to the new chunks.",
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
    finally:
        conn.execute(f"PRAGMA foreign_keys = {'ON' if fk_prev else 'OFF'}")


def _sweep_orphan_chunk_lemmas(conn: sqlite3.Connection) -> None:
    """Delete chunk_lemmas + embeddings rows whose chunk_id no longer
    exists in ``chunks``. Required after a snapshot-restore because
    chunks whose text genuinely changed get a fresh content-hashed
    chunk_id — the restored rows now point at the OLD id, leaving
    FK-orphans that would block subsequent writes once FK enforcement
    re-engages.

    Cheap when the tables are empty (typical fresh-ingest case) or
    when every chunk_id survived (typical content-stable reingest).
    """

    _sweep_orphan_table(conn, "chunk_lemmas")
    _sweep_orphan_table(conn, "embeddings")


def _sweep_orphan_table(conn: sqlite3.Connection, table: str) -> None:
    """Generic orphan sweep — ``DELETE FROM <table> WHERE chunk_id NOT
    IN (SELECT chunk_id FROM chunks)``. Used by the post-insert hook
    to clean both ``chunk_lemmas`` and ``embeddings`` after the
    snapshot-restore loop."""

    if conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is None:
        return
    if conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() is None:
        return
    before = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.execute(
        f"DELETE FROM {table} WHERE chunk_id NOT IN "
        "(SELECT chunk_id FROM chunks)"
    )
    after = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.commit()
    dropped = before - after
    if dropped:
        print(
            f"Dropped {dropped:,} orphan {table} (chunks whose text "
            f"changed); {after:,} rows preserved.",
            file=sys.stderr,
        )


def _resolve_incremental_scope(args: argparse.Namespace) -> frozenset[str]:
    """Resolve the union of --corpora and --from-ingest-only into a
    set of corpus slugs to scope an incremental rebuild to.

    --corpora takes a CSV list of corpus slugs (matching the JSONL
    ``corpus`` field, e.g. ``"hegel"``, ``"plato"``).

    --from-ingest-only reads ``meta.ingest.only`` set by the prior
    ``minerva ingest --only X Y Z`` invocation and maps each IngestSource
    id to its corpus slug via ``ingest/registry.py``. Multi-source-per-
    corpus authors (e.g. ``aesop`` + ``aesop_babrius`` both yielding
    ``corpus="aesop"`` chunks) deduplicate naturally through the set.

    Returns an empty frozenset when neither flag carries content.
    """

    scope: set[str] = set()
    corpora_csv = getattr(args, "corpora", "") or ""
    if corpora_csv:
        for slug in corpora_csv.split(","):
            slug = slug.strip()
            if slug:
                scope.add(slug)
    if getattr(args, "from_ingest_only", False):
        if not args.db.exists():
            print(
                "--from-ingest-only: index DB doesn't exist yet; nothing "
                "to read meta.ingest.only from.",
                file=sys.stderr,
            )
        else:
            scope |= _read_ingest_only_meta(args.db)
    return frozenset(scope)


def _read_ingest_only_meta(db_path: Path) -> set[str]:
    """Read ``meta.ingest.only`` and map IngestSource ids → corpus slugs.

    The mapping handles multi-source-per-corpus authors (the IngestSource
    id ``aesop_babrius`` maps to corpus slug ``aesop``, etc.). When no
    prior ``--only`` invocation has run, returns an empty set with a
    stderr note for the operator.
    """

    probe = sqlite3.connect(db_path)
    try:
        row = probe.execute(
            "SELECT value FROM meta WHERE key='ingest.only'"
        ).fetchone()
    except sqlite3.OperationalError:
        # Fresh DB / meta table missing.
        row = None
    finally:
        probe.close()
    if not row or not row[0]:
        print(
            "--from-ingest-only: no `meta.ingest.only` recorded; run "
            "`minerva ingest --only X` first.",
            file=sys.stderr,
        )
        return set()
    only_ids = {s.strip() for s in row[0].split(",") if s.strip()}
    from ..ingest.registry import corpus_slugs_for_ingest_ids

    return corpus_slugs_for_ingest_ids(only_ids)


def register(parent_subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    px = parent_subparsers.add_parser("index", help="Load chunks JSONL into SQLite/FTS5.")
    add_common_db_arg(px)
    px.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_CHUNKS,
        help="Input JSONL produced by `minerva ingest`.",
    )
    px.add_argument(
        "--reset",
        action="store_true",
        help="Delete the existing index first.",
    )
    px.add_argument(
        "--incremental",
        action="store_true",
        help=(
            "Corpus-scoped re-index — only the chunks in the named "
            "corpora are deleted + re-inserted. Pair with --corpora "
            "or --from-ingest-only. Incompatible with --reset."
        ),
    )
    px.add_argument(
        "--corpora",
        type=str,
        default="",
        help=(
            "CSV of corpus slugs scoping --incremental (e.g. "
            "'hegel,plato'). The slug must match the JSONL `corpus` "
            "field."
        ),
    )
    px.add_argument(
        "--from-ingest-only",
        action="store_true",
        dest="from_ingest_only",
        help=(
            "Read the most recent `ingest --only X Y` invocation from "
            "meta.ingest.only and scope --incremental to those corpora. "
            "Standard post-ingest flow: "
            "`minerva ingest --only X; minerva index --incremental "
            "--from-ingest-only`."
        ),
    )
    px.add_argument(
        "--timing",
        action="store_true",
        help=(
            "Print stage timings (insert, overall) to stderr; the "
            "overall wall time is persisted to meta.timing.index "
            "regardless."
        ),
    )
    px.set_defaults(func=cmd_index)
