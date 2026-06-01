"""``minerva ingest`` — parse Perseus TEI XML into ``data/chunks.jsonl``.

Three knobs control the work shape:

* **Full vs. partial** — ``--only <id>[,<id>...]`` re-parses just the
  named sources and overlays their chunks onto the existing JSONL by
  corpus (every row for the touched corpora gets replaced). Default
  is to parse everything and overwrite.
* **Sequential vs. parallel** — ``--jobs N`` (default 1) parallelizes
  per-source parsing via :class:`ProcessPoolExecutor`. Each source
  writes a shard JSONL, and the orchestrator merges shards in
  registry order so the final ``chunks.jsonl`` is deterministic
  regardless of worker scheduling.
* **Timing** — ``--timing`` prints per-source and overall wall times
  to stderr; the overall duration is persisted to
  ``meta.timing.ingest``.

Phases 0 + 1b + 2 of the 2026-05-29 ingestion-bottleneck remediation
plan all converge here.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from ..ingest import (
    _merge_dicts_to_jsonl,
    iter_corpus_chunks,
    load_jsonl,
    merge_jsonl,
    write_jsonl,
)
from ..ingest.parallel import concat_shards, parallel_ingest
from ..ingest.registry import INGEST_SOURCES, build_iter_corpus_kwargs
from ._shared import DEFAULT_CHUNKS, DEFAULT_DB, Timer, fmt_elapsed, record_timing


def cmd_ingest(args: argparse.Namespace) -> int:
    overrides = {
        source.kwarg_name: getattr(args, source.kwarg_name, None)
        for source in INGEST_SOURCES
    }

    only: frozenset[str] | None = None
    if args.only:
        requested = frozenset(s.strip() for s in args.only.split(",") if s.strip())
        known_ids = {source.id for source in INGEST_SOURCES}
        unknown = requested - known_ids
        if unknown:
            print(
                f"ingest: unknown --only source ids: {sorted(unknown)!r}. "
                f"Known ids: {sorted(known_ids)!r}",
                file=sys.stderr,
            )
            return 2
        only = requested

    with Timer() as overall:
        if args.jobs > 1:
            total, touched, counts, mode = _parallel_ingest_path(
                args, only, overrides
            )
        else:
            chunks = iter_corpus_chunks(
                only=only,
                per_source_timing=args.timing,
                **overrides,
            )
            if only is None:
                # Full ingest — overwrite ``chunks.jsonl``.
                n, counts = write_jsonl(chunks, args.output)
                total = n
                touched = n
                mode = "wrote"
            else:
                # Partial ingest — overlay onto existing JSONL.
                total, touched, counts = merge_jsonl(chunks, args.output)
                mode = "merged"

    print(f"{mode.capitalize()} {touched} chunks into {args.output} (total: {total})")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")

    if args.timing:
        print(f"timing: ingest  {fmt_elapsed(overall.elapsed)}", file=sys.stderr)
    # Persist overall timing so `minerva stats` can surface the last
    # run without re-running with --timing. No-op when the DB doesn't
    # exist yet (fresh checkout, pre-index).
    record_timing(args.db, "ingest", overall.elapsed)
    # Persist the --only IngestSource ids so a subsequent
    # ``minerva index --incremental --from-ingest-only`` can pick them
    # up as the scope. No-op when --only wasn't passed (full ingests
    # don't need an incremental rescope) or when the DB is missing.
    _record_ingest_only(args.db, only)
    return 0


def _record_ingest_only(db_path: Path, only: frozenset[str] | None) -> None:
    """Write the most recent ``--only`` argument list to ``meta.ingest.only``.

    Idempotent (overwrites the prior value each ingest). The
    counterpart reader is :func:`minerva.cli.index_cmd._read_ingest_only_meta`,
    which maps IngestSource ids → corpus slugs and scopes
    ``index --incremental`` to those corpora.

    No-op when the DB doesn't exist yet (first checkout) or hasn't
    been initialized with a ``meta`` table.
    """

    if only is None or not db_path.exists():
        return
    try:
        import sqlite3

        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('ingest.only', ?)",
                (",".join(sorted(only)),),
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.OperationalError:
        # Fresh DB without a meta table — silent no-op.
        pass


def _parallel_ingest_path(
    args: argparse.Namespace,
    only: frozenset[str] | None,
    overrides: dict[str, Path | None],
) -> tuple[int, int, dict[str, int], str]:
    """Run the ``--jobs N`` parallel path.

    Returns ``(total, touched, counts, mode)`` in the same shape as
    the sequential branch so :func:`cmd_ingest` can use the same
    summary print. The shard dir is a tempdir cleaned up
    automatically; chunks land in ``args.output`` either by direct
    concat (full ingest) or by ``merge_jsonl`` overlay (``--only``).
    """

    # Decide which sources participate.
    if only is None:
        source_ids = [s.id for s in INGEST_SOURCES]
    else:
        source_ids = [s.id for s in INGEST_SOURCES if s.id in only]
    if not source_ids:
        return 0, 0, {}, "wrote"

    # Resolve the paths the workers will see. We can't pickle a
    # closure-wrapped IngestSource, but the workers re-resolve by id;
    # they need only the (kwarg_name → path) dict for path lookup.
    paths_by_kwarg = build_iter_corpus_kwargs(**overrides)

    with tempfile.TemporaryDirectory(prefix="minerva-ingest-shards-") as tmp:
        shard_dir = Path(tmp)
        shard_paths, _total, counts = parallel_ingest(
            source_ids,
            paths_by_kwarg,
            shard_dir,
            jobs=args.jobs,
            per_source_timing=args.timing,
        )
        if only is None:
            # Full ingest: stream shards directly into the final JSONL.
            written = concat_shards(shard_paths, args.output)
            return written, written, counts, "wrote"
        # Partial ingest: load shards and overlay onto the existing
        # JSONL by chunk_id. Replays the streaming behavior of
        # ``merge_jsonl`` but pulls chunks from shard files rather than
        # a live parser iterator.
        merged_total, touched, merged_counts = _overlay_shards(
            shard_paths, args.output
        )
        return merged_total, touched, merged_counts, "merged"


def _overlay_shards(
    shard_paths: list[Path],
    output_path: Path,
) -> tuple[int, int, dict[str, int]]:
    """Overlay every shard's rows onto ``output_path`` at corpus
    granularity — mirroring :func:`~minerva.ingest.merge_jsonl`'s
    semantics so a parallel ``--only`` reingest behaves identically
    to the sequential path.

    Fix A of the 2026-05-30 remediation II plan: the previous
    chunk-id-keyed overlay was wrong for the same reason
    chunk-id-keyed overlay was wrong for sequential ingest — content-
    hashed chunk_ids change when text is cleaned/re-OCR'd, so the
    old-id rows for the touched corpora persisted alongside the
    fresh ones (720 stale Essai chunks survived the 2026-05-29
    re-ingest until merge_jsonl was switched to corpus-level
    semantics; the parallel path was never updated).
    """

    if not output_path.exists():
        # No existing rows to preserve — just cat the shards in.
        n = concat_shards(shard_paths, output_path)
        counts: dict[str, int] = {}
        for shard in shard_paths:
            for obj in load_jsonl(shard):
                k = f"{obj.get('corpus')}/{obj.get('lang')}"
                counts[k] = counts.get(k, 0) + 1
        return n, n, counts

    # Shards are on disk and can be re-read cheaply, so we keep the
    # new batch streaming from disk (no extra RAM) and only carry
    # the dicts list across the second pass. For very large parallel
    # re-ingests (multi-corpus --only), this caps RAM at the size
    # of the touched-corpora set + the new batch needed by the
    # shared merge helper.
    new_batch: list[dict] = []
    touched_corpora: set[str | None] = set()
    for shard in shard_paths:
        for obj in load_jsonl(shard):
            c = obj.get("corpus")
            if c:
                touched_corpora.add(c)
            new_batch.append(obj)
    return _merge_dicts_to_jsonl(new_batch, touched_corpora, output_path)


def register(parent_subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    from ..ingest.registry import default_paths_by_param

    pi = parent_subparsers.add_parser("ingest", help="Parse TEI XML into chunks JSONL.")
    defaults = default_paths_by_param()
    for source in INGEST_SOURCES:
        pi.add_argument(
            source.argparse_flag,
            type=Path,
            default=defaults[source.kwarg_name],
            dest=source.kwarg_name,
            help=source.help or f"Path for {source.id} corpus.",
        )
    pi.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_CHUNKS,
        help="Output JSONL path.",
    )
    pi.add_argument(
        "--only",
        default=None,
        help=(
            "Comma-separated list of IngestSource ids (e.g. "
            "'plato,aristotle' or 'origen_grc'). When set, only those "
            "sources are re-parsed and their chunks REPLACE every "
            "existing row for the same corpus (chunk_ids are content-"
            "hashed, so a cleanup pass changes ids — corpus-level "
            "replace drops the stale ones). Every other corpus is "
            "preserved bit-for-bit. Default is to parse every source "
            "and overwrite the output."
        ),
    )
    pi.add_argument(
        "--timing",
        action="store_true",
        help=(
            "Print per-source parse times to stderr and persist the "
            "overall wall time to meta.timing.ingest for later "
            "inspection via `minerva stats`."
        ),
    )
    pi.add_argument(
        "--jobs",
        type=int,
        default=1,
        help=(
            "Parse corpus sources in parallel across N worker "
            "processes (default: 1 — sequential). Each worker imports "
            "the registry fresh and parses one IngestSource; the "
            "orchestrator merges per-source shard JSONLs in registry "
            "order so the final output is deterministic. PDF-heavy "
            "sources (Hegel/Kant) hold the most RAM per worker — "
            "start with --jobs 4 on a 16 GB machine."
        ),
    )
    pi.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=(
            f"DB path used for persisting the timing metadata "
            f"(default: {DEFAULT_DB.name}). Not modified otherwise — "
            f"`minerva index` is what loads chunks into the DB."
        ),
    )
    pi.set_defaults(func=cmd_ingest)
