"""Reading `request_spans` back: the query behind the per-request surface.

The design's ledger filters on route, method, errors-only and has-a-phase, and
orders newest first. Those are the filters, so they belong in SQL rather than
in the client — the table is designed to hold years, and shipping a year to
the browser to filter it there is not a plan.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from minerva.metrics import store as m

T0 = 1_700_000_000.0


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(m.SCHEMA)
    return c


def _add(c, *, n=0, at=T0, label="works list", method="GET", status=200,
         total=10.0, phases=()):
    c.execute(
        "INSERT INTO request_spans"
        " (id, at, label, method, status, total_ms, accounted_ms, phases)"
        " VALUES (?,?,?,?,?,?,?,?)",  # named, so an added column cannot break this
        (f"id{n:04d}", at, label, method, status, total,
         sum(p["ms"] for p in phases), json.dumps(list(phases))),
    )
    c.commit()


def test_newest_first(conn):
    for i in range(5):
        _add(conn, n=i, at=T0 + i)
    got = m.requests(conn, since=0.0, until=T0 + 100)
    assert [r["at"] for r in got] == [T0 + 4, T0 + 3, T0 + 2, T0 + 1, T0]


def test_phases_come_back_parsed_not_as_a_json_string(conn):
    _add(conn, phases=[{"name": "llm_call", "ms": 812.4}], total=900.0)
    (row,) = m.requests(conn, since=0.0, until=T0 + 100)
    assert row["phases"] == [{"name": "llm_call", "ms": 812.4}]
    assert row["accounted_ms"] == pytest.approx(812.4)
    assert row["unaccounted_ms"] == pytest.approx(87.6)


def test_filter_by_label_and_method(conn):
    _add(conn, n=0, label="chat", method="POST")
    _add(conn, n=1, label="works list", method="GET")
    _add(conn, n=2, label="chat", method="POST")
    assert len(m.requests(conn, since=0.0, until=T0 + 100, label="chat")) == 2
    assert len(m.requests(conn, since=0.0, until=T0 + 100, method="GET")) == 1


def test_errors_only_means_4xx_and_5xx(conn):
    for i, status in enumerate((200, 404, 500, 302)):
        _add(conn, n=i, status=status, at=T0 + i)
    got = m.requests(conn, since=0.0, until=T0 + 100, errors_only=True)
    assert sorted(r["status"] for r in got) == [404, 500]


def test_phased_only_uses_the_partial_index_predicate(conn):
    """`phases != '[]'` is exactly the predicate the partial index is built on,
    so the filter the UI offers is the one the index can serve."""

    _add(conn, n=0, at=T0)
    _add(conn, n=1, at=T0 + 1, phases=[{"name": "stanza_parse", "ms": 100.0}], total=200.0)
    got = m.requests(conn, since=0.0, until=T0 + 100, phased_only=True)
    assert [r["phases"][0]["name"] for r in got] == ["stanza_parse"]


def test_the_window_is_honoured(conn):
    _add(conn, n=0, at=T0 - 10_000)
    _add(conn, n=1, at=T0)
    got = m.requests(conn, since=T0 - 100, until=T0 + 100)
    assert len(got) == 1


def test_limit_caps_the_result(conn):
    for i in range(50):
        _add(conn, n=i, at=T0 + i)
    assert len(m.requests(conn, since=0.0, until=T0 + 1000, limit=10)) == 10


def test_limit_is_clamped_so_a_caller_cannot_ask_for_the_whole_table(conn):
    """Retention is uncapped by design, so this table is expected to grow to
    years. An unbounded `limit` from a query string would let one request
    materialise all of it."""

    for i in range(5):
        _add(conn, n=i, at=T0 + i)
    got = m.requests(conn, since=0.0, until=T0 + 1000, limit=10**9)
    assert len(got) == 5
    assert m.REQUESTS_MAX_LIMIT <= 1000


def test_unaccounted_excludes_database_time(conn):
    """A request whose time is entirely SQLite must not read as unexplained.

    Phase 3 measures the database time and the row carries it, but
    `unaccounted_ms` was `total - accounted` where `accounted` counts only
    phases — so `metrics series`, at 0.3 ms total and 0.3 ms SQLite, reported
    100% unaccounted on a surface whose whole job is saying where time went.
    """

    conn.execute(
        "INSERT INTO request_spans"
        " (id, at, label, method, status, total_ms, accounted_ms, phases,"
        "  sqlite_ms, sqlite_queries)"
        " VALUES ('a', ?, 'metrics series', 'GET', 200, 0.3, 0.0, '[]', 0.3, 1)",
        (T0,),
    )
    conn.commit()
    (row,) = m.requests(conn, since=0.0, until=T0 + 100)
    assert row["unaccounted_ms"] == pytest.approx(0.0)


def test_phases_and_database_time_are_both_subtracted(conn):
    """They are disjoint: of the three instrumented spans, `llm_call` is an
    HTTP call, `stanza_parse` is NLP, and `embed_search` wraps a numpy search
    over an already-loaded matrix. None touches a connection."""

    conn.execute(
        "INSERT INTO request_spans"
        " (id, at, label, method, status, total_ms, accounted_ms, phases,"
        "  sqlite_ms, sqlite_queries)"
        " VALUES ('a', ?, 'chat', 'POST', 200, 100.0, 60.0,"
        " '[{\"name\": \"llm_call\", \"ms\": 60.0}]', 30.0, 4)",
        (T0,),
    )
    conn.commit()
    (row,) = m.requests(conn, since=0.0, until=T0 + 100)
    assert row["unaccounted_ms"] == pytest.approx(10.0)


def test_unaccounted_never_goes_negative(conn):
    """Clamped, and the clamp is a DETECTOR: reaching zero while `total_ms` is
    larger than zero means a span has started wrapping database work, so the
    two are being double-counted and the assumption above has expired."""

    conn.execute(
        "INSERT INTO request_spans"
        " (id, at, label, method, status, total_ms, accounted_ms, phases,"
        "  sqlite_ms, sqlite_queries)"
        " VALUES ('a', ?, 'chat', 'POST', 200, 10.0, 8.0,"
        " '[{\"name\": \"llm_call\", \"ms\": 8.0}]', 9.0, 2)",
        (T0,),
    )
    conn.commit()
    (row,) = m.requests(conn, since=0.0, until=T0 + 100)
    assert row["unaccounted_ms"] == 0.0


def test_a_row_without_database_timing_is_unchanged(conn):
    """Rows written before Phase 3 carry NULL, which must not be read as 0
    database time and must not change the arithmetic."""

    _add(conn, n=0, total=50.0, phases=[{"name": "llm_call", "ms": 20.0}])
    (row,) = m.requests(conn, since=0.0, until=T0 + 100)
    assert row["sqlite_ms"] is None
    assert row["unaccounted_ms"] == pytest.approx(30.0)
