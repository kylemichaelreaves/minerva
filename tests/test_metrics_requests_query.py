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
