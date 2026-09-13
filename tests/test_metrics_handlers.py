"""Window parsing, granularity selection, and the two read endpoints."""

from __future__ import annotations

import sqlite3

import pytest
from conftest import StubBackend, make_deps

from minerva.http.handlers.metrics import (
    _bucket_seconds_for,
    _handle_metrics_series,
    _handle_metrics_summary,
    _parse_window,
)
from minerva.http.server_core import _HTTPError
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


def test_no_metrics_connection_renders_empty_not_500(populated_db):
    # `minerva serve --no-metrics` leaves metrics_conn None. Both endpoints
    # must answer with an empty payload; persistence being off is a
    # configuration, not an error.
    d = make_deps(populated_db, StubBackend(reply="ok"))
    d.metrics_conn = None
    assert _handle_metrics_summary(d, {"window": "24h"})["rows"] == []
    assert _handle_metrics_series(d, {"label": "x", "window": "24h"})["points"] == []
