"""``minerva index`` — load chunks JSONL into ``data/index.sqlite``.

Also exposes the pre-index DB snapshot helper so re-indexes don't
silently lose cross_references rows on a partial write.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .. import serve_lock, store
from ..sqlite_util import sweep_orphan_chunk_ids
from ..store.preserved_state import (
    _maybe_restore_preserved_state_from_snapshot,
    _maybe_snapshot_pre_index,
)
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
    _maybe_snapshot_pre_index(args.db, incremental=incremental)
    if args.reset:
        running = serve_lock.find_running_server(args.db)
        if running:
            print(
                f"index --reset refused: minerva serve is already running "
                f"({running}) against {args.db}. Stop the server first.",
                file=sys.stderr,
            )
            return 2
        # reset_db also unlinks the -wal/-shm siblings — a stale WAL
        # next to a freshly-created file is a corruption vector.
        store.reset_db(args.db)
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

    for table in ("chunk_lemmas", "embeddings"):
        dropped = sweep_orphan_chunk_ids(conn, table)
        if dropped:
            remaining = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(
                f"Dropped {dropped:,} orphan {table} (chunks whose text "
                f"changed); {remaining:,} rows preserved.",
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
