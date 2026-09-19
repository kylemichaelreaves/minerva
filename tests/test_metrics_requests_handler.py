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


def _add(d, *, n=0, at=T0, label="works list", method="GET", status=200,
         total=10.0, phases=()):
    d.metrics_conn.execute(
        "INSERT INTO request_spans"
        " (id, at, label, method, status, total_ms, accounted_ms, phases)"
        " VALUES (?,?,?,?,?,?,?,?)",  # named, so an added column cannot break this
        (f"id{n:04d}", at, label, method, status, total,
         sum(p["ms"] for p in phases), json.dumps(list(phases))),
    )
    d.metrics_conn.commit()


def test_shape(deps):
    _add(deps, at=T0)
    body = _handle_metrics_requests(deps, {"window": "all"})
    assert set(body) == {"window", "since", "until", "rows", "limit"}
    row = body["rows"][0]
    assert set(row) == {
        "id", "at", "label", "method", "status",
        "total_ms", "accounted_ms", "unaccounted_ms", "phases", "cpu_ms",
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
