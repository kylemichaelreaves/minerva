"""Durable request-timing histograms, in their own SQLite file.

NOT a table in `data/index.sqlite`: `minerva index --reset` unlinks that
file outright (`cli/index_cmd.py:84` -> `store/schema.py:101`), and a
`--reset` re-index is precisely the event these numbers exist to bracket.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .histogram import BUCKET_COUNT, bucket_index, quantile

# Bucket width. 5 minutes keeps a day of one busy route near 288 rows, so
# nothing needs a rollup job and history can be kept indefinitely.
BUCKET_SECONDS = 300

# How many days of per-request rows to keep. `None` means keep everything, and
# that is the decision, not an oversight: measured at the observed 751
# requests/day, 18 years of complete history is 567 MB and the "last 24h"
# query stays flat at 0.1 ms. What grows with the table is UNINDEXED scans —
# "slowest 20" and the json_each phase rollup — and the three indexes on
# `request_spans` flatten those (177 ms -> 0.0 ms, 170 ms -> 15 ms at 5M rows).
# So indexes are the mitigation and deletion is not needed.
#
# A constant rather than a CLI flag: nobody has wanted a value yet, and adding
# the flag later is additive. The real hazard is a RATE change, not row count —
# a `#/metrics` tab polling every 5s is 23x the observed rate.
RETAIN_DAYS: int | None = None

_BUCKET_COLS = ", ".join(f"b{i}" for i in range(BUCKET_COUNT))
_BUCKET_DECLS = ",\n    ".join(f"b{i} INTEGER NOT NULL DEFAULT 0" for i in range(BUCKET_COUNT))

# `span` is NOT NULL DEFAULT '' deliberately. SQLite does not enforce
# NOT NULL on a non-INTEGER PRIMARY KEY, and ON CONFLICT never matches
# NULL — a nullable span would accumulate duplicate rows whose counts
# never increment, with no error raised. Measured on sqlite 3.50.4.
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS request_timings (
    bucket_start  INTEGER NOT NULL,
    label         TEXT    NOT NULL,
    method        TEXT    NOT NULL,
    kind          TEXT    NOT NULL,
    span          TEXT    NOT NULL DEFAULT '',
    status_class  INTEGER NOT NULL,
    count         INTEGER NOT NULL DEFAULT 0,
    sum_ms        REAL    NOT NULL DEFAULT 0,
    min_ms        REAL    NOT NULL,
    max_ms        REAL    NOT NULL,
    {_BUCKET_DECLS},
    PRIMARY KEY (bucket_start, label, method, kind, span, status_class)
) WITHOUT ROWID;

-- One row per completed request, beside the aggregate rather than instead of
-- it. `request_timings` answers "how is this route behaving"; a bucket mixes
-- requests, so it cannot answer "which request was slow and where did its time
-- go". This table can, and is the only durable place the two halves are paired.
CREATE TABLE IF NOT EXISTS request_spans (
    id            TEXT    PRIMARY KEY,
    at            REAL    NOT NULL,
    label         TEXT    NOT NULL,
    method        TEXT    NOT NULL,
    status        INTEGER NOT NULL,
    total_ms      REAL    NOT NULL,
    accounted_ms  REAL    NOT NULL,
    -- JSON array of objects, each with a name and a ms. Empty array when no
    -- phase fired. A column rather than a child table because a phase gains
    -- a cpu_ms next, and a JSON object grows a key where a table needs an
    -- ALTER. Also: only 0.22% of observed requests carry any phase, so a
    -- child table would be empty for almost every row. json_each keeps it
    -- queryable; see notes/phase-1-plan.md for the measurements.
    phases        TEXT    NOT NULL,
    -- NULLABLE on purpose. NULL means "not measured" (no `time.thread_time`
    -- on this platform, or a row written before Phase 2); 0.0 means "measured,
    -- and the request used no CPU". Collapsing the two would make a missing
    -- clock indistinguishable from an idle request.
    cpu_ms        REAL,
    -- Database time, summed over every statement the request issued, and the
    -- count so a mean is derivable. Nullable for the same reason as cpu_ms:
    -- a route that genuinely touches no database must not be indistinguishable
    -- from a row written before this was measured.
    sqlite_ms     REAL,
    sqlite_queries INTEGER
);
CREATE INDEX IF NOT EXISTS request_spans_at ON request_spans(at);
-- `total_ms DESC` keeps "the slowest N" flat as the table grows: measured
-- 177ms -> 0.0ms at 5M rows.
CREATE INDEX IF NOT EXISTS request_spans_slow ON request_spans(total_ms DESC);
-- Partial, because phases are rare: indexes thousands of rows instead of
-- millions and takes the json_each rollup from 170ms to 15ms at 5M rows.
CREATE INDEX IF NOT EXISTS request_spans_phased ON request_spans(at)
    WHERE phases != '[]';
"""


@dataclasses.dataclass(frozen=True, slots=True)
class Sample:
    """One observed duration, before it is folded into a bucket."""

    at: float
    label: str
    method: str
    kind: str
    span: str
    status_class: int
    ms: float


@dataclasses.dataclass(frozen=True, slots=True)
class RequestRow:
    """One completed request, for `request_spans`."""

    id: str
    at: float
    label: str
    method: str
    status: int
    total_ms: float
    accounted_ms: float
    phases: list[tuple[str, float]]
    # name -> cpu ms. Parallel to `phases` rather than widening its tuples:
    # every existing consumer unpacks exactly two elements.
    phase_cpu: dict[str, float] = dataclasses.field(default_factory=dict)
    cpu_ms: float | None = None
    sqlite_ms: float | None = None
    sqlite_queries: int | None = None


def open_db(
    path: Path,
    *,
    check_same_thread: bool = True,
    retain_days: int | None = RETAIN_DAYS,
) -> sqlite3.Connection:
    """Open the metrics DB, creating tables if missing.

    Mirrors `conversations.open_db`. The HTTP server passes
    `check_same_thread=False` and serializes with its own lock.

    Pruning happens HERE, once per process, and never on the request path:
    a DELETE in `_finish` would put a scan in front of every request to bound
    a table that does not need bounding. `retain_days=None` prunes nothing.
    """

    from ..sqlite_util import open_sqlite

    conn = open_sqlite(path, SCHEMA, check_same_thread=check_same_thread)
    _add_missing_columns(conn)
    if retain_days is not None:
        prune(conn, retain_days=retain_days)
    return conn


# Columns added to `request_spans` after #619 shipped it. `CREATE TABLE IF NOT
# EXISTS` does nothing to a table that already exists, so a database in the
# wild keeps the old shape unless something adds them.
_ADDED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("cpu_ms", "REAL"),
    ("sqlite_ms", "REAL"),
    ("sqlite_queries", "INTEGER"),
)


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """Bring an existing `request_spans` up to the current column set.

    Additive only, and every added column is nullable with no default, so old
    rows read as NOT MEASURED rather than as a measured zero.
    """

    have = {r[1] for r in conn.execute("PRAGMA table_info(request_spans)")}
    missing = [(n, decl) for n, decl in _ADDED_COLUMNS if n not in have]
    if not missing:
        return
    with conn:
        for name, decl in missing:
            conn.execute(f"ALTER TABLE request_spans ADD COLUMN {name} {decl}")


def prune(conn: sqlite3.Connection, *, retain_days: int, now: float | None = None) -> int:
    """Drop `request_spans` rows older than *retain_days*. Returns the count.

    `request_timings` is deliberately untouched: it is bounded by construction
    (one row per 5-minute bucket per route) and is not what grows.
    """

    cutoff = (time.time() if now is None else now) - retain_days * 86400
    with conn:
        cur = conn.execute("DELETE FROM request_spans WHERE at < ?", (cutoff,))
    return cur.rowcount


def _fold_samples(conn: sqlite3.Connection, samples: Sequence[Sample]) -> None:
    """Fold *samples* into their buckets. Caller owns the transaction."""

    if not samples:
        return
    sets = ", ".join(f"b{i} = b{i} + excluded.b{i}" for i in range(BUCKET_COUNT))
    placeholders = ", ".join("?" * (10 + BUCKET_COUNT))
    sql = f"""
        INSERT INTO request_timings
            (bucket_start, label, method, kind, span, status_class,
             count, sum_ms, min_ms, max_ms, {_BUCKET_COLS})
        VALUES ({placeholders})
        ON CONFLICT (bucket_start, label, method, kind, span, status_class)
        DO UPDATE SET
            count  = count + excluded.count,
            sum_ms = sum_ms + excluded.sum_ms,
            min_ms = MIN(min_ms, excluded.min_ms),
            max_ms = MAX(max_ms, excluded.max_ms),
            {sets}
    """
    rows = []
    for s in samples:
        buckets = [0] * BUCKET_COUNT
        buckets[bucket_index(s.ms)] = 1
        rows.append(
            (
                int(s.at) // BUCKET_SECONDS * BUCKET_SECONDS,
                s.label, s.method, s.kind, s.span, s.status_class,
                1, s.ms, s.ms, s.ms, *buckets,
            )
        )
    conn.executemany(sql, rows)


def write(conn: sqlite3.Connection, samples: Sequence[Sample]) -> None:
    """Fold *samples* into their buckets, one transaction for the batch."""

    if not samples:
        return
    with conn:
        _fold_samples(conn, samples)


def _insert_span(conn: sqlite3.Connection, row: RequestRow) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO request_spans"
        " (id, at, label, method, status, total_ms, accounted_ms, phases, cpu_ms,"
        "  sqlite_ms, sqlite_queries)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            row.id, row.at, row.label, row.method, row.status,
            row.total_ms, row.accounted_ms,
            json.dumps(
                [
                    # `cpu_ms` omitted entirely when unmeasured, so a reader can
                    # tell it apart from a measured zero.
                    {"name": n, "ms": ms, **({"cpu_ms": row.phase_cpu[n]} if n in row.phase_cpu else {})}
                    for n, ms in row.phases
                ]
            ),
            row.cpu_ms,
            row.sqlite_ms,
            row.sqlite_queries,
        ),
    )


def write_request(
    conn: sqlite3.Connection, samples: Sequence[Sample], row: RequestRow
) -> None:
    """Both sinks for one request, in ONE transaction.

    Two `with conn:` blocks would mean two commits — and two fsyncs — on the
    request path, for data that describes the same event. They also would not
    agree under failure: the aggregate could commit while the per-request row
    was lost, leaving a bucket whose count no row explains.
    """

    with conn:
        _fold_samples(conn, samples)
        _insert_span(conn, row)


# Retention is uncapped by design, so `request_spans` is expected to reach
# years. A caller-supplied `limit` is therefore clamped rather than trusted:
# without this, one query string could materialise the whole table.
REQUESTS_MAX_LIMIT = 500


def requests(
    conn: sqlite3.Connection,
    *,
    since: float,
    until: float,
    label: str | None = None,
    method: str | None = None,
    errors_only: bool = False,
    phased_only: bool = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Per-request rows, newest first.

    Filtering happens in SQL, not in the caller: every filter here has an
    index behind it, and `phased_only` deliberately uses `phases != '[]'` —
    the exact predicate `request_spans_phased` is built on, so the filter the
    UI offers is one the index can serve.
    """

    where = ["at >= ?", "at < ?"]
    params: list[Any] = [since, until]
    if label:
        where.append("label = ?")
        params.append(label)
    if method:
        where.append("method = ?")
        params.append(method)
    if errors_only:
        where.append("status >= 400")
    if phased_only:
        where.append("phases != '[]'")
    params.append(max(1, min(limit, REQUESTS_MAX_LIMIT)))

    sql = (
        "SELECT id, at, label, method, status, total_ms, accounted_ms, phases,"
        " cpu_ms, sqlite_ms, sqlite_queries"
        f" FROM request_spans WHERE {' AND '.join(where)}"
        " ORDER BY at DESC LIMIT ?"
    )
    out: list[dict[str, Any]] = []
    for row in conn.execute(sql, params):
        (rid, at, lbl, meth, status, total_ms, accounted_ms, phases,
         cpu_ms, sqlite_ms, sqlite_queries) = row
        out.append(
            {
                "id": rid,
                "at": at,
                "label": lbl,
                "method": meth,
                "status": status,
                "total_ms": total_ms,
                "accounted_ms": accounted_ms,
                # Stored as a complement so the two measured numbers are the
                # two kept; the derived one is computed at read time.
                "unaccounted_ms": total_ms - accounted_ms,
                "phases": json.loads(phases),
                # None, not 0: "not measured" is a different answer from
                # "measured, and idle".
                "cpu_ms": cpu_ms,
                "sqlite_ms": sqlite_ms,
                "sqlite_queries": sqlite_queries,
            }
        )
    return out


def _quantiles(buckets: list[int]) -> dict[str, float]:
    return {
        "p50_ms": quantile(buckets, 0.50),
        "p95_ms": quantile(buckets, 0.95),
        "p99_ms": quantile(buckets, 0.99),
    }


def _window_bounds(since: float, until: float) -> tuple[int, int]:
    """Bucket-aligned `[lo, hi)` for a window covering `[since, until]`.

    `bucket_start` is floored to `BUCKET_SECONDS`, so a request at `now`
    is filed under `floor(now)` — at or *before* `now`. Comparing that
    against a raw `until` excluded the row for the first second of every
    bucket, because the two are then equal and the bound is strict. A
    window ending "now" lost everything in the bucket still in progress,
    `window=all` included (#598).

    So both ends are floored and the upper one is extended to the end of
    the bucket `until` lands in. The cost is that two adjacent windows —
    a window and its previous-window baseline (#601) — share the one
    bucket on their boundary: 1 of 288 for `24h`. Charging that bucket to
    both is the lesser error against blacking it out of both.
    """

    lo = int(since) // BUCKET_SECONDS * BUCKET_SECONDS
    hi = int(until) // BUCKET_SECONDS * BUCKET_SECONDS + BUCKET_SECONDS
    return lo, hi


def summary(
    conn: sqlite3.Connection,
    *,
    since: float,
    until: float,
    label: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregate one window into a row per (label, method, kind, span).

    Without *label*, returns whole-request rows only (`span = ''`). With
    *label*, returns that route's sub-spans instead — the drill-down.
    """

    span_clause = "span = ''" if label is None else "label = ? AND span != ''"
    params: list[Any] = list(_window_bounds(since, until))
    if label is not None:
        params.append(label)
    sums = ", ".join(f"SUM(b{i})" for i in range(BUCKET_COUNT))
    sql = f"""
        SELECT label, method, kind, span,
               SUM(count), SUM(sum_ms), MIN(min_ms), MAX(max_ms),
               SUM(CASE WHEN status_class = 5 THEN count ELSE 0 END),
               {sums}
          FROM request_timings
         WHERE bucket_start >= ? AND bucket_start < ? AND {span_clause}
      GROUP BY label, method, kind, span
    """
    out: list[dict[str, Any]] = []
    for row in conn.execute(sql, params):
        label_, method, kind, span, count, sum_ms, min_ms, max_ms, errors = row[:9]
        buckets = list(row[9:])
        out.append(
            {
                "label": label_,
                "method": method,
                "kind": kind,
                "span": span,
                "count": count,
                "mean_ms": sum_ms / count if count else 0.0,
                "min_ms": min_ms,
                "max_ms": max_ms,
                "error_rate": errors / count if count else 0.0,
                **_quantiles(buckets),
            }
        )
    out.sort(key=lambda r: r["p95_ms"], reverse=True)
    return out


def series(
    conn: sqlite3.Connection,
    *,
    label: str,
    kind: str,
    span: str,
    since: float,
    until: float,
    bucket_seconds: int,
) -> list[dict[str, Any]]:
    """One point per *bucket_seconds* window for a single route.

    Granularity is applied here rather than stored. Summing the histogram
    columns is what lets the quantiles survive the regrouping.
    """

    sums = ", ".join(f"SUM(b{i})" for i in range(BUCKET_COUNT))
    # `bucket_start / ?` is INTEGER division: both operands are integers and
    # SQLite floors. That is deliberate — it is what groups rows into the
    # coarser window. Do not "fix" it to a float division or a CAST.
    sql = f"""
        SELECT (bucket_start / ?) * ? AS t,
               SUM(count), SUM(sum_ms), MAX(max_ms), {sums}
          FROM request_timings
         WHERE bucket_start >= ? AND bucket_start < ?
               AND label = ? AND kind = ? AND span = ?
      GROUP BY t
      ORDER BY t
    """
    lo, hi = _window_bounds(since, until)
    params = (bucket_seconds, bucket_seconds, lo, hi, label, kind, span)
    out: list[dict[str, Any]] = []
    for row in conn.execute(sql, params):
        t, count, sum_ms, max_ms = row[:4]
        buckets = list(row[4:])
        out.append(
            {
                "t": t,
                "count": count,
                "mean_ms": sum_ms / count if count else 0.0,
                "max_ms": max_ms,
                **_quantiles(buckets),
            }
        )
    return out


__all__ = [
    "BUCKET_SECONDS",
    "REQUESTS_MAX_LIMIT",
    "SCHEMA",
    "RequestRow",
    "Sample",
    "open_db",
    "requests",
    "series",
    "summary",
    "write",
    "write_request",
]
