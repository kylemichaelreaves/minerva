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

from minerva.concordance.index_queries import _fold_initial


def build(conn: sqlite3.Connection, *, verbose: bool = False) -> dict[str, int]:
    """Rebuild ``lemma_counts`` from ``chunk_lemmas`` + ``chunks_full``.

    Returns a summary dict with row counts per scope_kind for the
    caller's logging. The rebuild is transactional — the DELETE and
    every INSERT ride one transaction committed at the very end, so a
    crash mid-build rolls back to the prior contents instead of
    leaving a half-built table served as truth.

    Performance: a full corpus rebuild touches every chunk_lemmas
    row once. Measured 2026-09-10 — 26,122,391 chunk_lemmas rows in,
    4,487,900 lemma_counts rows out, 205.2s end to end. (This docstring
    read "~8M lemma rows … ~5s … ~10s" until then; the corpus grew 3.2x
    and the rebuild ~13x, so do not size work off the old figures.)

    The end result still swaps a 16-36s read-time GROUP BY for a
    millisecond seek. But "paid once per ``minerva index`` rather than
    once per user request" understates it now: every ``terms lemmatize``
    pays it too, in full, however few chunks it touched, because there
    is no scope parameter. #548 tracks scoping it.
    """

    t0 = time.time()
    if verbose:
        print("aggregate: rebuilding lemma_counts …")

    # Wipe and rebuild — incremental updates would require tracking
    # which chunks changed since the last build, which the ingest
    # pipeline doesn't expose. The full rebuild is fast enough that
    # avoiding that complexity is worth it. The DELETE opens the
    # transaction (legacy isolation mode); the single commit/rollback
    # below makes the swap all-or-nothing — a ~4.5M-row transaction is
    # comfortably within SQLite's range.
    try:
        conn.execute("DELETE FROM lemma_counts")

        # Single streaming pass over chunk_lemmas × chunks_full, filling
        # the corpus / author / work buckets simultaneously. Previously
        # ran three separate scans of the same 14M-row join (one per
        # scope_kind) — single pass is ~3× faster and uses comparable
        # memory since the three bucket dicts are independent. See
        # lemmatize-perf-plan memory.
        corpus_n, author_n, work_n = _build_all(conn, verbose=verbose)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise

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


def _build_all(conn: sqlite3.Connection, *, verbose: bool) -> tuple[int, int, int]:
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

    # COALESCE(cl.lang, cf.lang), not cf.lang alone: `chunk_lemmas.lang`
    # (migration 0032) is NULL for an ordinary same-script token but
    # explicit for a cross-script run — an embedded Latin phrase inside
    # a `grc` chunk, tagged 'lat' by the lemmatizer, must count as
    # Latin vocabulary in every scope, not as Greek (#430).
    t_scan = time.time()
    for lang, author, work, lemma, pos in conn.execute(
        """
        SELECT COALESCE(cl.lang, cf.lang), cf.author, cf.work, cl.lemma, cl.pos
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
        corpus_rows.append((lang, "corpus", None, lemma, pos, total, distinct_works, per_work_json))
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
    # the single work + count, kept for shape parity with the other scopes.
    #
    # The read path does NOT ignore it, which this comment used to claim: the
    # non-aggregate branch passes it through verbatim and `_merge_per_work_blobs`
    # sums it on the aggregate branch (the default). The concordance therefore
    # rendered a one-bar sparkline from it on every row at work scope — a full
    # block carrying nothing — until #370 stopped drawing it below two works.
    # If you are tempted to make this shape richer, that renderer is the caller
    # to check first.
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
    """Insert in fixed-size batches to keep the prepared-statement bind
    buffer bounded. Deliberately does NOT commit — all three scope
    inserts plus the initial DELETE ride the single transaction owned
    by ``build``, so an abort mid-rebuild rolls back to the previous
    complete table instead of leaving a partial aggregate behind."""

    if not rows:
        return
    # `lemma_initial` is derived here rather than at the three `append` sites
    # (#425). One place means the corpus, author and work scopes cannot disagree
    # about a row's rail bucket, and it is derived with the very function the
    # read path folds its request parameter with — imported, not reimplemented,
    # because a second copy of the fold is exactly how the stored value and the
    # query drift apart. See migration 0031 for why the column exists.
    for i in range(0, len(rows), _INSERT_BATCH):
        batch = [(*r, _fold_initial(r[3])) for r in rows[i : i + _INSERT_BATCH]]
        conn.executemany(
            "INSERT INTO lemma_counts "
            "(lang, scope_kind, scope_value, lemma, pos, "
            " count, distinct_works, per_work_json, lemma_initial) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            batch,
        )
