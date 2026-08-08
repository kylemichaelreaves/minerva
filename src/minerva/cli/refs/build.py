"""`minerva refs build` — auto-detect cross-references via the three-
stage pipeline from the plan.

Strategy dispatch:

* ``--strategy rules`` (Phase 2) — walks the corpus, runs the per-
  author rule modules (``refs.rules.<author>``), inserts candidate
  rows with ``curator_status='auto'``.

* ``--strategy embed-verify`` (Phase 3) — pre-existing rule rows with
  ``quoted_phrase`` are cosine-checked against the target's
  embedding(s); promoted to ``rule+embed`` above threshold, rejected
  below. Plus an embedding-only allusion sweep that emits
  ``source_method='embed_only'`` rows for cross-author similarities
  above ``--allusion-threshold`` (default 0.85) for the pair set in
  :data:`refs.embed_verify.DEFAULT_ALLUSION_PAIRS` (override with
  ``--pair <Source> <Target>``).

* ``--strategy llm-verify`` (Phase 4) — batches pre-existing auto rows
  through an LLM judge (:func:`refs.llm_verify.verify_rows_with_llm`);
  promotes / rejects per verdict under a ``--max-llm-calls`` budget,
  with ``--resume`` picking up from the persisted checkpoint.
  ``--llm-base-url`` overrides go through the same
  ``validate_base_url`` credential-leak guard as ask/chat/serve.

Dedup: every insert goes through :func:`refs.rules.insert_candidate`,
which blocks re-creation of an existing logical row (same source +
target + reference_type + source_form + quoted_phrase) and never
overrides a curator-manual/approved row at the same site. Re-running
is idempotent — the row count stabilizes after the first pass.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict

from ...refs import embed_verify as refs_embed_verify
from ...refs import llm_verify as refs_llm_verify
from ...refs import rules as refs_rules
from ..terms._io import _open


def cmd_refs_build(args: argparse.Namespace) -> int:
    if args.strategy == "embed-verify":
        return _build_embed_verify(args)
    if args.strategy == "llm-verify":
        return _build_llm_verify(args)
    if args.strategy != "rules":
        print(
            f"strategy {args.strategy!r} not recognized",
            file=sys.stderr,
        )
        return 2

    conn = _open(args)
    conn.execute("PRAGMA foreign_keys = ON")

    n_chunks_scanned = 0
    n_candidates = 0
    n_inserted = 0
    n_skipped_dedup = 0
    per_source: dict[str, dict[str, int]] = defaultdict(
        lambda: {"chunks": 0, "candidates": 0, "inserted": 0}
    )
    per_pair: dict[tuple[str, str], int] = defaultdict(int)

    chunk_iter = refs_rules.iter_chunks_for_rules(
        conn,
        source_author=args.source_author,
        limit=args.limit,
        rescan_all=getattr(args, "rescan_all", False),
    )

    # Per-author throttling: skip a chunk when the source author has
    # no rule module (Plato, Aristotle, Descartes today). The runner
    # returns an empty candidate list for those, but we want the
    # report to show "scanned 0" rather than "scanned N, candidates 0"
    # which is misleading.
    rules_seen_for: dict[str, bool] = {}

    # Batch the scan-state upserts — record_scan_state issues one
    # executemany per flush rather than one INSERT per chunk.
    scan_state_batch: list[refs_rules.ChunkInfo] = []

    for chunk in chunk_iter:
        # Skip chunks whose source author has no rule module — saves
        # a pattern scan on every Plato/Aristotle chunk. We still
        # record_scan_state for them so the next run skips them at
        # the iterator level instead of re-issuing this check.
        if chunk.author not in rules_seen_for:
            rules_seen_for[chunk.author] = bool(refs_rules._rules_for_author(chunk.author))
        scan_state_batch.append(chunk)
        if not rules_seen_for[chunk.author]:
            continue

        n_chunks_scanned += 1
        per_source[chunk.author]["chunks"] += 1

        candidates = refs_rules.apply_rules_to_chunk(chunk)
        n_candidates += len(candidates)
        per_source[chunk.author]["candidates"] += len(candidates)

        for cand in candidates:
            new_id = refs_rules.insert_candidate(conn, cand)
            if new_id is None:
                n_skipped_dedup += 1
                continue
            n_inserted += 1
            per_source[chunk.author]["inserted"] += 1
            per_pair[(chunk.author, cand.target_author)] += 1

        # Commit periodically to bound the transaction size. Every
        # 500 chunks is small enough to surface a hard failure quickly
        # but big enough that we're not paying the fsync cost per row.
        if n_chunks_scanned % 500 == 0:
            refs_rules.record_scan_state(conn, scan_state_batch)
            scan_state_batch.clear()
            conn.commit()
            if args.verbose:
                print(
                    f"  ... {n_chunks_scanned} chunks scanned, "
                    f"{n_inserted} inserted, {n_skipped_dedup} skipped",
                    file=sys.stderr,
                )

    refs_rules.record_scan_state(conn, scan_state_batch)
    conn.commit()

    # Report.
    print(
        f"\nrules build complete: "
        f"scanned {n_chunks_scanned} chunks, "
        f"{n_candidates} candidates emitted, "
        f"{n_inserted} new rows, "
        f"{n_skipped_dedup} skipped (already present)"
    )

    if per_source:
        print("\nPer source author:")
        for author in sorted(per_source.keys()):
            s = per_source[author]
            print(
                f"  {author:14s}  chunks={s['chunks']:5d}  "
                f"candidates={s['candidates']:5d}  inserted={s['inserted']:5d}"
            )

    if per_pair:
        print("\nNew references by (source → target):")
        for (src, tgt), n in sorted(per_pair.items(), key=lambda kv: -kv[1]):
            print(f"  {src:14s} → {tgt:18s}  {n}")

    return 0


def _build_embed_verify(args: argparse.Namespace) -> int:
    """Phase 3 dispatch: cosine-verify quoted-phrase rows + the
    cross-author allusion sweep. Both passes share an ``Embedder``
    instance — the SentenceTransformer load is ~2 s and we want to
    pay it once."""

    from ... import embed as embed_mod
    from ... import store as store_mod

    conn = _open(args)
    conn.execute("PRAGMA foreign_keys = ON")

    if not store_mod.has_embeddings(conn):
        print(
            "no embeddings present — run `minerva embed --lang any` first.",
            file=sys.stderr,
        )
        return 2

    try:
        embedder = embed_mod.Embedder()
    except embed_mod.EmbeddingsUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 2

    # PASS A — quoted-phrase verifier. Cheap when there are few
    # quoted rows (Phase 2's rule_weak surface forms don't have
    # quoted_phrase set, so this is typically a small handful of
    # manual / specially-curated rows today). Future quote-extraction
    # rules will populate quoted_phrase more aggressively.
    if not args.skip_verify:
        print("PASS A — verifying quoted-phrase rows ...")
        stats_a = refs_embed_verify.verify_quoted_references(
            conn,
            embedder,
            promote_threshold=args.promote_threshold,
            reject_threshold=args.reject_threshold,
            source_author=args.source_author,
            target_author=args.target_author,
        )
        print(
            f"  examined={stats_a.examined}  "
            f"promoted={stats_a.promoted}  "
            f"rejected={stats_a.rejected}  "
            f"skipped(no_target)={stats_a.skipped_no_target}  "
            f"skipped(no_embedding)={stats_a.skipped_no_embedding}"
        )

    # PASS B — cross-author allusion sweep. Pair list from the user's
    # --pair flag or the default channel set in refs.embed_verify.
    if not args.skip_allusions:
        pairs: list[tuple[str, str]] = []
        if args.pair:
            # Argparse stacks --pair into a list of [src, tgt] pairs.
            for raw in args.pair:
                if " " not in raw and "/" not in raw:
                    print(
                        f"--pair {raw!r}: use 'Source/Target' or 'Source Target' shape",
                        file=sys.stderr,
                    )
                    return 2
                sep = "/" if "/" in raw else " "
                src, tgt = (p.strip() for p in raw.split(sep, 1))
                pairs.append((src, tgt))
        else:
            pairs = list(refs_embed_verify.DEFAULT_ALLUSION_PAIRS)
            # Apply the --source-author / --target-author filters to
            # the default pair set so a `--source-author Aquinas`
            # invocation only runs Aquinas pairs.
            if args.source_author:
                pairs = [(s, t) for (s, t) in pairs if s == args.source_author]
            if args.target_author:
                pairs = [(s, t) for (s, t) in pairs if t == args.target_author]

        if not pairs:
            print(
                "no allusion pairs to sweep after filters — try --pair Author/Target",
                file=sys.stderr,
            )
        else:
            print(f"\nPASS B — allusion sweep across {len(pairs)} channel(s) ...")
            stats_b = refs_embed_verify.find_cross_author_allusions(
                conn,
                pairs=pairs,
                min_cosine=args.allusion_threshold,
                top_k=args.allusion_top_k,
                min_chunk_chars=args.min_chunk_chars,
                verbose=args.verbose,
            )
            print(
                f"  pairs={stats_b.pairs_examined}  "
                f"emitted={stats_b.candidates_emitted}  "
                f"inserted={stats_b.candidates_inserted}  "
                f"skipped(dedup)={stats_b.candidates_skipped_dedup}"
            )

    return 0


def _build_llm_verify(args: argparse.Namespace) -> int:
    """Phase 4 dispatch: LLM-verify auto rows. Defaults to the scope
    confirmed at planning time — skip boilerplate-tied embed_only
    rows + skip rule_strong rows (already 0.92+ from definitional
    conventions). The user can override with the explicit flags."""

    from ... import llm as llm_mod
    from .._shared import validate_base_url

    # Same credential-leak guard as ask/chat/serve: --llm-base-url sends
    # the API key to whatever host is named, so refuse non-trusted hosts
    # unless --unsafe-llm-base-url-host is given. Runs before any DB work.
    validate_base_url(
        argparse.Namespace(
            llm=args.llm_backend,
            llm_base_url=args.llm_base_url,
            unsafe_llm_base_url_host=args.unsafe_llm_base_url_host,
        )
    )

    conn = _open(args)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        backend = llm_mod.make_backend(
            args.llm_backend,
            model=args.llm_model,
            base_url=args.llm_base_url,
        )
    except llm_mod.LLMError as exc:
        print(f"LLM backend init failed: {exc}", file=sys.stderr)
        return 2
    if isinstance(backend, llm_mod.NullBackend):
        print(
            "llm-verify requires a real backend; pass --llm-backend anthropic|openai|ollama",
            file=sys.stderr,
        )
        return 2

    print(
        f"PASS C — LLM verify "
        f"(backend={backend.name}, model={getattr(backend, 'model', '?')}, "
        f"max_llm_calls={args.max_llm_calls}, batch_size={args.batch_size})"
    )

    stats = refs_llm_verify.verify_rows_with_llm(
        conn,
        backend,
        batch_size=args.batch_size,
        max_llm_calls=args.max_llm_calls,
        skip_short_chunks=not args.include_short_chunks,
        skip_strong=not args.include_strong,
        min_confidence=args.min_confidence,
        source_author=args.source_author,
        source_work=getattr(args, "source_work", None),
        target_author=args.target_author,
        verbose=args.verbose,
        sleep_between_calls=args.sleep_between_calls,
        resume=getattr(args, "resume", False),
    )
    print(
        f"\nllm-verify done: "
        f"examined={stats.examined}  "
        f"promoted={stats.promoted}  "
        f"rejected={stats.rejected}  "
        f"unchanged={stats.unchanged}  "
        f"calls={stats.llm_calls}  "
        f"parse_errors={stats.parse_errors}  "
        f"backend_errors={stats.backend_errors}  "
        f"lost_rows={stats.lost_rows}  "
        f"missing_verdicts={stats.missing_verdicts}"
    )
    return 0
