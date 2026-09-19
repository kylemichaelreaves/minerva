"""CPU time reaching `request_spans`, and the not-measured/measured-zero split.

99.8% of requests carry no phase, so a phase-only CPU number would be absent
from almost every row. The request-level number is what makes wall-vs-cpu
answerable for the ones with nothing instrumented inside them.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from minerva.metrics import recorder as R
from minerva.metrics import store as m
from minerva.metrics.recorder import Recorder, sub_span


class FakeCpu:
    """A CPU clock the test advances by hand."""

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


def _row(conn):
    conn.row_factory = sqlite3.Row
    return dict(conn.execute("SELECT * FROM request_spans").fetchone())


def test_the_request_row_carries_cpu_time(conn, monkeypatch):
    cpu = FakeCpu()
    monkeypatch.setattr(R, "_THREAD_TIME", cpu)
    rec = Recorder(conn, now=lambda: 1_700_000_000.0)
    with rec.record("works list", "GET") as span:
        cpu.advance(0.030)
        span.status = 200
    assert _row(conn)["cpu_ms"] == pytest.approx(30.0)


def test_a_phase_carries_its_own_cpu_in_the_json(conn, monkeypatch):
    cpu = FakeCpu()
    monkeypatch.setattr(R, "_THREAD_TIME", cpu)
    rec = Recorder(conn, now=lambda: 1_700_000_000.0)
    with rec.record("chat", "POST") as span:
        with sub_span("llm_call", cpu_clock=cpu):
            cpu.advance(0.004)
        span.status = 200
    phases = json.loads(_row(conn)["phases"])
    assert phases == [{"name": "llm_call", "ms": pytest.approx(phases[0]["ms"]),
                       "cpu_ms": pytest.approx(4.0)}]


def test_an_unmeasurable_cpu_is_null_not_zero(conn, monkeypatch):
    """`NULL` and `0.0` are different answers — "not measured" versus
    "measured, and it was idle". A reader cannot tell them apart if the
    platform's missing clock silently becomes a zero."""

    monkeypatch.setattr(R, "_THREAD_TIME", None)
    rec = Recorder(conn, now=lambda: 1_700_000_000.0)
    with rec.record("works list", "GET") as span:
        span.status = 200
    assert _row(conn)["cpu_ms"] is None


def test_a_genuinely_idle_request_records_zero_not_null(conn, monkeypatch):
    cpu = FakeCpu()
    monkeypatch.setattr(R, "_THREAD_TIME", cpu)
    rec = Recorder(conn, now=lambda: 1_700_000_000.0)
    with rec.record("works list", "GET") as span:
        span.status = 200          # no CPU burned at all
    assert _row(conn)["cpu_ms"] == 0.0


def test_an_existing_database_gains_the_column(tmp_path):
    """`data/metrics.sqlite` already exists in the wild with #619's table and
    no cpu column. Opening it must add the column, not fail and not silently
    keep writing without it."""

    path = tmp_path / "metrics.sqlite"
    c = sqlite3.connect(path)
    # The pre-Phase-2 table, exactly as #619 shipped it.
    c.executescript(
        "CREATE TABLE request_spans (id TEXT PRIMARY KEY, at REAL NOT NULL,"
        " label TEXT NOT NULL, method TEXT NOT NULL, status INTEGER NOT NULL,"
        " total_ms REAL NOT NULL, accounted_ms REAL NOT NULL, phases TEXT NOT NULL);"
    )
    c.execute("INSERT INTO request_spans VALUES ('old', 1.0, 'works list', 'GET', 200, 5.0, 0.0, '[]')")
    c.commit()
    c.close()

    conn = m.open_db(path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(request_spans)")}
    assert "cpu_ms" in cols, "migration did not run"
    # And the effect, not just that it ran: the old row reads as NOT MEASURED.
    assert conn.execute("SELECT cpu_ms FROM request_spans WHERE id='old'").fetchone()[0] is None
    conn.close()


def test_opening_an_already_migrated_database_is_a_no_op(tmp_path):
    path = tmp_path / "metrics.sqlite"
    m.open_db(path).close()
    conn = m.open_db(path)          # must not raise "duplicate column name"
    assert "cpu_ms" in {r[1] for r in conn.execute("PRAGMA table_info(request_spans)")}
    conn.close()
