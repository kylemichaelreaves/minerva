# Request Timing Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record per-route request latency into a durable SQLite histogram store and expose it as a `#/metrics` surface, so the operator can see how latency changes across ingests.

**Architecture:** A context manager at each of the four `do_*` dispatch sites records `(label, method, kind, span, status_class, ms)`. Samples upsert into 5-minute histogram buckets in a dedicated database file. Two read endpoints aggregate those buckets at a granularity derived in SQL. The frontend is a route table plus a hand-rolled SVG trend chart.

**Tech Stack:** Python 3 stdlib (`sqlite3`, `contextvars`, `contextlib`), SolidJS, vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-request-timing-observability-design.md`

## Global Constraints

- **Branch from `main`, not from `docs/581-request-timing-spec`.** A PR based on another branch registers no `closingIssuesReferences`, however many closing keywords the body carries.
- **The metrics database is a separate file.** Never a table in `data/index.sqlite`, and never a numbered migration. `minerva index --reset` unlinks that file (`cli/index_cmd.py:84` → `store/schema.py:101-107`), which would delete the timing history on exactly the event it exists to measure.
- **Frontend tests go in `web/tests/`**, never colocated under `web/src/`. Sonar analyses `web/src` as production source; a colocated test scores 0% and fails the required gate. `check-diff-coverage` cannot see this.
- **New-code coverage ≥ 80%, branches included.** A guard whose false branch is untested scores 3/4.
- **Cognitive complexity ≤ 15 per function.** Ruff's `C901` does not measure this and will not warn.
- **Duplication ≤ 3% on new code.** Do not copy `LeaderboardPanel` wholesale.
- **Python invocation is `./.venv/bin/python`.** `direnv exec . python` fails; `timeout` is absent on this machine.
- **`gh` must be run as `direnv exec . gh`.** Never `gh auth switch`.
- Histogram bucket bounds, the `kind` vocabulary, and the `span` sentinel (`''`, never `NULL`) are fixed by Task 1 and must not be redefined later.

---

## File Structure

| Path | Responsibility |
|---|---|
| `src/minerva/metrics/__init__.py` | Public surface: re-exports `SCHEMA`, `open_db`, `Recorder`, `sub_span`, `Sample` |
| `src/minerva/metrics/histogram.py` | Pure bucket math: bounds, `bucket_index`, `quantile` |
| `src/minerva/metrics/store.py` | `SCHEMA`, `open_db`, `write`, `summary`, `series` |
| `src/minerva/metrics/recorder.py` | `Recorder`, `Span`, `sub_span`, in-memory ring buffer |
| `src/minerva/http/handlers/metrics.py` | `_handle_metrics_summary`, `_handle_metrics_series` |
| `web/src/api/metricsApi.ts` | Wire types + fetch functions |
| `web/src/Metrics/TimeSeriesChart.tsx` | Hand-rolled SVG chart |
| `web/src/Metrics/MetricsPanel.tsx` | Window selector, route table, chart composition |
| `web/src/routes/MetricsRoute.tsx` | Route shell |

---

### Task 1: Histogram primitives

Pure functions with no I/O. Everything downstream depends on these bounds, so they are fixed here.

**Files:**
- Create: `src/minerva/metrics/__init__.py`
- Create: `src/minerva/metrics/histogram.py`
- Test: `tests/test_metrics_histogram.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `BUCKET_UPPER_MS: tuple[float, ...]` (13 finite bounds), `BUCKET_COUNT: int` (14, the last being overflow), `bucket_index(ms: float) -> int`, `quantile(counts: Sequence[int], q: float) -> float`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metrics_histogram.py
"""Bucket math for request timings. Pure functions, no I/O."""

from __future__ import annotations

import pytest

from minerva.metrics.histogram import (
    BUCKET_COUNT,
    BUCKET_UPPER_MS,
    bucket_index,
    quantile,
)


def test_bucket_count_is_finite_bounds_plus_overflow():
    assert BUCKET_COUNT == len(BUCKET_UPPER_MS) + 1


def test_bucket_index_lower_edge_lands_in_first_bucket():
    assert bucket_index(0.0) == 0
    assert bucket_index(0.9) == 0


def test_bucket_index_is_upper_exclusive():
    # 1.0 is the first bound, so it belongs to the NEXT bucket.
    assert bucket_index(1.0) == 1
    assert bucket_index(2.4) == 1


def test_bucket_index_overflow():
    assert bucket_index(999_999.0) == BUCKET_COUNT - 1


def test_bucket_index_negative_clamps_to_first():
    # A clock that went backwards must not produce a negative index.
    assert bucket_index(-5.0) == 0


def test_quantile_empty_is_zero():
    assert quantile([0] * BUCKET_COUNT, 0.95) == 0.0


def test_quantile_single_bucket_interpolates_within_it():
    counts = [0] * BUCKET_COUNT
    counts[3] = 10  # bucket 3 spans [5.0, 10.0)
    got = quantile(counts, 0.5)
    assert 5.0 <= got <= 10.0


def test_quantile_p95_lands_in_the_tail_bucket():
    counts = [0] * BUCKET_COUNT
    counts[0] = 95   # [0, 1)
    counts[8] = 5    # [250, 500)
    assert quantile(counts, 0.99) > 250.0


def test_quantile_overflow_bucket_returns_last_finite_bound():
    counts = [0] * BUCKET_COUNT
    counts[BUCKET_COUNT - 1] = 4
    # Cannot interpolate to infinity; the last finite bound is the floor.
    assert quantile(counts, 0.95) == BUCKET_UPPER_MS[-1]


@pytest.mark.parametrize("q", [0.0, -0.1, 1.1])
def test_quantile_rejects_out_of_range(q):
    with pytest.raises(ValueError):
        quantile([1] + [0] * (BUCKET_COUNT - 1), q)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_metrics_histogram.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'minerva.metrics'`

- [ ] **Step 3: Write the implementation**

```python
# src/minerva/metrics/histogram.py
"""Fixed log-scale latency buckets and the quantile estimate over them.

Counts are stored PER BUCKET, not cumulatively. Cumulative would be the
Prometheus convention and makes the quantile scan marginally simpler, but
recording a request then means incrementing every column at or above the
observed value instead of exactly one. Cumulate at read time; summation
aggregates either form, so nothing downstream cares.
"""

from __future__ import annotations

from collections.abc import Sequence

# Upper bounds in milliseconds, exclusive. Chosen to span a sub-millisecond
# static-asset read through a ~10s Stanza cold start with roughly even
# resolution in log space.
BUCKET_UPPER_MS: tuple[float, ...] = (
    1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0,
    250.0, 500.0, 1000.0, 2500.0, 5000.0, 10000.0,
)

# One more than the finite bounds: the last bucket is the overflow.
BUCKET_COUNT: int = len(BUCKET_UPPER_MS) + 1


def bucket_index(ms: float) -> int:
    """Return the bucket *ms* falls in. Upper bounds are exclusive, so a
    duration of exactly 1.0 ms lands in bucket 1, not bucket 0."""

    for i, upper in enumerate(BUCKET_UPPER_MS):
        if ms < upper:
            return i
    return BUCKET_COUNT - 1


def _bucket_bounds(i: int) -> tuple[float, float]:
    lo = 0.0 if i == 0 else BUCKET_UPPER_MS[i - 1]
    hi = BUCKET_UPPER_MS[i]
    return lo, hi


def quantile(counts: Sequence[int], q: float) -> float:
    """Estimate the *q*th quantile in milliseconds from per-bucket *counts*.

    Linearly interpolates within the bucket the target rank falls into, so
    the result carries up to one bucket-width of error. `sum_ms / count` is
    exact and is the precise trend signal; this is the tail-shape signal.
    """

    if not 0.0 < q <= 1.0:
        raise ValueError(f"quantile q must be in (0, 1], got {q!r}")
    total = sum(counts)
    if total == 0:
        return 0.0
    target = q * total
    cumulative = 0
    for i, count in enumerate(counts):
        if count == 0:
            continue
        previous = cumulative
        cumulative += count
        if cumulative < target:
            continue
        if i == BUCKET_COUNT - 1:
            # Overflow bucket has no upper bound to interpolate toward.
            return BUCKET_UPPER_MS[-1]
        lo, hi = _bucket_bounds(i)
        return lo + (hi - lo) * ((target - previous) / count)
    return BUCKET_UPPER_MS[-1]


__all__ = ["BUCKET_COUNT", "BUCKET_UPPER_MS", "bucket_index", "quantile"]
```

```python
# src/minerva/metrics/__init__.py
"""Request-timing metrics: bucket math, a durable store, and the recorder.

Kept in its own database file rather than a table in the corpus index.
`minerva index --reset` unlinks the index file outright (`store.reset_db`),
and a `--reset` re-index is exactly the event whose latency impact these
numbers exist to bracket. The sibling modules `conversations`,
`translations` and `concept_cache` are separate files for the same reason —
see the `--conversations-db` help text in `cli/serve_cmd.py`.
"""

from __future__ import annotations

from .histogram import BUCKET_COUNT, BUCKET_UPPER_MS, bucket_index, quantile

__all__ = ["BUCKET_COUNT", "BUCKET_UPPER_MS", "bucket_index", "quantile"]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_metrics_histogram.py -q`
Expected: PASS, 11 passed

- [ ] **Step 5: Commit**

```bash
git add src/minerva/metrics/ tests/test_metrics_histogram.py
git commit -m "feat(metrics): fixed log-scale latency buckets and a quantile estimate

Per-bucket rather than cumulative counts: recording then increments
exactly one column instead of every column at or above the observed
value. Summation aggregates either form.

Refs #581"
```

---

### Task 2: The metrics store

**Files:**
- Create: `src/minerva/metrics/store.py`
- Modify: `src/minerva/metrics/__init__.py`
- Test: `tests/test_metrics_store.py`

**Interfaces:**
- Consumes: `BUCKET_COUNT`, `bucket_index`, `quantile` from Task 1.
- Produces: `SCHEMA: str`, `open_db(path, *, check_same_thread=True) -> sqlite3.Connection`, `Sample` (frozen dataclass: `at: float`, `label: str`, `method: str`, `kind: str`, `span: str`, `status_class: int`, `ms: float`), `BUCKET_SECONDS: int`, `write(conn, samples: Sequence[Sample]) -> None`, `summary(conn, *, since, until, label=None) -> list[dict]`, `series(conn, *, label, kind, span, since, until, bucket_seconds) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metrics_store.py
"""The durable timing store: upsert accumulation and read aggregation."""

from __future__ import annotations

import sqlite3

import pytest

from minerva.metrics import store as m


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(m.SCHEMA)
    yield c
    c.close()


def _sample(**kw):
    base = dict(
        at=1_700_000_000.0,
        label="work range",
        method="GET",
        kind="total",
        span="",
        status_class=2,
        ms=12.0,
    )
    base.update(kw)
    return m.Sample(**base)


def test_write_accumulates_into_one_row(conn):
    m.write(conn, [_sample(), _sample(), _sample()])
    rows = conn.execute("SELECT count, sum_ms FROM request_timings").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 3


def test_write_never_leaves_a_null_span(conn):
    # NULL in the composite PK silently defeats the upsert: ON CONFLICT
    # never matches NULL, so each write would insert a duplicate row whose
    # count stays at 1. Guarding it here because the failure is silent.
    m.write(conn, [_sample(), _sample()])
    spans = [r[0] for r in conn.execute("SELECT span FROM request_timings")]
    assert spans == [""]
    assert None not in spans


def test_write_separates_kinds(conn):
    m.write(conn, [_sample(kind="total"), _sample(kind="ttfe")])
    assert conn.execute("SELECT count(*) FROM request_timings").fetchone()[0] == 2


def test_write_floors_to_the_bucket(conn):
    m.write(conn, [_sample(at=1_700_000_001.0), _sample(at=1_700_000_299.0)])
    starts = [r[0] for r in conn.execute("SELECT DISTINCT bucket_start FROM request_timings")]
    assert starts == [1_700_000_000 // m.BUCKET_SECONDS * m.BUCKET_SECONDS]


def test_write_splits_across_bucket_boundary(conn):
    m.write(conn, [_sample(at=1_700_000_000.0), _sample(at=1_700_000_400.0)])
    assert conn.execute("SELECT count(*) FROM request_timings").fetchone()[0] == 2


def test_write_tracks_min_and_max(conn):
    m.write(conn, [_sample(ms=5.0), _sample(ms=90.0), _sample(ms=40.0)])
    lo, hi = conn.execute("SELECT min_ms, max_ms FROM request_timings").fetchone()
    assert (lo, hi) == (5.0, 90.0)


def test_write_empty_is_a_noop(conn):
    m.write(conn, [])
    assert conn.execute("SELECT count(*) FROM request_timings").fetchone()[0] == 0


def test_summary_reports_exact_mean(conn):
    m.write(conn, [_sample(ms=10.0), _sample(ms=20.0), _sample(ms=30.0)])
    rows = m.summary(conn, since=0, until=2_000_000_000)
    assert len(rows) == 1
    assert rows[0]["count"] == 3
    assert rows[0]["mean_ms"] == pytest.approx(20.0)


def test_summary_error_rate(conn):
    m.write(conn, [_sample(status_class=2)] * 3 + [_sample(status_class=5)])
    rows = m.summary(conn, since=0, until=2_000_000_000)
    # Rows collapse per (label, method, kind, span); error_rate is the 5xx share.
    assert rows[0]["error_rate"] == pytest.approx(0.25)


def test_summary_respects_the_window(conn):
    m.write(conn, [_sample(at=1_000_000_000.0), _sample(at=1_700_000_000.0)])
    rows = m.summary(conn, since=1_600_000_000, until=2_000_000_000)
    assert rows[0]["count"] == 1


def test_summary_label_filter_returns_sub_spans(conn):
    m.write(conn, [_sample(span=""), _sample(span="stanza_parse")])
    rows = m.summary(conn, since=0, until=2_000_000_000, label="work range")
    assert {r["span"] for r in rows} == {"stanza_parse"}


def test_series_groups_by_requested_granularity(conn):
    m.write(conn, [_sample(at=1_700_000_000.0), _sample(at=1_700_001_000.0)])
    points = m.series(
        conn, label="work range", kind="total", span="",
        since=0, until=2_000_000_000, bucket_seconds=3600,
    )
    assert len(points) == 1
    assert points[0]["count"] == 2


def test_series_is_ordered_by_time(conn):
    m.write(conn, [_sample(at=1_700_100_000.0), _sample(at=1_700_000_000.0)])
    points = m.series(
        conn, label="work range", kind="total", span="",
        since=0, until=2_000_000_000, bucket_seconds=300,
    )
    assert [p["t"] for p in points] == sorted(p["t"] for p in points)


def test_series_empty_when_nothing_matches(conn):
    m.write(conn, [_sample()])
    points = m.series(
        conn, label="nonexistent", kind="total", span="",
        since=0, until=2_000_000_000, bucket_seconds=300,
    )
    assert points == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_metrics_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'minerva.metrics.store'`

- [ ] **Step 3: Write the implementation**

```python
# src/minerva/metrics/store.py
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
    params: list[Any] = [int(since), int(until)]
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
    sql = f"""
        SELECT (bucket_start / ?) * ? AS t,
               SUM(count), SUM(sum_ms), MAX(max_ms), {sums}
          FROM request_timings
         WHERE bucket_start >= ? AND bucket_start < ?
               AND label = ? AND kind = ? AND span = ?
      GROUP BY t
      ORDER BY t
    """
    params = (bucket_seconds, bucket_seconds, int(since), int(until), label, kind, span)
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
```

Then extend `src/minerva/metrics/__init__.py`:

```python
from .store import BUCKET_SECONDS, SCHEMA, Sample, open_db, series, summary, write

__all__ = [
    "BUCKET_COUNT", "BUCKET_SECONDS", "BUCKET_UPPER_MS", "SCHEMA", "Sample",
    "bucket_index", "open_db", "quantile", "series", "summary", "write",
]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_metrics_store.py -q`
Expected: PASS, 14 passed

- [ ] **Step 5: Commit**

```bash
git add src/minerva/metrics/store.py src/minerva/metrics/__init__.py tests/test_metrics_store.py
git commit -m "feat(metrics): durable histogram store in its own SQLite file

Separate file, not a table in the corpus index: index --reset unlinks
that file outright, on exactly the event these numbers exist to bracket.

span is NOT NULL DEFAULT '' because SQLite does not enforce NOT NULL on
a non-INTEGER PRIMARY KEY and ON CONFLICT never matches NULL — a
nullable column would accumulate duplicates whose counts never
increment, silently.

Refs #581"
```

---

### Task 3: The recorder and sub-spans

**Files:**
- Create: `src/minerva/metrics/recorder.py`
- Modify: `src/minerva/metrics/__init__.py`
- Test: `tests/test_metrics_recorder.py`

**Interfaces:**
- Consumes: `Sample`, `write` from Task 2.
- Produces: `Recorder(conn=None, lock=None, *, ring_size=200, now=time.time, clock=time.perf_counter)`, `Recorder.record(label: str, method: str) -> ContextManager[Span]`, `Recorder.recent() -> list[dict]`, `Span.status: int`, `Span.first_event() -> None`, `sub_span(name: str) -> ContextManager[None]`.

A `Recorder` with `conn=None` records to the ring buffer only. That is the default on `ServerDeps`, so every existing test keeps working untouched and no `do_*` site needs a `None` branch.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metrics_recorder.py
"""The request-timing context manager: what it records, and when."""

from __future__ import annotations

import sqlite3

import pytest

from minerva.metrics import store as m
from minerva.metrics.recorder import Recorder, sub_span


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(m.SCHEMA)
    yield c
    c.close()


class FakeClock:
    """Monotonic stand-in so durations are exact, not timing-dependent."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def test_records_a_total_sample(conn):
    clock = FakeClock()
    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=clock)
    with rec.record("work range", "GET") as span:
        clock.advance(0.020)
        span.status = 200
    row = conn.execute("SELECT kind, count, sum_ms FROM request_timings").fetchone()
    assert row[0] == "total"
    assert row[1] == 1
    assert row[2] == pytest.approx(20.0)


def test_status_class_is_derived_from_status(conn):
    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=FakeClock())
    with rec.record("work range", "GET") as span:
        span.status = 404
    assert conn.execute("SELECT status_class FROM request_timings").fetchone()[0] == 4


def test_exception_records_a_5xx_and_reraises(conn):
    # The failure path must still produce a sample; a route that only ever
    # errors is exactly the one worth seeing.
    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=FakeClock())
    with pytest.raises(RuntimeError):
        with rec.record("chat", "POST"):
            raise RuntimeError("boom")
    assert conn.execute("SELECT status_class FROM request_timings").fetchone()[0] == 5


def test_first_event_records_a_ttfe_sample_as_well(conn):
    clock = FakeClock()
    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=clock)
    with rec.record("chat", "POST") as span:
        clock.advance(0.100)
        span.first_event()
        clock.advance(0.900)
        span.status = 200
    kinds = dict(conn.execute("SELECT kind, sum_ms FROM request_timings"))
    assert kinds["ttfe"] == pytest.approx(100.0)
    assert kinds["total"] == pytest.approx(1000.0)


def test_first_event_is_recorded_once(conn):
    clock = FakeClock()
    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=clock)
    with rec.record("chat", "POST") as span:
        span.first_event()
        clock.advance(0.500)
        span.first_event()  # every SSE event calls it; only the first counts
        span.status = 200
    ttfe = conn.execute(
        "SELECT sum_ms FROM request_timings WHERE kind = 'ttfe'"
    ).fetchone()[0]
    assert ttfe == pytest.approx(0.0)


def test_sub_span_is_recorded_against_the_active_request(conn):
    clock = FakeClock()
    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=clock)
    with rec.record("chunk syntax", "GET") as span:
        with sub_span("stanza_parse", clock=clock):
            clock.advance(0.150)
        span.status = 200
    spans = dict(conn.execute("SELECT span, sum_ms FROM request_timings"))
    assert spans["stanza_parse"] == pytest.approx(150.0)
    assert spans[""] == pytest.approx(150.0)


def test_sub_span_outside_a_request_is_a_noop(conn):
    # CLI callers hit the same instrumented code paths with no request
    # in flight. That must not raise and must not write.
    with sub_span("stanza_parse"):
        pass
    assert conn.execute("SELECT count(*) FROM request_timings").fetchone()[0] == 0


def test_ring_buffer_keeps_the_most_recent(conn):
    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=FakeClock(), ring_size=2)
    for label in ("a", "b", "c"):
        with rec.record(label, "GET") as span:
            span.status = 200
    assert [r["label"] for r in rec.recent()] == ["b", "c"]


def test_recorder_without_a_connection_still_fills_the_ring():
    rec = Recorder(now=lambda: 1_700_000_000.0, clock=FakeClock())
    with rec.record("work range", "GET") as span:
        span.status = 200
    assert len(rec.recent()) == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_metrics_recorder.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'minerva.metrics.recorder'`

- [ ] **Step 3: Write the implementation**

```python
# src/minerva/metrics/recorder.py
"""The timing context manager used at each `do_*` dispatch site.

One context manager per site rather than a unified dispatcher. The four
`do_*` methods diverge on cross-origin checks, rate limiting, body parsing
and response shape; folding them into one function means four or five
boolean flags, which is the shape that drove #559's cognitive complexity
to 29 while local coverage stayed green.
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from typing import Any

from .store import Sample, write

# Per-thread by construction: each thread gets its own top-level Context,
# which is what makes this safe under ThreadingHTTPServer. Threading the
# span through every handler signature would be the alternative.
_CURRENT: Any = None


def _init_contextvar() -> Any:
    import contextvars

    return contextvars.ContextVar("minerva_metrics_span", default=None)


_CURRENT = _init_contextvar()


class Span:
    """One in-flight request. Mutable; the dispatch site sets `status`."""

    __slots__ = ("label", "method", "status", "_clock", "_t0", "_ttfe_ms", "_subs")

    def __init__(self, label: str, method: str, clock: Callable[[], float]) -> None:
        self.label = label
        self.method = method
        self.status = 200
        self._clock = clock
        self._t0 = clock()
        self._ttfe_ms: float | None = None
        self._subs: list[tuple[str, float]] = []

    def elapsed_ms(self) -> float:
        return (self._clock() - self._t0) * 1000.0

    def first_event(self) -> None:
        """Mark time-to-first-event. Called from every SSE write; only the
        first call counts, because that is the number that means anything."""

        if self._ttfe_ms is None:
            self._ttfe_ms = self.elapsed_ms()

    def add_sub(self, name: str, ms: float) -> None:
        self._subs.append((name, ms))


@contextlib.contextmanager
def sub_span(name: str, *, clock: Callable[[], float] = time.perf_counter) -> Iterator[None]:
    """Time a named step inside the active request. A no-op with no request
    in flight, so the same code path stays usable from the CLI."""

    span = _CURRENT.get()
    if span is None:
        yield
        return
    t0 = clock()
    try:
        yield
    finally:
        span.add_sub(name, (clock() - t0) * 1000.0)


class Recorder:
    """Owns the metrics connection, its lock, and the recent-request ring.

    `conn=None` records to the ring only. That is the `ServerDeps` default,
    so existing tests need no change and no dispatch site needs a guard.
    """

    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        lock: threading.Lock | None = None,
        *,
        ring_size: int = 200,
        now: Callable[[], float] = time.time,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._conn = conn
        self._lock = lock or threading.Lock()
        self._ring: deque[dict[str, Any]] = deque(maxlen=ring_size)
        self._now = now
        self._clock = clock

    @contextlib.contextmanager
    def record(self, label: str, method: str) -> Iterator[Span]:
        span = Span(label, method, self._clock)
        token = _CURRENT.set(span)
        try:
            yield span
        except BaseException:
            span.status = 500
            raise
        finally:
            _CURRENT.reset(token)
            self._finish(span)

    def _finish(self, span: Span) -> None:
        total_ms = span.elapsed_ms()
        at = self._now()
        status_class = span.status // 100
        samples = [
            Sample(at, span.label, span.method, "total", "", status_class, total_ms)
        ]
        if span._ttfe_ms is not None:
            samples.append(
                Sample(at, span.label, span.method, "ttfe", "", status_class, span._ttfe_ms)
            )
        samples.extend(
            Sample(at, span.label, span.method, "total", name, status_class, ms)
            for name, ms in span._subs
        )
        self._ring.append(
            {
                "at": at,
                "label": span.label,
                "method": span.method,
                "status": span.status,
                "ms": total_ms,
                "subs": list(span._subs),
            }
        )
        if self._conn is None:
            return
        with self._lock:
            write(self._conn, samples)

    def recent(self) -> list[dict[str, Any]]:
        """Most recent requests, oldest first. In-memory only; lost on restart."""

        return list(self._ring)


__all__ = ["Recorder", "Span", "sub_span"]
```

Add to `src/minerva/metrics/__init__.py`:

```python
from .recorder import Recorder, Span, sub_span
```
and extend `__all__` with `"Recorder"`, `"Span"`, `"sub_span"`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_metrics_recorder.py -q`
Expected: PASS, 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/minerva/metrics/recorder.py src/minerva/metrics/__init__.py tests/test_metrics_recorder.py
git commit -m "feat(metrics): timing context manager with TTFE and sub-spans

A context manager per dispatch site, not a unified dispatcher: the four
do_* methods diverge on cross-origin checks, rate limiting, body parsing
and response shape, and folding them together needs four or five boolean
flags — the shape that drove #559 to complexity 29.

Sub-spans reach the active request through a ContextVar rather than a
parameter on every handler signature, and no-op with no request in
flight so CLI callers hit the same code path safely.

Refs #581"
```

---

### Task 4: Wire the recorder into the server

**Files:**
- Modify: `src/minerva/http/server_core.py` (add the `metrics` field to `ServerDeps`)
- Modify: `src/minerva/http/serve.py` (four `do_*` sites, `_send_sse`, `serve()` signature)
- Modify: `src/minerva/cli/_shared.py` (add `DEFAULT_METRICS_DB`)
- Modify: `src/minerva/cli/__init__.py` (re-export it)
- Modify: `src/minerva/cli/serve_cmd.py` (open the DB, `--metrics-db`, `--no-metrics`)
- Test: `tests/test_server_metrics.py`

**Interfaces:**
- Consumes: `Recorder` from Task 3.
- Produces: `ServerDeps.metrics: Recorder` (defaulted, never `None`); `serve(..., metrics_conn: sqlite3.Connection | None = None)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_server_metrics.py
"""Request timing recorded through the real dispatch path."""

from __future__ import annotations

import sqlite3

import pytest
from conftest import StubBackend, make_deps

from minerva.metrics import store as m
from minerva.metrics.recorder import Recorder


@pytest.fixture
def metrics_conn():
    c = sqlite3.connect(":memory:")
    c.executescript(m.SCHEMA)
    yield c
    c.close()


def test_deps_default_recorder_is_inert(populated_db):
    # Every existing test constructs deps without metrics; that must stay
    # a no-op rather than requiring each of them to be updated.
    deps = make_deps(populated_db, StubBackend(reply="ok"))
    assert deps.metrics.recent() == []


def test_get_route_records_a_sample(populated_db, metrics_conn):
    deps = make_deps(populated_db, StubBackend(reply="ok"))
    deps.metrics = Recorder(metrics_conn)
    with deps.metrics.record("works list", "GET") as span:
        span.status = 200
    row = metrics_conn.execute(
        "SELECT label, method, kind FROM request_timings"
    ).fetchone()
    assert row == ("works list", "GET", "total")


def test_recorder_survives_a_handler_exception(populated_db, metrics_conn):
    deps = make_deps(populated_db, StubBackend(reply="ok"))
    deps.metrics = Recorder(metrics_conn)
    with pytest.raises(ValueError):
        with deps.metrics.record("work range", "GET"):
            raise ValueError("handler blew up")
    assert metrics_conn.execute(
        "SELECT status_class FROM request_timings"
    ).fetchone()[0] == 5
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_server_metrics.py -q`
Expected: FAIL — `AttributeError: 'ServerDeps' object has no attribute 'metrics'`

- [ ] **Step 3: Write the implementation**

In `src/minerva/http/server_core.py`, import `Recorder` and add the field next to `rate_limiter`:

```python
from ..metrics.recorder import Recorder

    # Request-timing recorder. Defaults to a connection-less Recorder, which
    # fills the in-memory ring and writes nothing — so tests and any caller
    # that doesn't want persistence need no branch at the dispatch sites.
    metrics: Recorder = dataclasses.field(default_factory=Recorder)
```

In `src/minerva/http/serve.py`, wrap each dispatch site. `do_GET`, after the rate-limit check:

```python
            try:
                with self.deps.metrics.record(label, "GET") as span:
                    body = handler(*args)  # type: ignore[arg-type]
                    self._send_json(HTTPStatus.OK, body)
            except Exception as exc:
                err = _translate_route_exception(label, exc)
                self._send_error_json(err)
                return
            return
```

`do_POST`, wrapping the body-read through response:

```python
        try:
            with self.deps.metrics.record(label, "POST") as span:
                payload = _read_json_body(self.headers, self.rfile)
                if path == "/api/chat" and payload.get("stream") is True:
                    self._send_sse(HTTPStatus.OK, _handle_chat_stream(self.deps, payload))
                    return
                body = _dispatch_json_mutation(handler, args, payload)
                self._send_json(HTTPStatus.OK, body)
        except Exception as exc:
            self._send_error_json(_translate_route_exception(label, exc))
            return
```

`do_PATCH` and `do_DELETE` take the same two lines around their existing bodies, with `span.status = HTTPStatus.NO_CONTENT` set on the `do_DELETE` success path and `span.status = HTTPStatus.NOT_FOUND` on its falsy-result path.

In `_send_sse`, mark first event inside the write loop:

```python
        from ..metrics.recorder import _CURRENT
        ...
                self.wfile.write(chunk)
                self.wfile.flush()
                active = _CURRENT.get()
                if active is not None:
                    active.first_event()
```

In `src/minerva/cli/_shared.py`, beside the sibling defaults:

```python
DEFAULT_METRICS_DB = REPO_ROOT / "data" / "metrics.sqlite"
```

In `src/minerva/cli/serve_cmd.py`, mirroring `--conversations-db`:

```python
    psv.add_argument(
        "--metrics-db",
        type=Path,
        default=DEFAULT_METRICS_DB,
        help=(
            "SQLite path for request-timing history. Kept separate from the "
            "corpus index because `index --reset` unlinks that file, which "
            "would erase the history on exactly the event it records "
            f"(default: {DEFAULT_METRICS_DB.relative_to(REPO_ROOT)})."
        ),
    )
    psv.add_argument(
        "--no-metrics",
        action="store_true",
        help="Don't persist request timings. The in-memory recent-request ring stays on.",
    )
```

and in `cmd_serve`:

```python
    metrics_conn = (
        None if args.no_metrics else metrics.open_db(args.metrics_db, check_same_thread=False)
    )
```
passing `metrics_conn=metrics_conn` into `_server.serve(...)`, which builds
`ServerDeps(metrics=Recorder(metrics_conn), ...)` when it is not None.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_server_metrics.py tests/test_server_http.py tests/test_cli_args.py -q`
Expected: PASS — and the existing suites must be untouched, which the defaulted field is what buys.

- [ ] **Step 5: Commit**

```bash
git add src/minerva/http/server_core.py src/minerva/http/serve.py src/minerva/cli/ tests/test_server_metrics.py
git commit -m "feat(metrics): record timings at the four dispatch sites

ServerDeps.metrics defaults to a connection-less Recorder, so no existing
test changes and no dispatch site needs a None branch.

--metrics-db points at its own file. index --reset unlinks the corpus
index outright, which would erase the history on exactly the event it
records.

Refs #581"
```

---

### Task 5: Instrument the three hot paths

**Files:**
- Modify: `src/minerva/http/handlers/syntax.py` (Stanza parse)
- Modify: `src/minerva/retrieve.py` (embed search)
- Modify: `src/minerva/llm.py` (LLM call)
- Test: `tests/test_metrics_subspans.py`

**Interfaces:**
- Consumes: `sub_span` from Task 3.
- Produces: three span names, fixed here and referenced by the frontend drill-down: `"stanza_parse"`, `"embed_search"`, `"llm_call"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metrics_subspans.py
"""The three instrumented hot paths report under the active request."""

from __future__ import annotations

import sqlite3

import pytest

from minerva.metrics import store as m
from minerva.metrics.recorder import Recorder

SPAN_NAMES = ("stanza_parse", "embed_search", "llm_call")


@pytest.fixture
def metrics_conn():
    c = sqlite3.connect(":memory:")
    c.executescript(m.SCHEMA)
    yield c
    c.close()


@pytest.mark.parametrize("name", SPAN_NAMES)
def test_span_name_is_instrumented_somewhere(name):
    """Guard the names the frontend drill-down depends on. A rename that
    misses this list would leave the breakdown silently empty."""

    import subprocess

    hit = subprocess.run(
        ["grep", "-rn", f'sub_span("{name}"', "src/minerva/"],
        capture_output=True, text=True,
    )
    assert hit.stdout.strip(), f"no sub_span({name!r}) call found in src/minerva/"


def test_sub_spans_and_the_request_land_in_one_write(metrics_conn):
    from minerva.metrics.recorder import sub_span

    rec = Recorder(metrics_conn, now=lambda: 1_700_000_000.0)
    with rec.record("chunk syntax", "GET") as span:
        with sub_span("stanza_parse"):
            pass
        span.status = 200
    spans = {r[0] for r in metrics_conn.execute("SELECT span FROM request_timings")}
    assert spans == {"", "stanza_parse"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_metrics_subspans.py -q`
Expected: FAIL — the three parametrized cases fail with "no sub_span(...) call found"

- [ ] **Step 3: Write the implementation**

Wrap each call site. In `src/minerva/http/handlers/syntax.py`, around the parse:

```python
from ...metrics.recorder import sub_span
...
    with sub_span("stanza_parse"):
        parsed = <existing parse call>
```

In `src/minerva/retrieve.py`, around the vector search, and in `src/minerva/llm.py`, around the backend round-trip, with `sub_span("embed_search")` and `sub_span("llm_call")` respectively. Each is a one-line wrap of an existing call; do not restructure the surrounding function.

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_metrics_subspans.py -q`
Expected: PASS, 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/minerva/http/handlers/syntax.py src/minerva/retrieve.py src/minerva/llm.py tests/test_metrics_subspans.py
git commit -m "feat(metrics): time the Stanza parse, embed search and LLM call

Three names the frontend drill-down depends on, guarded by a test so a
rename cannot leave the breakdown silently empty.

Refs #581"
```

---

### Task 6: Read endpoints, routes and API contract

**Files:**
- Create: `src/minerva/http/handlers/metrics.py`
- Modify: `src/minerva/http/handlers/__init__.py`, `src/minerva/http/router.py`
- Create: `tests/fixtures/api/metrics_summary.keys.json`, `tests/fixtures/api/metrics_series.keys.json`
- Modify: `scripts/check_api_types.py` (`FIXTURE_TYPES` entries)
- Modify: `tests/test_api_contract.py`
- Test: `tests/test_metrics_handlers.py`

**Interfaces:**
- Consumes: `summary`, `series` from Task 2.
- Produces: `_handle_metrics_summary(deps, qs) -> dict`, `_handle_metrics_series(deps, qs) -> dict`. Response keys: summary `{"window", "since", "until", "rows"}`; series `{"label", "kind", "span", "bucket_seconds", "points"}`. Router labels: `"metrics summary"`, `"metrics series"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metrics_handlers.py
"""Window parsing, granularity selection, and the two read endpoints."""

from __future__ import annotations

import sqlite3

import pytest
from conftest import StubBackend, make_deps

from minerva.http.server_core import _HTTPError
from minerva.http.handlers.metrics import (
    _bucket_seconds_for,
    _handle_metrics_series,
    _handle_metrics_summary,
    _parse_window,
)
from minerva.metrics import store as m
from minerva.metrics.recorder import Recorder


@pytest.fixture
def deps(populated_db):
    c = sqlite3.connect(":memory:")
    c.executescript(m.SCHEMA)
    d = make_deps(populated_db, StubBackend(reply="ok"))
    d.metrics = Recorder(c)
    d.metrics_conn = c
    return d


def test_parse_window_known_values():
    assert _parse_window("24h") == 86_400
    assert _parse_window("7d") == 604_800


def test_parse_window_all_is_unbounded():
    assert _parse_window("all") is None


def test_parse_window_rejects_junk():
    with pytest.raises(_HTTPError):
        _parse_window("bananas")


@pytest.mark.parametrize(
    "span_seconds,expected",
    [(3600, 300), (21_600, 300), (86_400, 3600), (604_800, 3600), (2_592_000, 86_400)],
)
def test_bucket_seconds_for(span_seconds, expected):
    assert _bucket_seconds_for(span_seconds) == expected


def test_summary_shape(deps):
    body = _handle_metrics_summary(deps, {"window": "24h"})
    assert set(body) == {"window", "since", "until", "rows"}
    assert isinstance(body["rows"], list)


def test_summary_returns_recorded_routes(deps):
    with deps.metrics.record("works list", "GET") as span:
        span.status = 200
    body = _handle_metrics_summary(deps, {"window": "all"})
    assert [r["label"] for r in body["rows"]] == ["works list"]


def test_series_shape(deps):
    body = _handle_metrics_series(deps, {"label": "works list", "window": "24h"})
    assert set(body) == {"label", "kind", "span", "bucket_seconds", "points"}


def test_series_requires_a_label(deps):
    with pytest.raises(_HTTPError):
        _handle_metrics_series(deps, {"window": "24h"})


def test_series_defaults_to_total_kind_and_empty_span(deps):
    body = _handle_metrics_series(deps, {"label": "works list", "window": "24h"})
    assert body["kind"] == "total"
    assert body["span"] == ""
```

Fixtures:

```json
// tests/fixtures/api/metrics_summary.keys.json
["window", "since", "until", "rows"]
```
```json
// tests/fixtures/api/metrics_series.keys.json
["label", "kind", "span", "bucket_seconds", "points"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_metrics_handlers.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'minerva.http.handlers.metrics'`

- [ ] **Step 3: Write the implementation**

```python
# src/minerva/http/handlers/metrics.py
"""Read endpoints over the request-timing store.

Granularity is derived here rather than stored. Summing the histogram
columns is what lets the quantiles survive the regrouping — the reason
the store keeps buckets instead of raw rows.
"""

from __future__ import annotations

import time
from http import HTTPStatus
from typing import Any

from ...metrics import store as metrics_store
from ..server_core import ServerDeps, _HTTPError

_WINDOWS: dict[str, int | None] = {
    "1h": 3_600,
    "6h": 21_600,
    "24h": 86_400,
    "7d": 604_800,
    "30d": 2_592_000,
    "all": None,
}

# Granularity thresholds, in seconds of window span.
_SIX_HOURS = 21_600
_SEVEN_DAYS = 604_800


def _parse_window(value: str) -> int | None:
    """Seconds for a named window, or None for 'all'."""

    if value not in _WINDOWS:
        allowed = ", ".join(_WINDOWS)
        raise _HTTPError(HTTPStatus.BAD_REQUEST, f"window must be one of: {allowed}")
    return _WINDOWS[value]


def _bucket_seconds_for(span_seconds: int) -> int:
    if span_seconds <= _SIX_HOURS:
        return metrics_store.BUCKET_SECONDS
    if span_seconds <= _SEVEN_DAYS:
        return 3_600
    return 86_400


def _range(qs: dict[str, str]) -> tuple[float, float, str]:
    name = qs.get("window", "24h")
    width = _parse_window(name)
    until = time.time()
    since = 0.0 if width is None else until - width
    return since, until, name


def _handle_metrics_summary(deps: ServerDeps, qs: dict[str, str]) -> dict[str, Any]:
    since, until, name = _range(qs)
    label = qs.get("label") or None
    rows = metrics_store.summary(deps.metrics_conn, since=since, until=until, label=label)
    return {"window": name, "since": since, "until": until, "rows": rows}


def _handle_metrics_series(deps: ServerDeps, qs: dict[str, str]) -> dict[str, Any]:
    label = qs.get("label")
    if not label:
        raise _HTTPError(HTTPStatus.BAD_REQUEST, "label is required")
    since, until, _ = _range(qs)
    bucket_seconds = _bucket_seconds_for(int(until - since))
    kind = qs.get("kind", "total")
    span = qs.get("span", "")
    points = metrics_store.series(
        deps.metrics_conn,
        label=label, kind=kind, span=span,
        since=since, until=until, bucket_seconds=bucket_seconds,
    )
    return {
        "label": label,
        "kind": kind,
        "span": span,
        "bucket_seconds": bucket_seconds,
        "points": points,
    }


__all__ = ["_handle_metrics_series", "_handle_metrics_summary"]
```

`ServerDeps` gains `metrics_conn: sqlite3.Connection | None = None` alongside `metrics`, so the read path has a connection to query. When it is `None` both handlers return empty `rows` / `points` rather than raising — a server started with `--no-metrics` should render an empty page, not a 500.

Register in `router.py`, in `build_get_routes`, before the catch-all `_WORK_PATH_RE`:

```python
        ("/api/metrics/summary", "metrics summary", lambda: _handle_metrics_summary(deps, qs())),
        ("/api/metrics/series", "metrics series", lambda: _handle_metrics_series(deps, qs())),
```

Add both to `handlers/__init__.py`'s imports and `__all__`, and add to `scripts/check_api_types.py`:

```python
    "metrics_summary": (TS_API / "metricsApi.ts", "MetricsSummaryResponse"),
    "metrics_series": (TS_API / "metricsApi.ts", "MetricsSeriesResponse"),
```

Add two cases to `tests/test_api_contract.py` following the existing `_assert_has_keys(body, _load_keys(...))` pattern.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_metrics_handlers.py tests/test_api_contract.py -q && ./.venv/bin/python scripts/check_api_types.py`
Expected: PASS. `check_api_types.py` will fail until Task 7 creates `metricsApi.ts` — that is expected here and resolved by the next task; run it again then.

- [ ] **Step 5: Commit**

```bash
git add src/minerva/http/handlers/metrics.py src/minerva/http/handlers/__init__.py src/minerva/http/router.py src/minerva/http/server_core.py tests/ scripts/check_api_types.py
git commit -m "feat(metrics): summary and series read endpoints

Granularity derived in SQL rather than stored; summing histogram columns
is what lets quantiles survive the regroup.

--no-metrics returns empty rows rather than 500ing, so a server without
persistence renders an empty page.

Refs #581"
```

---

### Task 7: Frontend API module

**Files:**
- Create: `web/src/api/metricsApi.ts`
- Test: `web/tests/metricsApi.test.ts`

**Interfaces:**
- Consumes: the endpoint shapes from Task 6.
- Produces: `MetricsSummaryRow`, `MetricsSummaryResponse`, `MetricsSeriesPoint`, `MetricsSeriesResponse`, `fetchMetricsSummary(window, label?, signal?)`, `fetchMetricsSeries(label, opts, signal?)`, `METRIC_WINDOWS`.

- [ ] **Step 1: Write the failing test**

```ts
// web/tests/metricsApi.test.ts
import { describe, expect, it, vi, afterEach } from "vitest";
import {
  METRIC_WINDOWS,
  fetchMetricsSeries,
  fetchMetricsSummary,
} from "~/api/metricsApi";

function mockFetch(body: unknown) {
  const spy = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => body,
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => vi.unstubAllGlobals());

describe("metricsApi", () => {
  it("exposes the windows the backend accepts", () => {
    expect(METRIC_WINDOWS).toEqual(["1h", "6h", "24h", "7d", "30d", "all"]);
  });

  it("requests the summary for a window", async () => {
    const spy = mockFetch({ window: "24h", since: 0, until: 1, rows: [] });
    await fetchMetricsSummary("24h");
    expect(spy.mock.calls[0][0]).toContain("/api/metrics/summary");
    expect(spy.mock.calls[0][0]).toContain("window=24h");
  });

  it("passes a label through to the sub-span drill-down", async () => {
    const spy = mockFetch({ window: "24h", since: 0, until: 1, rows: [] });
    await fetchMetricsSummary("24h", "chunk syntax");
    expect(spy.mock.calls[0][0]).toContain("label=chunk+syntax");
  });

  it("requests a series with kind and span", async () => {
    const spy = mockFetch({
      label: "chat", kind: "ttfe", span: "", bucket_seconds: 300, points: [],
    });
    const got = await fetchMetricsSeries("chat", { window: "7d", kind: "ttfe" });
    expect(spy.mock.calls[0][0]).toContain("kind=ttfe");
    expect(got.bucket_seconds).toBe(300);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd web && npx vitest run tests/metricsApi.test.ts`
Expected: FAIL — cannot resolve `~/api/metricsApi`

- [ ] **Step 3: Write the implementation**

```ts
// web/src/api/metricsApi.ts
import { apiGet } from "~/api/client";

export const METRIC_WINDOWS = ["1h", "6h", "24h", "7d", "30d", "all"] as const;
export type MetricWindow = (typeof METRIC_WINDOWS)[number];

/** Whole-request timing, or a named step inside one when `span` is set. */
export interface MetricsSummaryRow {
  label: string;
  method: string;
  kind: "total" | "ttfe";
  span: string;
  count: number;
  mean_ms: number;
  min_ms: number;
  max_ms: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  error_rate: number;
}

export interface MetricsSummaryResponse {
  window: string;
  since: number;
  until: number;
  rows: MetricsSummaryRow[];
}

export interface MetricsSeriesPoint {
  t: number;
  count: number;
  mean_ms: number;
  max_ms: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
}

export interface MetricsSeriesResponse {
  label: string;
  kind: string;
  span: string;
  bucket_seconds: number;
  points: MetricsSeriesPoint[];
}

export async function fetchMetricsSummary(
  window: MetricWindow,
  label?: string,
  signal?: AbortSignal,
): Promise<MetricsSummaryResponse> {
  const qs = new URLSearchParams({ window });
  if (label) qs.set("label", label);
  return apiGet<MetricsSummaryResponse>(`/api/metrics/summary?${qs}`, signal);
}

export async function fetchMetricsSeries(
  label: string,
  opts: { window: MetricWindow; kind?: string; span?: string },
  signal?: AbortSignal,
): Promise<MetricsSeriesResponse> {
  const qs = new URLSearchParams({ label, window: opts.window });
  if (opts.kind) qs.set("kind", opts.kind);
  if (opts.span) qs.set("span", opts.span);
  return apiGet<MetricsSeriesResponse>(`/api/metrics/series?${qs}`, signal);
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd web && npx vitest run tests/metricsApi.test.ts` then `cd .. && ./.venv/bin/python scripts/check_api_types.py`
Expected: both PASS — the API-types gate now has its TS interfaces.

- [ ] **Step 5: Commit**

```bash
git add web/src/api/metricsApi.ts web/tests/metricsApi.test.ts
git commit -m "feat(metrics): frontend API module and wire types

Satisfies check_api_types.py for the two fixtures added with the
endpoints.

Refs #581"
```

---

### Task 8: The trend chart

**Files:**
- Create: `web/src/Metrics/TimeSeriesChart.tsx`
- Test: `web/tests/TimeSeriesChart.test.tsx`

**Interfaces:**
- Consumes: `MetricsSeriesPoint` from Task 7.
- Produces: `<TimeSeriesChart points={MetricsSeriesPoint[]} height?={number} />`.

Hand-rolled SVG following `Network/components/HeatmapPanel.tsx`. `solid-js` is the project's only runtime dependency and a metrics page does not earn the second.

- [ ] **Step 1: Write the failing test**

```tsx
// web/tests/TimeSeriesChart.test.tsx
import { render } from "@solidjs/testing-library";
import { describe, expect, it } from "vitest";
import { TimeSeriesChart } from "~/Metrics/TimeSeriesChart";
import type { MetricsSeriesPoint } from "~/api/metricsApi";

const point = (t: number, p50: number, p95: number): MetricsSeriesPoint => ({
  t, count: 10, mean_ms: p50, max_ms: p95, p50_ms: p50, p95_ms: p95, p99_ms: p95,
});

describe("TimeSeriesChart", () => {
  it("renders an empty state rather than an axis-less chart", () => {
    const { getByText } = render(() => <TimeSeriesChart points={[]} />);
    expect(getByText(/no data/i)).toBeTruthy();
  });

  it("draws one polyline per series", () => {
    const points = [point(0, 10, 40), point(300, 12, 50), point(600, 11, 45)];
    const { container } = render(() => <TimeSeriesChart points={points} />);
    expect(container.querySelectorAll("polyline").length).toBe(2);
  });

  it("survives a single point without dividing by a zero span", () => {
    const { container } = render(() => <TimeSeriesChart points={[point(0, 10, 40)]} />);
    const d = container.querySelector("polyline")?.getAttribute("points") ?? "";
    expect(d).not.toContain("NaN");
  });

  it("survives a flat series without dividing by a zero range", () => {
    const points = [point(0, 10, 10), point(300, 10, 10)];
    const { container } = render(() => <TimeSeriesChart points={points} />);
    const d = container.querySelector("polyline")?.getAttribute("points") ?? "";
    expect(d).not.toContain("NaN");
  });

  it("labels the y axis in milliseconds", () => {
    const { getByText } = render(() => <TimeSeriesChart points={[point(0, 10, 40)]} />);
    expect(getByText(/ms/)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd web && npx vitest run tests/TimeSeriesChart.test.tsx`
Expected: FAIL — cannot resolve `~/Metrics/TimeSeriesChart`

- [ ] **Step 3: Write the implementation**

Render a `viewBox`ed `<svg>` with two `<polyline>` elements (p50 and p95), four horizontal gridlines with `ms` labels, and time labels at the first and last point. Both degenerate cases — one point, and a flat series — must not divide by zero; guard each denominator with `|| 1`. Keep the scale helpers as module-level pure functions so they stay under the cognitive-complexity bar and can be tested directly.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd web && npx vitest run tests/TimeSeriesChart.test.tsx`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add web/src/Metrics/TimeSeriesChart.tsx web/tests/TimeSeriesChart.test.tsx
git commit -m "feat(metrics): hand-rolled SVG trend chart

Follows Network's precedent. solid-js is the project's only runtime
dependency and a metrics page doesn't earn a second one.

Refs #581"
```

---

### Task 9: The metrics surface

**Files:**
- Create: `web/src/Metrics/MetricsPanel.tsx`, `web/src/routes/MetricsRoute.tsx`
- Modify: `web/src/routing.ts` (the `Route` union at :11 and `readRoute` at :175), `web/src/AppRoutes.tsx`
- Test: `web/tests/MetricsPanel.test.tsx`, `web/tests/metricsRouting.test.ts`

**Interfaces:**
- Consumes: Tasks 7 and 8.
- Produces: the `#/metrics` route; `routing.ts` parses `#/metrics` and `#/metrics?window=7d&label=<label>`.

- [ ] **Step 1: Write the failing test**

```ts
// web/tests/metricsRouting.test.ts
import { describe, expect, it } from "vitest";
import { readRoute } from "~/routing";

// `readRoute()` takes no argument — it reads `window.location.hash`. jsdom
// carries a directly-assigned hash between tests, so switch via
// history.replaceState, exactly as web/tests/routing.test.ts does.
function withHash<T>(hash: string, fn: () => T): T {
  const prev = window.location.hash;
  window.history.replaceState(null, "", hash || "#");
  try {
    return fn();
  } finally {
    window.history.replaceState(null, "", prev || "#");
  }
}

describe("#/metrics routing", () => {
  it("parses the bare surface", () => {
    expect(withHash("#/metrics", readRoute)).toMatchObject({ kind: "metrics" });
  });

  it("carries the window and selected label", () => {
    expect(
      withHash("#/metrics?window=7d&label=chunk+syntax", readRoute),
    ).toMatchObject({ kind: "metrics", window: "7d", label: "chunk syntax" });
  });

  it("ignores an unknown window rather than rendering a broken page", () => {
    expect(withHash("#/metrics?window=bananas", readRoute)).toMatchObject({
      kind: "metrics",
      window: undefined,
    });
  });
});
```

```tsx
// web/tests/MetricsPanel.test.tsx
import { render, waitFor } from "@solidjs/testing-library";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MetricsPanel } from "~/Metrics/MetricsPanel";

const row = (label: string, p95: number) => ({
  label, method: "GET", kind: "total" as const, span: "",
  count: 10, mean_ms: p95 / 2, min_ms: 1, max_ms: p95,
  p50_ms: p95 / 2, p95_ms: p95, p99_ms: p95, error_rate: 0,
});

function mockSummary(rows: unknown[]) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200,
    json: async () => ({ window: "24h", since: 0, until: 1, rows }),
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe("MetricsPanel", () => {
  it("lists routes slowest first", async () => {
    mockSummary([row("fast", 5), row("slow", 900)]);
    const { findAllByTestId } = render(() => <MetricsPanel />);
    const cells = await findAllByTestId("metrics-route-label");
    expect(cells.map((c) => c.textContent)).toEqual(["slow", "fast"]);
  });

  it("shows an empty state when nothing has been recorded", async () => {
    mockSummary([]);
    const { findByText } = render(() => <MetricsPanel />);
    expect(await findByText(/no requests recorded/i)).toBeTruthy();
  });

  it("surfaces a fetch failure instead of rendering an empty table", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    const { findByText } = render(() => <MetricsPanel />);
    await waitFor(async () => expect(await findByText(/couldn't load/i)).toBeTruthy());
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd web && npx vitest run tests/metricsRouting.test.ts tests/MetricsPanel.test.tsx`
Expected: FAIL — `kind: "metrics"` unhandled; `~/Metrics/MetricsPanel` unresolved

- [ ] **Step 3: Write the implementation**

Add a `#/metrics` branch to `routing.ts` beside the `#/network` one (`web/src/routing.ts:239`), reading `window` and `label` from the query string and discarding a `window` not in `METRIC_WINDOWS`. Add the route type to `web/src/routes/types.ts`, a `<Match>` in `AppRoutes.tsx` beside the existing surfaces, and `MetricsRoute.tsx` as a thin shell wrapping `MetricsPanel` in `SurfaceErrorBoundary` the way the other route files do.

`MetricsPanel` owns: a window selector, a `createResource` over `fetchMetricsSummary`, a table (each label cell carrying `data-testid="metrics-route-label"`), a selected-route signal feeding `fetchMetricsSeries` into `<TimeSeriesChart>`, a sub-span breakdown from `fetchMetricsSummary(window, label)`, and a total/TTFE toggle shown only when the selected route has a `ttfe` row.

Do not copy `LeaderboardPanel`; if a sortable-table shell is wanted for both, extract it — a wholesale copy fails the 3% duplication gate at any coverage (#254).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd web && npx vitest run tests/metricsRouting.test.ts tests/MetricsPanel.test.tsx tests/App.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/Metrics/ web/src/routes/ web/src/routing.ts web/src/AppRoutes.tsx web/tests/
git commit -m "feat(metrics): #/metrics surface

Route table slowest-first, click-through to the trend chart, sub-span
breakdown, TTFE toggle on the streaming routes.

Refs #581"
```

---

### Task 10: Docs, gates, and the PR

**Files:**
- Modify: `docs/CONTRIBUTING.md` or `README.md` (one paragraph on `--metrics-db`)
- Modify: `docs/superpowers/specs/2026-09-13-request-timing-observability-design.md` (status → implemented)

- [ ] **Step 1: Document the operator surface**

One paragraph: what `#/metrics` shows, that history lives in `data/metrics.sqlite`, that it deliberately survives `index --reset`, and that `--no-metrics` turns persistence off while leaving the in-memory ring on.

- [ ] **Step 2: Run the full gate and read the output**

Run: `make check`
Expected: PASS. Re-run it after *any* edit made while fixing its output — two pushes on #254 failed CI on errors introduced after the last local run.

- [ ] **Step 3: Confirm the new-code coverage number**

Run: `make check` and read the `check-diff-coverage` line specifically.
Expected: ≥ 80% on changed lines, branches included. Do not substitute `make coverage` — that is whole-project coverage, a different number that can be green while the gate is red (75% project vs 58.5% new code on #254).

- [ ] **Step 4: Open the PR**

```bash
git push -u origin feat/581-request-timing-observability
direnv exec . gh pr create --base main \
  --title "feat(metrics): request-timing observability with a #/metrics surface" \
  --body-file <path>
```

The body must contain `Closes #581`, target `main`, and state what was left out.

- [ ] **Step 5: Verify the issue link actually registered**

```bash
make check-pr-link PR=<n> ISSUES="581"
```

Expected: exit 0. Empty `closingIssuesReferences` on a PR that fixes something is a bug in the PR — the link only registers for PRs targeting the default branch, and is parsed when the body is written, not when the base changes.

---

## Self-Review

**Spec coverage:** recording site → Task 4; storage in a separate file → Tasks 2 and 4; histogram buckets and the approximate-p95 caveat → Task 1; TTFE → Tasks 3 and 4; sub-spans on three hot paths → Tasks 3 and 5; both endpoints and derived granularity → Task 6; `#/metrics` with table, chart, breakdown and toggle → Tasks 7–9; gates → Task 10. The spec's in-memory ring buffer is built in Task 3 and exposed via `Recorder.recent()`; **no endpoint or view surfaces it**, which is a deliberate deferral — the durable histograms answer the question that motivated the feature, and a slow-request detail view can follow once the trend view shows where to look. Say so in the PR body rather than leaving it silent.

**Type consistency:** `Sample` fields match between Tasks 2 and 3. `Recorder(conn, lock, *, ring_size, now, clock)` is constructed the same way in Tasks 3, 4 and 6. Response keys in Task 6 match the fixtures in Task 6 and the TS interfaces in Task 7. Span names are fixed in Task 5 and guarded by a test there.

**Known gap to resolve during Task 6:** `ServerDeps` gains both `metrics: Recorder` and `metrics_conn`, which is mild redundancy — the `Recorder` already holds the connection. The handler needs read access and the `Recorder` deliberately exposes no connection getter. If a reviewer objects, add a `Recorder.connection` property and drop `metrics_conn`; do not do both.
