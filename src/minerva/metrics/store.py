"""Durable request-timing histograms, in their own SQLite file.

NOT a table in `data/index.sqlite`: `minerva index --reset` unlinks that
file outright (`cli/index_cmd.py:84` -> `store/schema.py:101`), and a
`--reset` re-index is precisely the event these numbers exist to bracket.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .histogram import BUCKET_COUNT, bucket_index, quantile

# Bucket width. 5 minutes keeps a day of one busy route near 288 rows, so
# nothing needs a rollup job and history can be kept indefinitely.
BUCKET_SECONDS = 300

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


def open_db(path: Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open the metrics DB, creating tables if missing.

    Mirrors `conversations.open_db`. The HTTP server passes
    `check_same_thread=False` and serializes with its own lock.
    """

    from ..sqlite_util import open_sqlite

    return open_sqlite(path, SCHEMA, check_same_thread=check_same_thread)


def write(conn: sqlite3.Connection, samples: Sequence[Sample]) -> None:
    """Fold *samples* into their buckets, one transaction for the batch."""

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
    with conn:
        conn.executemany(sql, rows)


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


__all__ = ["BUCKET_SECONDS", "SCHEMA", "Sample", "open_db", "series", "summary", "write"]
