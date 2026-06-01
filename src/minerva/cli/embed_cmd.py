"""``minerva embed`` — compute and store sentence embeddings.

Incremental by default: only chunks lacking an ``embeddings`` row for
the requested ``--model`` are encoded. ``--all`` forces a full
re-encode (the prior behaviour, retained for model swaps and recovery
from a corrupted embeddings table).

This was the headline win from the 2026-05-29 ingestion-bottleneck
remediation plan (Phase 1a): a content-stable ``make reingest`` used
to re-encode every chunk from scratch (~20 min for 344K chunks across
7 languages) even though almost none of the text actually changed.
With the ``NOT EXISTS`` skip in ``iter_chunks_without_embeddings``
the same reingest encodes only the new-author additions (seconds).
"""

from __future__ import annotations

import argparse
import sys

from .. import embed, store
from ._shared import (
    Timer,
    add_common_db_arg,
    fmt_elapsed,
    record_timing,
)


def cmd_embed(args: argparse.Namespace) -> int:
    with Timer() as t_model_load:
        try:
            embedder = embed.Embedder(args.model)
        except embed.EmbeddingsUnavailable as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if args.timing:
        print(
            f"timing: embed:model-load  {fmt_elapsed(t_model_load.elapsed)}",
            file=sys.stderr,
        )
    t_overall = Timer()
    t_overall.__enter__()
    conn = store.open_db(args.db)
    # `--lang any` is the CLI sentinel for "embed every language".
    # The store helpers expect None to mean unrestricted, so translate
    # at this boundary.
    lang_filter = None if args.lang == "any" else args.lang

    # Pick the row source. Incremental (default) skips chunks already
    # embedded under the same model; ``--all`` re-encodes everything,
    # which is what you want after switching models or rebuilding a
    # corrupted embeddings table.
    if args.all:
        total = store.chunk_count(conn, lang=lang_filter)
        row_source = store.iter_chunks(conn, lang=lang_filter)
        mode_label = "all chunks"
    else:
        total = store.count_chunks_without_embeddings(
            conn, model=args.model, lang=lang_filter
        )
        row_source = store.iter_chunks_without_embeddings(
            conn, model=args.model, lang=lang_filter
        )
        mode_label = "missing chunks"

    if total == 0:
        t_overall.__exit__(None, None, None)
        if args.all:
            print("No chunks present. Run `minerva index` first.", file=sys.stderr)
            return 2
        print(
            f"All chunks already embedded with {args.model}. "
            f"Pass `--all` to force a full re-encode.",
        )
        if args.timing:
            print(f"timing: embed  {fmt_elapsed(t_overall.elapsed)}", file=sys.stderr)
        record_timing(args.db, "embed", t_overall.elapsed)
        return 0

    print(
        f"Embedding {total} {mode_label} with {args.model} (dim={embedder.dim})..."
    )
    batch = args.batch_size
    written = 0
    pending: list[dict] = []
    # We commit every ~10 batches rather than every batch — the
    # transactional grouping cuts WAL fsync overhead without risking
    # much rework on a mid-run crash (worst case: ~640 chunks re-encoded
    # at batch=64 × 10). Cache invalidation happens once at the end
    # rather than per batch (the prior code dropped the cached
    # embedding matrix on every upsert, which a long retrieval-serving
    # process would have to rebuild from scratch each time).
    commit_every = 10

    def flush(slab: list[dict], *, final: bool) -> int:
        if not slab:
            return 0
        vectors = embedder.encode(
            [r["text"] for r in slab],
            batch_size=args.encode_batch_size,
        )
        items = list(zip([r["chunk_id"] for r in slab], vectors, strict=True))
        n = store.upsert_embeddings(
            conn,
            model=args.model,
            dim=embedder.dim,
            items=items,
            commit=final,
            invalidate_cache=final,
        )
        return n

    for row in row_source:
        pending.append(row)
        if len(pending) >= batch:
            written += flush(pending, final=False)
            pending = []
            # Periodic commit + progress print so a long run shows
            # forward motion and recovers gracefully from interruption.
            if (written // batch) % commit_every == 0:
                conn.commit()
                print(f"  ... {written}/{total}")
    # Drain anything left in the buffer with a final commit + cache
    # invalidation so the next vector-search request sees the new rows.
    written += flush(pending, final=True)
    print(f"  ... {written}/{total}")
    print("Done.")
    t_overall.__exit__(None, None, None)
    if args.timing:
        print(f"timing: embed  {fmt_elapsed(t_overall.elapsed)}", file=sys.stderr)
    record_timing(args.db, "embed", t_overall.elapsed)
    return 0


def register(parent_subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    pe = parent_subparsers.add_parser("embed", help="Compute and store sentence embeddings.")
    add_common_db_arg(pe)
    pe.add_argument(
        "--model",
        default=embed.DEFAULT_MODEL,
        help="Sentence-transformers model name.",
    )
    pe.add_argument(
        "--lang",
        choices=("eng", "grc", "any"),
        default="eng",
        help="Restrict embedding to this language (default: eng).",
    )
    pe.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help=(
            "How many chunk rows to buffer before invoking encode + "
            "upsert. Controls SQLite commit grouping, NOT the inner "
            "sentence-transformers minibatch — use --encode-batch-size "
            "for that."
        ),
    )
    pe.add_argument(
        "--encode-batch-size",
        type=int,
        default=32,
        help=(
            "Sentence-transformers internal batch size for one "
            "`model.encode()` call (default: 32). Raise on a GPU with "
            "headroom; lower if you OOM on CPU."
        ),
    )
    pe.add_argument(
        "--all",
        action="store_true",
        help=(
            "Re-encode every chunk in the language, ignoring existing "
            "embeddings. Use when switching models or recovering from a "
            "corrupted embeddings table — incremental is the default."
        ),
    )
    pe.add_argument(
        "--timing",
        action="store_true",
        help=(
            "Print model-load + overall wall times to stderr. The "
            "overall time is persisted to meta.timing.embed for "
            "later inspection via `minerva stats`."
        ),
    )
    pe.set_defaults(func=cmd_embed)
