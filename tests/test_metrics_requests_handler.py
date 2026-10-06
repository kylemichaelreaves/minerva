"""`GET /api/metrics/requests` — the endpoint behind the per-request surface."""

from __future__ import annotations

import json
import sqlite3

import pytest
from conftest import StubBackend, make_deps

from minerva.http.handlers.metrics import _handle_metrics_requests
from minerva.http.server_core import _HTTPError
from minerva.metrics import store as m

T0 = 1_700_000_000.0


@pytest.fixture
def deps(populated_db):
    c = sqlite3.connect(":memory:")
    c.executescript(m.SCHEMA)
    d = make_deps(populated_db, StubBackend(reply="ok"))
    d.metrics_conn = c
    return d


def _add(d, *, n=0, at=T0, label="works list", method="GET", status=200, total=10.0, phases=()):
    d.metrics_conn.execute(
        "INSERT INTO request_spans"
        " (id, at, label, method, status, total_ms, accounted_ms, phases)"
        " VALUES (?,?,?,?,?,?,?,?)",  # named, so an added column cannot break this
        (
            f"id{n:04d}",
            at,
            label,
            method,
            status,
            total,
            sum(p["ms"] for p in phases),
            json.dumps(list(phases)),
        ),
    )
    d.metrics_conn.commit()


def test_shape(deps):
    _add(deps, at=T0)
    body = _handle_metrics_requests(deps, {"window": "all"})
    assert set(body) == {
        "window",
        "since",
        "until",
        "rows",
        "limit",
        "has_more",
        "next_before",
    }
    row = body["rows"][0]
    assert set(row) == {
        "id",
        "at",
        "label",
        "method",
        "status",
        "total_ms",
        "accounted_ms",
        "unaccounted_ms",
        "phases",
        "cpu_ms",
        "sqlite_ms",
        "sqlite_queries",
    }


def test_filters_are_read_from_the_query_string(deps):
    _add(deps, n=0, label="chat", method="POST", status=500, at=T0)
    _add(deps, n=1, label="works list", method="GET", status=200, at=T0 + 1)
    assert len(_handle_metrics_requests(deps, {"window": "all", "label": "chat"})["rows"]) == 1
    assert len(_handle_metrics_requests(deps, {"window": "all", "errors": "1"})["rows"]) == 1
    assert len(_handle_metrics_requests(deps, {"window": "all", "method": "GET"})["rows"]) == 1
    assert len(_handle_metrics_requests(deps, {"window": "all", "phased": "1"})["rows"]) == 0


def test_no_metrics_connection_renders_empty_rather_than_500ing(deps):
    """Same posture as the summary handler: persistence being off is a
    configuration, not an error."""

    deps.metrics_conn = None
    body = _handle_metrics_requests(deps, {"window": "all"})
    assert body["rows"] == []


def test_a_junk_window_is_a_400_not_a_500(deps):
    with pytest.raises(_HTTPError):
        _handle_metrics_requests(deps, {"window": "bananas"})


def test_a_junk_limit_is_rejected_rather_than_silently_ignored(deps):
    with pytest.raises(_HTTPError):
        _handle_metrics_requests(deps, {"window": "all", "limit": "lots"})


def test_the_reported_limit_is_the_clamped_one(deps):
    """The response says what was actually applied, so a client asking for
    100,000 rows can see it got 500 rather than concluding the table is small."""

    body = _handle_metrics_requests(deps, {"window": "all", "limit": "100000"})
    assert body["limit"] == m.REQUESTS_MAX_LIMIT


def test_the_response_carries_a_cursor_for_the_next_page(deps):
    """A client should not have to reconstruct the cursor from the last row —
    that couples it to the ordering, which is exactly what keyset hides."""

    for i in range(5):
        _add(deps, n=i, at=T0 + i)
    body = _handle_metrics_requests(deps, {"window": "all", "limit": "2"})
    assert body["has_more"] is True
    assert body["next_before"] == {"at": body["rows"][-1]["at"], "id": body["rows"][-1]["id"]}


def test_the_last_page_says_so(deps):
    for i in range(2):
        _add(deps, n=i, at=T0 + i)
    body = _handle_metrics_requests(deps, {"window": "all", "limit": "10"})
    assert body["has_more"] is False
    assert body["next_before"] is None


def test_has_more_does_not_cost_an_extra_page(deps):
    """Asked for 2, got 2 — the probe row used to detect a third must not
    leak into the payload."""

    for i in range(5):
        _add(deps, n=i, at=T0 + i)
    body = _handle_metrics_requests(deps, {"window": "all", "limit": "2"})
    assert len(body["rows"]) == 2


def test_the_cursor_round_trips(deps):
    for i in range(5):
        _add(deps, n=i, at=T0 + i)
    first = _handle_metrics_requests(deps, {"window": "all", "limit": "2"})
    nxt = _handle_metrics_requests(
        deps,
        {
            "window": "all",
            "limit": "2",
            "before_at": str(first["next_before"]["at"]),
            "before_id": first["next_before"]["id"],
        },
    )
    assert {r["id"] for r in first["rows"]} & {r["id"] for r in nxt["rows"]} == set()


def test_a_junk_cursor_is_a_400_not_a_silent_first_page(deps):
    """Silently ignoring it would hand back page one while the client
    believed it was on page two — a duplicate-looking list with no error."""

    with pytest.raises(_HTTPError):
        _handle_metrics_requests(deps, {"window": "all", "before_at": "yesterday"})


def test_a_cursor_needs_both_halves(deps):
    with pytest.raises(_HTTPError):
        _handle_metrics_requests(deps, {"window": "all", "before_at": "1.0"})
