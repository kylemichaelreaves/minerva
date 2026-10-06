"""One durable row per request, so unaccounted time is per-request, not per-bucket.

`request_timings` folds requests into 5-minute buckets, so a gap between a
request's total and its phases attaches to a bucket — and a bucket mixes
requests, which loses the outlier. This table keeps the pairing.

`request_timings` is untouched by everything here.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from minerva.metrics import store as m
from minerva.metrics.recorder import Recorder, sub_span


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(m.SCHEMA)
    yield c
    c.close()


def _rows(conn):
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute("SELECT * FROM request_spans ORDER BY at")]


def test_one_row_per_request(conn):
    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=FakeClock())
    for label in ("works list", "chat", "health"):
        with rec.record(label, "GET") as span:
            span.status = 200
    assert [r["label"] for r in _rows(conn)] == ["works list", "chat", "health"]


def test_the_row_is_keyed_on_the_span_id(conn):
    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=FakeClock())
    with rec.record("works list", "GET") as span:
        span.status = 200
        expected = span.id
    assert [r["id"] for r in _rows(conn)] == [expected]


def test_unaccounted_time_is_recoverable_from_the_row(conn):
    """The whole point: total minus phases, for THIS request."""

    clock = FakeClock()
    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=clock)
    with rec.record("chat", "POST") as span:
        clock.advance(0.010)  # 10ms unmeasured before the phase
        with sub_span("llm_call", clock=clock):
            clock.advance(0.080)  # 80ms inside the phase
        clock.advance(0.010)  # 10ms unmeasured after
        span.status = 200

    (row,) = _rows(conn)
    assert row["total_ms"] == pytest.approx(100.0)
    assert row["accounted_ms"] == pytest.approx(80.0)
    assert row["total_ms"] - row["accounted_ms"] == pytest.approx(20.0)
    # Asserted by the keys this test is about, not by exact equality: the
    # phase object grows keys (Phase 2 added `cpu_ms`), and a whole-object
    # match would break on every additive change without testing anything more.
    (phase,) = json.loads(row["phases"])
    assert phase["name"] == "llm_call"
    assert phase["ms"] == pytest.approx(80.0)


def test_a_request_with_no_phase_stores_an_empty_array(conn):
    """99.8% of real requests. `[]`, not NULL — so `json_each` joins cleanly
    and the column is never a three-state value."""

    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=FakeClock())
    with rec.record("health", "GET") as span:
        span.status = 200
    (row,) = _rows(conn)
    assert row["phases"] == "[]"
    assert row["accounted_ms"] == 0.0


def test_the_full_status_is_kept_not_the_class(conn):
    """`request_timings` stores status_class (5 for any 5xx). A per-request row
    that also collapsed 404 and 400 into `4` would answer fewer questions than
    the aggregate it exists to refine."""

    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=FakeClock())
    with rec.record("work range", "GET") as span:
        span.status = 404
    assert [r["status"] for r in _rows(conn)] == [404]


def test_request_timings_is_still_written_and_unchanged(conn):
    """Both sinks on the same path. The aggregate must not regress."""

    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=FakeClock())
    with rec.record("works list", "GET") as span:
        span.status = 200
    row = conn.execute(
        "SELECT label, method, kind, span, count FROM request_timings"
        " WHERE kind = 'total' AND span = ''"
    ).fetchone()
    assert row == ("works list", "GET", "total", "", 1)


def test_both_sinks_land_in_one_transaction(conn, monkeypatch):
    """Two `with conn:` blocks would mean two commits per request. If the row
    insert fails, the sample must not have been committed either."""

    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=FakeClock())
    real = m._insert_span

    def boom(*a, **k):
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(m, "_insert_span", boom)
    with rec.record("works list", "GET") as span:
        span.status = 200
    monkeypatch.setattr(m, "_insert_span", real)

    assert conn.execute("SELECT count(*) FROM request_timings").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM request_spans").fetchone()[0] == 0
