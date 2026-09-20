"""Parallel ingest via ``ProcessPoolExecutor`` (Phase 2 of the
2026-05-29 ingestion-bottleneck remediation plan).

Each registered :class:`~minerva.ingest.registry.IngestSource` becomes
one worker task. A worker process re-imports
:mod:`minerva.ingest.registry`, resolves its source by ``id``, parses
the corpus, and writes its chunks to ``chunks.<source_id>.jsonl`` in
a temp shard directory. The orchestrator collects shards in
``INGEST_SOURCES`` order and either concatenates them into the final
``chunks.jsonl`` (full ingest) or hands them to
:func:`~minerva.ingest.merge_jsonl` for overlay onto an existing
JSONL (``--only`` partial ingest).

Why ``ProcessPoolExecutor`` not threads:

* TEI / EpiDoc parsers are CPU-bound (lxml.etree walks, regex
  substitutions, BeautifulSoup tag-soup cleanup).
* PyMuPDF (used by Hegel / Kant PDFs) is not thread-safe.
* The closures bound onto :class:`~minerva.ingest.registry.IngestSource`
  via the factory helpers (``_tei_dir``, ``_corpus_label``, etc.) are
  not picklable. Workers therefore receive the ``source_id`` string
  and re-resolve from a fresh module import — that side-steps pickling
  entirely.

Memory shape: each worker holds its parser's in-memory state (PyMuPDF
keeps the whole document; lxml parses TEI into a tree). Run with
``--jobs 1`` (the default) on small machines; bump to 4-8 on a desktop
with ≥16 GB. The orchestrator passes ``max_workers`` through verbatim.
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# Worker-only import: each ProcessPoolExecutor worker re-imports this
# module fresh, so the registry stays the worker's source of truth.
# Done at module scope here (not deferred) so attribute lookups in the
# worker function don't pay an import cost per task.
from .registry import INGEST_SOURCES


def _worker_parse_source(
    source_id: str,
    path_str: str | None,
    shard_path_str: str,
) -> dict[str, Any]:
    """Worker entry: parse one source and write its chunks to
    ``shard_path``. Runs in a fresh subprocess started by
    :class:`ProcessPoolExecutor` so the parse is fully independent
    of every other source.

    Returns a status dict the orchestrator uses for per-source timing
    + count reporting and for the deterministic shard-order merge.
    Errors are caught and reported via ``error`` rather than propagated
    so one bad parser doesn't poison the whole ingest — the user can
    re-run with ``--only <bad_source>`` after fixing the bug.
    """

    from ..corpus import pipeline as corpus_pipeline

    sources_by_id = {s.id: s for s in INGEST_SOURCES}
    if source_id not in sources_by_id:
        return {
            "source_id": source_id,
            "skipped": True,
            "reason": "unknown",
            "elapsed": 0.0,
            "count": 0,
        }
    source = sources_by_id[source_id]
    path = Path(path_str) if path_str else None
    if not source.path_present(path):
        return {
            "source_id": source_id,
            "skipped": True,
            "reason": "no-path",
            "elapsed": 0.0,
            "count": 0,
        }

    start = time.perf_counter()
    n = 0
    counts: dict[str, int] = {}
    error_msg: str | None = None
    # Per-file failures inside ``corpus.pipeline.parse_dir`` are caught
    # there (one bad file shouldn't kill the source) and recorded in
    # module state; reset before the parse and ship the list back so
    # the orchestrator can surface them and exit non-zero.
    corpus_pipeline.reset_parse_failures()
    try:
        with Path(shard_path_str).open("w", encoding="utf-8") as fh:
            for chunk in source.parse(path):  # type: ignore[arg-type]
                fh.write(json.dumps(chunk.to_json_dict(), ensure_ascii=False) + "\n")
                n += 1
                k = f"{chunk.corpus}/{chunk.lang}"
                counts[k] = counts.get(k, 0) + 1
    except Exception as exc:
        # Intentionally broad catch: we deliberately swallow the
        # exception in the worker so a single source can fail without
        # killing the whole pool. The orchestrator reports it on
        # stderr; the user re-runs with ``--only <id>`` after fixing.
        error_msg = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - start
    return {
        "source_id": source_id,
        "skipped": False,
        "elapsed": elapsed,
        "count": n,
        "counts": counts,
        "shard": shard_path_str,
        "error": error_msg,
        "parse_failures": corpus_pipeline.parse_failures(),
    }


def ingest_runs_from_results(results: dict, log) -> None:
    """Turn the workers' result dicts into per-source history rows.

    The orchestrator already receives `elapsed`, `count`, `skipped` and
    `error` and already reads them to print `timing: ingest:<id>` — so
    nothing new crosses the process boundary, only the parent writes.

    A result can be BOTH skipped and errored; failure wins. A source that
    failed is not a source that was skipped, and reporting it as skipped
    would hide the failure behind a benign-looking row.
    """

    for source_id, res in results.items():
        error = res.get("error")
        if error:
            status = "failed"
        elif res.get("skipped"):
            status = "skipped"
        else:
            status = "ok"
        log.record(
            source_id,
            status=status,
            elapsed_ms=float(res.get("elapsed", 0.0)) * 1000.0,
            chunks=int(res.get("count", 0)),
            error=str(error) if error else None,
        )


def parallel_ingest(
    source_ids: list[str],
    paths_by_kwarg: dict[str, Path | None],
    shard_dir: Path,
    *,
    jobs: int,
    per_source_timing: bool = False,
    run_log: object | None = None,
) -> tuple[list[Path], int, dict[str, int], dict[str, list[str]], list[str]]:
    """Parse ``source_ids`` in parallel across ``jobs`` worker processes.

    Returns:

    * ``shard_paths``: the per-source JSONL shards, ordered by
      ``INGEST_SOURCES`` position (deterministic regardless of which
      worker finished when — the resulting chunks.jsonl has stable
      ordering, which matters because ``store.insert_chunks`` assigns
      the ``ord`` column from JSONL position).
    * ``total``: total chunks written across all shards.
    * ``counts``: ``{corpus}/{lang} → count`` summary, same shape as
      :func:`~minerva.ingest.write_jsonl`.
    * ``failures``: ``source_id → error message(s)`` for every source
      that failed outright (excluded from the shard list — a full
      ingest would otherwise silently overwrite chunks.jsonl without
      that corpus) or that recorded per-file parse failures inside
      ``corpus.pipeline.parse_dir``. The caller (``cmd_ingest``) must
      surface these and exit non-zero.
    * ``dropped``: source ids whose shard is entirely absent from
      ``shard_paths`` (source-level error, or shard file missing) —
      i.e. the sources whose corpora would VANISH from chunks.jsonl if
      a full ingest concatenated the surviving shards. ``cmd_ingest``
      aborts a full write when this is non-empty. Deliberately-skipped
      sources (missing path, vetted upfront by ``cmd_ingest``) are not
      included.

    Failed sources are reported on stderr and excluded from the shard
    list. ``per_source_timing=True`` mirrors the sequential ingest's
    ``--timing`` output so users see consistent per-source timings
    regardless of parallel/sequential mode.
    """

    sources_by_id = {s.id: s for s in INGEST_SOURCES}
    shard_dir.mkdir(parents=True, exist_ok=True)

    # Sanity-check the requested ids before submitting any work; bad
    # ids should fail loudly before the pool spins up.
    unknown = [sid for sid in source_ids if sid not in sources_by_id]
    if unknown:
        raise ValueError(
            f"parallel_ingest: unknown source ids {unknown!r}; known ids: {sorted(sources_by_id)!r}"
        )

    futures: dict[Any, str] = {}
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for sid in source_ids:
            source = sources_by_id[sid]
            path = paths_by_kwarg.get(source.kwarg_name)
            shard_path = shard_dir / f"chunks.{sid}.jsonl"
            futures[
                pool.submit(
                    _worker_parse_source,
                    sid,
                    str(path) if path else None,
                    str(shard_path),
                )
            ] = sid

        results: dict[str, dict[str, Any]] = {}
        for fut in as_completed(futures):
            sid = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:
                # Intentionally broad: pool-level failure. Should only
                # fire on pickling errors or pool death; the per-source
                # try/except inside ``_worker_parse_source`` catches
                # everything else.
                results[sid] = {
                    "source_id": sid,
                    "skipped": False,
                    "elapsed": 0.0,
                    "count": 0,
                    "error": f"pool-level: {type(exc).__name__}: {exc}",
                }
                continue
            results[sid] = res
            if res.get("error"):
                print(
                    f"ingest:{sid} FAILED — {res['error']}",
                    file=sys.stderr,
                )
                continue
            if per_source_timing and not res.get("skipped"):
                print(
                    f"timing: ingest:{sid}  {res['elapsed']:.2f}s ({res['count']} chunks)",
                    file=sys.stderr,
                )

    # Order shards by INGEST_SOURCES order — deterministic merge so a
    # full ingest with ``--jobs N`` produces the same JSONL as
    # ``--jobs 1``.
    shard_paths: list[Path] = []
    total = 0
    counts: dict[str, int] = {}
    failures: dict[str, list[str]] = {}
    dropped: list[str] = []
    for source in INGEST_SOURCES:
        res = results.get(source.id)
        if res is None:
            continue
        msgs = list(res.get("parse_failures") or [])
        if res.get("error"):
            msgs.append(str(res["error"]))
        if msgs:
            failures[source.id] = msgs
        if res.get("skipped"):
            continue
        if res.get("error"):
            dropped.append(source.id)
            continue
        shard = Path(res.get("shard", ""))
        if not res.get("shard") or not shard.exists():
            dropped.append(source.id)
            continue
        shard_paths.append(shard)
        total += res["count"]
        for k, v in res.get("counts", {}).items():
            counts[k] = counts.get(k, 0) + v

    # Unconditional — NOT gated on `per_source_timing`. That flag controls the
    # stderr print; a history assembled only from runs where someone
    # remembered a flag is not a history.
    if run_log is not None:
        ingest_runs_from_results(results, run_log)

    return shard_paths, total, counts, failures, dropped


def concat_shards(shard_paths: list[Path], output_path: Path) -> int:
    """Stream every shard's lines into ``output_path``, in order, and
    return the total line count. Memory stays flat (no full-file
    materialization) so this scales with corpus size.

    Writes go to a temp file first, atomically renamed onto
    ``output_path`` — a crash or disk-full mid-concat must not leave a
    truncated ``chunks.jsonl`` for the next ``index --reset`` to load.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    n = 0
    try:
        with tmp_path.open("w", encoding="utf-8") as out_fh:
            for shard in shard_paths:
                with shard.open("r", encoding="utf-8") as in_fh:
                    for line in in_fh:
                        out_fh.write(line)
                        n += 1
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    tmp_path.replace(output_path)
    return n
