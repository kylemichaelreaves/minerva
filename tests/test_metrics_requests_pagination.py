"""Keyset pagination over `request_spans`.

Offset pagination would drift: the table is append-only and sorted
newest-first, so rows arriving between two page fetches push everything down
and the reader sees the same request on consecutive pages. A cursor on
`(at, id)` cannot do that — it names a position in the ordering rather than a
distance from the top.

The tiebreak on `id` is not decorative: `at` is a float from `time.time()`,
and two requests finishing in the same microsecond would otherwise straddle
the boundary and one would be skipped.
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


def _add(c, n, *, at):
    c.execute(
        "INSERT INTO request_spans"
        " (id, at, label, method, status, total_ms, accounted_ms, phases)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (f"id{n:04d}", at, "works list", "GET", 200, 10.0, 0.0, json.dumps([])),
    )
    c.commit()


def _ids(rows):
    return [r["id"] for r in rows]


def test_a_page_and_its_successor_do_not_overlap(conn):
    for i in range(10):
        _add(conn, i, at=T0 + i)
    first = m.requests(conn, since=0.0, until=T0 + 100, limit=4)
    nxt = m.requests(
        conn, since=0.0, until=T0 + 100, limit=4,
        before_at=first[-1]["at"], before_id=first[-1]["id"],
    )
    assert set(_ids(first)) & set(_ids(nxt)) == set()
    assert _ids(first) + _ids(nxt) == [f"id{i:04d}" for i in range(9, 1, -1)]


def test_a_row_inserted_between_pages_does_not_shift_the_second(conn):
    """The whole reason for keyset. With offset, a newer row pushes the
    window down and page two repeats page one's last entry."""

    for i in range(6):
        _add(conn, i, at=T0 + i)
    first = m.requests(conn, since=0.0, until=T0 + 100, limit=3)
    _add(conn, 99, at=T0 + 50)          # newer than everything already seen
    nxt = m.requests(
        conn, since=0.0, until=T0 + 100, limit=3,
        before_at=first[-1]["at"], before_id=first[-1]["id"],
    )
    assert set(_ids(first)) & set(_ids(nxt)) == set()
    assert "id0099" not in _ids(nxt)


def test_rows_sharing_an_instant_are_not_skipped(conn):
    """`at` is a float from `time.time()`. Two requests can land on the same
    value, and a cursor on `at` alone would drop one of them."""

    for i in range(4):
        _add(conn, i, at=T0)            # identical timestamps
    first = m.requests(conn, since=0.0, until=T0 + 100, limit=2)
    nxt = m.requests(
        conn, since=0.0, until=T0 + 100, limit=2,
        before_at=first[-1]["at"], before_id=first[-1]["id"],
    )
    assert len(_ids(first) + _ids(nxt)) == 4
    assert len(set(_ids(first) + _ids(nxt))) == 4


def test_the_cursor_respects_the_window(conn):
    _add(conn, 0, at=T0 - 10_000)
    for i in range(1, 4):
        _add(conn, i, at=T0 + i)
    rows = m.requests(
        conn, since=T0 - 100, until=T0 + 100, limit=10,
        before_at=T0 + 3, before_id="id0003",
    )
    assert _ids(rows) == ["id0002", "id0001"]


def test_the_cursor_respects_the_filters(conn):
    for i in range(4):
        _add(conn, i, at=T0 + i)
    conn.execute("UPDATE request_spans SET status = 500 WHERE id IN ('id0001','id0003')")
    conn.commit()
    rows = m.requests(
        conn, since=0.0, until=T0 + 100, limit=10, errors_only=True,
        before_at=T0 + 3, before_id="id0003",
    )
    assert _ids(rows) == ["id0001"]


def test_no_cursor_starts_at_the_newest(conn):
    for i in range(3):
        _add(conn, i, at=T0 + i)
    assert _ids(m.requests(conn, since=0.0, until=T0 + 100))[0] == "id0002"
