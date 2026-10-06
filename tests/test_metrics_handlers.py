"""Window parsing, granularity selection, and the two read endpoints."""

from __future__ import annotations

import sqlite3
import time

import pytest
from conftest import StubBackend, make_deps

from minerva.http.handlers.metrics import (
    _bucket_seconds_for,
    _handle_metrics_series,
    _handle_metrics_summary,
    _parse_offset,
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
    # `health` joined the four original keys additively: an empty `rows` used
    # to mean no traffic, metrics off, or every write failing, with no way to
    # tell which. Asserted exactly, so a future key is a deliberate change.
    body = _handle_metrics_summary(deps, {"window": "24h"})
    assert set(body) == {"window", "since", "until", "rows", "health"}
    assert isinstance(body["rows"], list)


def test_summary_returns_recorded_routes(deps):
    with deps.metrics.record("works list", "GET") as span:
        span.status = 200
    body = _handle_metrics_summary(deps, {"window": "all"})
    # Filtered by kind: the unlabeled summary carries a `ttfe` row and, since
    # CPU entered the aggregate, a `cpu` row for the same route.
    assert [r["label"] for r in body["rows"] if r["kind"] == "total"] == ["works list"]


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


# --- `offset`: shifting the window back by whole windows (#600) ---------
#
# The metrics view wants "is this route slower than it was?", which needs a
# baseline. Before this parameter there was no way to ask for one: `_range`
# anchored `until` to `time.time()`, so a second call could only ever fetch
# a window ending now, and comparing 6h against 24h compares a set against
# its own superset.


def test_summary_offset_shifts_the_window_back_one_whole_width(deps):
    body = _handle_metrics_summary(deps, {"window": "1h", "offset": "1"})
    assert body["until"] == pytest.approx(time.time() - 3_600, abs=5)
    assert body["since"] == pytest.approx(time.time() - 7_200, abs=5)


def test_summary_offset_excludes_rows_recorded_in_the_current_window(deps):
    with deps.metrics.record("works list", "GET") as span:
        span.status = 200
    rows_1h = _handle_metrics_summary(deps, {"window": "1h"})["rows"]
    assert [r["label"] for r in rows_1h if r["kind"] == "total"] == ["works list"]
    prior = _handle_metrics_summary(deps, {"window": "1h", "offset": "1"})
    assert prior["rows"] == []


def test_series_offset_shifts_the_window_back_too(deps):
    # Asserted against a recorded sample, not an empty DB: without one,
    # `points == []` holds whether or not the offset does anything.
    with deps.metrics.record("works list", "GET") as span:
        span.status = 200
    now = _handle_metrics_series(deps, {"label": "works list", "window": "6h"})
    assert len(now["points"]) == 1
    prior = _handle_metrics_series(deps, {"label": "works list", "window": "6h", "offset": "1"})
    assert prior["points"] == []


def test_summary_offset_zero_matches_an_absent_offset(deps):
    a = _handle_metrics_summary(deps, {"window": "1h", "offset": "0"})
    b = _handle_metrics_summary(deps, {"window": "1h"})
    assert a["since"] == pytest.approx(b["since"], abs=5)
    assert a["until"] == pytest.approx(b["until"], abs=5)


def test_parse_offset_defaults_to_zero_when_absent():
    assert _parse_offset(None) == 0


def test_parse_offset_reads_a_non_negative_integer():
    assert _parse_offset("0") == 0
    assert _parse_offset("3") == 3


@pytest.mark.parametrize("value", ["-1", "1.5", "bananas", "", " "])
def test_parse_offset_rejects_anything_else(value):
    with pytest.raises(_HTTPError):
        _parse_offset(value)


def test_offset_is_rejected_for_the_unbounded_window(deps):
    # `all` starts at the epoch, so there is no "previous all" to shift to.
    # Silently ignoring the offset would hand the caller the same rows it
    # already had and let it render a 0% delta as though it were measured.
    with pytest.raises(_HTTPError):
        _handle_metrics_summary(deps, {"window": "all", "offset": "1"})


def test_offset_zero_is_still_fine_for_the_unbounded_window(deps):
    body = _handle_metrics_summary(deps, {"window": "all", "offset": "0"})
    assert body["since"] == 0.0
