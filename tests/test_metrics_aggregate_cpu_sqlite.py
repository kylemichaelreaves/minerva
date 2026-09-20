"""CPU and SQLite time in the AGGREGATE, not only per request.

Phases 2 and 3 wrote both to `request_spans` only — "smallest change first",
deliberately deferred. But the interesting question is per ROUTE: one request
being CPU-bound says little, while "this route is CPU-bound across 500
requests" is actionable. This puts them where the drill-down can see them.

`request_timings`' shape is unchanged; these are new (kind, span) VALUES in
the existing columns, which is what makes it additive.
"""

from __future__ import annotations

import sqlite3

import pytest

from minerva.metrics import recorder as R
from minerva.metrics import store as m
from minerva.metrics.recorder import Recorder, sub_span


class FakeCpu:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(m.SCHEMA)
    return c


def _rows(conn):
    return {
        (kind, span): (count, sum_ms)
        for kind, span, count, sum_ms in conn.execute(
            "SELECT kind, span, count, sum_ms FROM request_timings"
        )
    }


def test_the_request_cpu_lands_in_the_aggregate(conn, monkeypatch):
    cpu = FakeCpu()
    monkeypatch.setattr(R, "_THREAD_TIME", cpu)
    rec = Recorder(conn, now=lambda: 1_700_000_000.0)
    with rec.record("chunk syntax", "GET") as span:
        cpu.advance(0.030)
        span.status = 200
    assert _rows(conn)[("cpu", "")] == (1, pytest.approx(30.0))


def test_each_phase_gets_its_own_cpu_row(conn, monkeypatch):
    cpu = FakeCpu()
    monkeypatch.setattr(R, "_THREAD_TIME", cpu)
    rec = Recorder(conn, now=lambda: 1_700_000_000.0)
    with rec.record("chat", "POST") as span:
        with sub_span("llm_call", cpu_clock=cpu):
            cpu.advance(0.004)
        span.status = 200
    rows = _rows(conn)
    assert rows[("cpu", "llm_call")] == (1, pytest.approx(4.0))
    assert ("total", "llm_call") in rows          # the wall row still there


def test_sqlite_time_appears_as_its_own_span(conn):
    rec = Recorder(conn, now=lambda: 1_700_000_000.0)
    with rec.record("works list", "GET") as span:
        span.add_db(240.5)
        span.status = 200
    assert _rows(conn)[("total", "sqlite")] == (1, pytest.approx(240.5))


def test_a_route_that_touched_no_database_gets_no_sqlite_row(conn):
    """A 0 ms bar in the waterfall is noise. Absence means "no database time
    recorded for this route", which is the honest reading in an aggregate."""

    rec = Recorder(conn, now=lambda: 1_700_000_000.0)
    with rec.record("health", "GET") as span:
        span.status = 200
    assert ("total", "sqlite") not in _rows(conn)


def test_an_unmeasurable_cpu_emits_no_cpu_row(conn, monkeypatch):
    """NULL is not zero. Where `thread_time` is unavailable there is no
    measurement, and a 0 ms row would assert one."""

    monkeypatch.setattr(R, "_THREAD_TIME", None)
    rec = Recorder(conn, now=lambda: 1_700_000_000.0)
    with rec.record("works list", "GET") as span:
        span.status = 200
    assert not [k for k in _rows(conn) if k[0] == "cpu"]


def test_the_existing_rows_are_unchanged(conn):
    """Additive. The total row every consumer already reads must not move."""

    rec = Recorder(conn, now=lambda: 1_700_000_000.0)
    with rec.record("works list", "GET") as span:
        span.add_db(5.0)
        span.status = 200
    assert ("total", "") in _rows(conn)


def test_the_drilldown_returns_the_new_spans(conn):
    """`summary(label=...)` filters on `span != ''`, so sqlite and the cpu
    rows arrive together — which is why the frontend must filter by kind."""

    cpu = FakeCpu()
    rec = Recorder(conn, now=lambda: 1_700_000_000.0)
    with rec.record("chat", "POST") as span:
        span.add_db(12.0)
        span.status = 200
    rows = m.summary(conn, since=0.0, until=1_700_000_999.0, label="chat")
    assert {(r["kind"], r["span"]) for r in rows} >= {("total", "sqlite")}
