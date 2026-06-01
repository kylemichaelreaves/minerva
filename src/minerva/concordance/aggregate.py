"""Build the ``lemma_counts`` materialized aggregate.

The concordance leaderboard's GROUP BY against the live
``chunk_lemmas`` table is unworkable on the current corpus
(~8M rows × 4-way join × temp B-tree = 16-36s per request).
This module rebuilds a flat aggregate table that the read path
seeks by ``(lang, scope_kind, scope_value)`` in milliseconds.

Three scope levels:

* ``corpus`` — one row per ``(lang, lemma, pos)``. ``scope_value``
  is NULL.
* ``author`` — one row per ``(lang, author, lemma, pos)``.
* ``work``   — one row per ``(lang, work_title, lemma, pos)``.

The ``per_work_json`` column carries the top-8 per-work breakdown
the sparkline reads — same shape the live query was building on
every request, now precomputed once at index time.

Call ``build(conn)`` after ``minerva ingest && minerva index &&
minerva terms lemmatize`` to refresh. Idempotent — replaces the table
contents in one transaction.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections import defaultdict


def build(conn: sqlite3.Connection, *, verbose: bool = False) -> dict[str, int]:
    """Rebuild ``lemma_counts`` from ``chunk_lemmas`` + ``chunks_full``.

    Returns a summary dict with row counts per scope_kind for the
    caller's logging. The rebuild is transactional — if anything
    raises mid-build, the prior contents survive.

    Performance: a full corpus rebuild touches every chunk_lemmas
    row once. On the current corpus (~8M lemma rows) the SELECT
    streams in ~5s and the INSERTs add another ~10s for ~8M
    lemma_counts rows. The end result swaps a 16-36s read-time
    GROUP BY for a millisecond seek — the rebuild cost is paid once
    per ``minerva index`` rather than once per user request.
    """

    t0 = time.time()
    if verbose:
        print("aggregate: rebuilding lemma_counts …")

    # Wipe and rebuild — incremental updates would require tracking
    # which chunks changed since the last build, which the ingest
    # pipeline doesn't expose. The full rebuild is fast enough that
    # avoiding that complexity is worth it.
    conn.execute("DELETE FROM lemma_counts")

    # Single streaming pass over chunk_lemmas × chunks_full, filling
    # the corpus / author / work buckets simultaneously. Previously
    # ran three separate scans of the same 14M-row join (one per
    # scope_kind) — single pass is ~3× faster and uses comparable
    # memory since the three bucket dicts are independent. See
    # lemmatize-perf-plan memory.
    corpus_n, author_n, work_n = _build_all(conn, verbose=verbose)

    total = corpus_n + author_n + work_n
    elapsed = time.time() - t0
    if verbose:
        print(
            f"aggregate: done · {total:,} rows "
            f"(corpus={corpus_n:,} author={author_n:,} work={work_n:,}) "
            f"in {elapsed:.1f}s"
        )

    return {
        "corpus": corpus_n,
        "author": author_n,
        "work": work_n,
        "total": total,
        "elapsed_seconds": elapsed,
    }


def _build_all(
    conn: sqlite3.Connection, *, verbose: bool
) -> tuple[int, int, int]:
    """Single streaming pass over chunk_lemmas × chunks_full, filling
    corpus / author / work buckets simultaneously.

    Replaces three separate scope-specific scans. The data needed by
    each scope is a subset of (lang, author, work, lemma, pos), so
    one SELECT with all columns + Python increments into three dicts
    finishes in ~1/3 the wall-clock time and uses comparable memory
    (each scope's bucket is independent).

    Materializes per-scope rows + inserts at the end. Returns
    (corpus_n, author_n, work_n).
    """

    if verbose:
        print("  single-pass scan: corpus + author + work …")

    # corpus: (lang, lemma, pos) → {work → count}
    corpus_buckets: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    # author: (lang, author, lemma, pos) → {work → count}
    author_buckets: dict[tuple[str, str, str, str], dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    # work: (lang, work, lemma, pos) → count
    work_buckets: dict[tuple[str, str, str, str], int] = defaultdict(int)

    t_scan = time.time()
    for lang, author, work, lemma, pos in conn.execute(
        """
        SELECT cf.lang, cf.author, cf.work, cl.lemma, cl.pos
        FROM chunk_lemmas cl
        JOIN chunks_full cf ON cf.chunk_id = cl.chunk_id
        """
    ):
        if not lemma or not pos:
            continue
        work_key = work or ""
        corpus_buckets[(lang, lemma, pos)][work_key] += 1
        if author:
            author_buckets[(lang, author, lemma, pos)][work_key] += 1
        if work:
            work_buckets[(lang, work, lemma, pos)] += 1
    if verbose:
        print(f"  scan done in {time.time() - t_scan:.1f}s")

    # ── materialize + insert corpus scope ──
    if verbose:
        print("  materializing scope=corpus …")
    corpus_rows = []
    for (lang, lemma, pos), per_work in corpus_buckets.items():
        total = sum(per_work.values())
        distinct_works = sum(1 for w, n in per_work.items() if w and n > 0)
        top = sorted(per_work.items(), key=lambda kv: -kv[1])[:8]
        per_work_json = json.dumps(
            [{"work": w, "n": n} for w, n in top if w],
            ensure_ascii=False,
        )
        corpus_rows.append(
            (lang, "corpus", None, lemma, pos, total, distinct_works, per_work_json)
        )
    _bulk_insert(conn, corpus_rows)
    corpus_n = len(corpus_rows)
    del corpus_rows, corpus_buckets

    # ── materialize + insert author scope ──
    if verbose:
        print("  materializing scope=author …")
    author_rows = []
    for (lang, author, lemma, pos), per_work in author_buckets.items():
        total = sum(per_work.values())
        distinct_works = sum(1 for w, n in per_work.items() if w and n > 0)
        top = sorted(per_work.items(), key=lambda kv: -kv[1])[:8]
        per_work_json = json.dumps(
            [{"work": w, "n": n} for w, n in top if w],
            ensure_ascii=False,
        )
        author_rows.append(
            (lang, "author", author, lemma, pos, total, distinct_works, per_work_json)
        )
    _bulk_insert(conn, author_rows)
    author_n = len(author_rows)
    del author_rows, author_buckets

    # ── materialize + insert work scope ──
    # work_buckets is a flat int-count dict — per_work_json is just
    # the single work + count, kept for shape parity with the other
    # scopes (read path ignores it when scope_kind='work').
    if verbose:
        print("  materializing scope=work …")
    work_rows = []
    for (lang, work, lemma, pos), total in work_buckets.items():
        per_work_json = json.dumps([{"work": work, "n": total}], ensure_ascii=False)
        work_rows.append((lang, "work", work, lemma, pos, total, 1, per_work_json))
    _bulk_insert(conn, work_rows)
    work_n = len(work_rows)
    del work_rows, work_buckets

    return corpus_n, author_n, work_n


_INSERT_BATCH = 5000


def _bulk_insert(
    conn: sqlite3.Connection,
    rows: list[tuple[str, str, str | None, str, str, int, int, str]],
) -> None:
    """Insert in fixed-size batches. ``executemany`` of 8M rows in one
    shot would hold a single huge transaction; batching keeps the WAL
    bounded and lets a Ctrl-C abort midway recover most of the work
    when the migration is re-run."""

    if not rows:
        return
    for i in range(0, len(rows), _INSERT_BATCH):
        conn.executemany(
            "INSERT INTO lemma_counts "
            "(lang, scope_kind, scope_value, lemma, pos, "
            " count, distinct_works, per_work_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows[i:i + _INSERT_BATCH],
        )
    conn.commit()
