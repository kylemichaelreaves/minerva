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

Dedup: every insert goes through :func:`refs.rules.upsert_candidate`,
which blocks re-creation of an existing logical row (same source +
target + reference_type + source_form + quoted_phrase + target chunk)
and never overrides a curator-manual/approved row at the same site.
Re-running is idempotent — the row count stabilizes after the first
pass. A matched row is not left as it was, though: a rule-tier row
nobody has verified follows the rule's current confidence and tier
(#518), and a span that no longer reads its snapshot is moved (#715).
``--refresh-only`` applies that to a whole scope without inserting.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict

from ...refs import embed_verify as refs_embed_verify
from ...refs import llm_verify as refs_llm_verify
from ...refs import rules as refs_rules
from ..terms._io import _open


def _rules_only_flag_misused(args: argparse.Namespace) -> str | None:
    """Name the rules-only flag passed with a verify strategy, if any."""
    if args.strategy == "rules":
        return None
    if getattr(args, "limit", None) is not None:
        # #572: neither verify strategy reads --limit, so it bounded
        # nothing while reading as a cost control.
        return (
            f"--limit applies to --strategy rules only; {args.strategy} never "
            "reads it. Bound an llm-verify run with --max-rows or --max-llm-calls."
        )
    if getattr(args, "refresh_only", False):
        return f"--refresh-only applies to --strategy rules only, not {args.strategy}."
    return None


def cmd_refs_build(args: argparse.Namespace) -> int:
    misuse = _rules_only_flag_misused(args)
    if misuse:
        print(misuse, file=sys.stderr)
        return 2
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
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _RulesPass(conn, args).run()
    finally:
        conn.close()
    return 0


class _RulesPass:
    """The ``--strategy rules`` pass, and its ``--refresh-only`` mode.

    ``--refresh-only`` (#518, #715) is the live backfill for
    :func:`refs.rules.upsert_candidate`'s refresh: it visits every chunk
    in scope regardless of ``refs_scan_state`` — the cache fingerprints
    the rules, not the insert path, so every affected chunk reads as
    current — refreshes the rows its candidates match, inserts nothing
    (so a rescan cannot add #801's duplicates), and leaves the scan-state
    cache as it found it.
    """

    def __init__(self, conn: sqlite3.Connection, args: argparse.Namespace) -> None:
        self.conn = conn
        self.args = args
        self.refresh_only = bool(getattr(args, "refresh_only", False))
        self.outcomes: dict[str, int] = defaultdict(int)
        self.n_chunks_scanned = 0
        self.n_candidates = 0
        self.per_source: dict[str, dict[str, int]] = defaultdict(
            lambda: {"chunks": 0, "candidates": 0, "inserted": 0}
        )
        self.per_pair: dict[tuple[str, str], int] = defaultdict(int)
        # Per-author throttling: skip a chunk when the source author has
        # no rule module. The runner returns an empty candidate list for
        # those, but we want the report to show "scanned 0" rather than
        # "scanned N, candidates 0" which is misleading.
        #
        # This used to name Plato, Aristotle and Descartes as examples —
        # wrong by the time #459 found it: all three have real modules, and
        # the wrong example is what let Aristotle's `refs_scan_state` cache
        # sit falsely "current" (hash and rules fingerprint both matching)
        # for 17,095 chunks, silently withholding 58 detectable references
        # that only `--rescan-all` surfaced. Naming specific authors here
        # invites the same drift; check `_rules_for_author` directly.
        self.rules_seen_for: dict[str, bool] = {}
        # Batch the scan-state upserts — record_scan_state issues one
        # executemany per flush rather than one INSERT per chunk.
        self.scan_state_batch: list[refs_rules.ChunkInfo] = []

    def run(self) -> None:
        chunk_iter = refs_rules.iter_chunks_for_rules(
            self.conn,
            source_author=self.args.source_author,
            limit=self.args.limit,
            rescan_all=self.refresh_only or getattr(self.args, "rescan_all", False),
        )
        for chunk in chunk_iter:
            self._scan(chunk)
        self._flush()
        self._report()

    def _has_rules(self, author: str) -> bool:
        if author not in self.rules_seen_for:
            self.rules_seen_for[author] = bool(refs_rules._rules_for_author(author))
        return self.rules_seen_for[author]

    def _scan(self, chunk: refs_rules.ChunkInfo) -> None:
        # Skip chunks whose source author has no rule module — saves
        # a pattern scan on every such chunk. We still
        # record_scan_state for them so the next run skips them at
        # the iterator level instead of re-issuing this check.
        self.scan_state_batch.append(chunk)
        if not self._has_rules(chunk.author):
            return
        self.n_chunks_scanned += 1
        source = self.per_source[chunk.author]
        source["chunks"] += 1
        candidates = refs_rules.apply_rules_to_chunk(chunk)
        self.n_candidates += len(candidates)
        source["candidates"] += len(candidates)
        for cand in candidates:
            outcome, _ = refs_rules.upsert_candidate(self.conn, cand, insert=not self.refresh_only)
            self.outcomes[outcome] += 1
            if outcome == "inserted":
                source["inserted"] += 1
                self.per_pair[(chunk.author, cand.target_author)] += 1
        # Commit periodically to bound the transaction size. Every
        # 500 chunks is small enough to surface a hard failure quickly
        # but big enough that we're not paying the fsync cost per row.
        if self.n_chunks_scanned % 500 == 0:
            self._flush()
            if self.args.verbose:
                print(
                    f"  ... {self.n_chunks_scanned} chunks scanned, "
                    f"{self.outcomes['inserted']} inserted, "
                    f"{self.outcomes['refreshed']} refreshed",
                    file=sys.stderr,
                )

    def _flush(self) -> None:
        if not self.refresh_only:
            refs_rules.record_scan_state(self.conn, self.scan_state_batch)
        self.scan_state_batch.clear()
        self.conn.commit()

    def _report(self) -> None:
        o = self.outcomes
        mode = "rules refresh-only" if self.refresh_only else "rules build"
        print(
            f"\n{mode} complete: "
            f"scanned {self.n_chunks_scanned} chunks, "
            f"{self.n_candidates} candidates emitted, "
            f"{o['inserted']} new rows, "
            f"{o['refreshed']} refreshed, "
            f"{o['unchanged'] + o['blocked']} skipped (already present)"
            + (f", {o['absent']} unmatched (not inserted)" if self.refresh_only else "")
        )
        if self.per_source:
            print("\nPer source author:")
            for author in sorted(self.per_source):
                s = self.per_source[author]
                print(
                    f"  {author:14s}  chunks={s['chunks']:5d}  "
                    f"candidates={s['candidates']:5d}  inserted={s['inserted']:5d}"
                )
        if self.per_pair:
            print("\nNew references by (source → target):")
            for (src, tgt), n in sorted(self.per_pair.items(), key=lambda kv: -kv[1]):
                print(f"  {src:14s} → {tgt:18s}  {n}")


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

    try:
        backend = llm_mod.make_backend(
            args.llm_backend,
            model=args.llm_model,
            base_url=args.llm_base_url,
            effort=args.llm_effort or refs_llm_verify.LLM_VERIFY_DEFAULT_EFFORT,
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

    # Opened after the backend so a bad backend never touches the DB.
    conn = _open(args)
    conn.execute("PRAGMA foreign_keys = ON")

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
        rejudge_blind=getattr(args, "rejudge_blind", False),
        max_rows=getattr(args, "max_rows", None),
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
