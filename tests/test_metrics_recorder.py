"""The request-timing context manager: what it records, and when."""

from __future__ import annotations

import logging
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
    with pytest.raises(RuntimeError), rec.record("chat", "POST"):
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


def test_error_status_records_what_the_client_actually_received(conn):
    # GET/PATCH/non-streaming POST reach a non-200 only by raising, so
    # without this mapping a 404 or a 400 the client correctly received is
    # filed under `status_class = 5` and the Errors column reads 100% for
    # a route that is merely rejecting bad input.
    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=FakeClock())
    with pytest.raises(KeyError), rec.record("work range", "GET", error_status=lambda _: 404):
        raise KeyError("no such work")
    assert conn.execute("SELECT status_class FROM request_timings").fetchone()[0] == 4


def _cannot_be_written(conn):
    """Make every subsequent `write` raise a real `sqlite3.Error`.

    Dropping the table stands in for the operational triggers — a full
    disk, a file locked by another process, a read-only filesystem — none
    of which can be provoked from a test but all of which surface here as
    the same exception type.
    """

    conn.execute("DROP TABLE request_timings")


def test_a_failing_write_does_not_reach_the_caller(conn):
    # The write runs in `record()`'s `finally`, which every dispatch site
    # sits inside its own `except Exception`: an exception here answers
    # 500 for a request that succeeded, and on the streaming path writes a
    # second response onto a connection that already has one.
    _cannot_be_written(conn)
    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=FakeClock())
    with rec.record("work range", "GET") as span:
        span.status = 200
    # Sample dropped, request unharmed, ring still filled.
    assert len(rec.recent()) == 1


def test_a_failing_write_is_logged_once_not_once_per_request(conn, caplog):
    # A full disk fails on every request; one line each would bury the log.
    _cannot_be_written(conn)
    rec = Recorder(conn, now=lambda: 1_700_000_000.0, clock=FakeClock())
    with caplog.at_level(logging.WARNING, logger="minerva.metrics.recorder"):
        for _ in range(3):
            with rec.record("work range", "GET") as span:
                span.status = 200
    assert len(caplog.records) == 1
    assert "metrics write failed" in caplog.records[0].message
