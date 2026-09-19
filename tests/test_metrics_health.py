"""Zero rows and zero errors must be distinguishable from zero rows and a fault.

Before this, a `#/metrics` page with nothing on it meant one of three things —
no traffic, metrics switched off, or every write failing — and they were
indistinguishable to a reader. `_write_failed` was a boolean latch that logged
once and then went silent, so even the log stopped saying anything.
"""

from __future__ import annotations

import sqlite3

import pytest
from conftest import StubBackend, make_deps

from minerva.http.handlers.metrics import _handle_metrics_summary
from minerva.metrics import store as m
from minerva.metrics.recorder import Recorder


class Unwritable:
    """A connection whose every write fails. `write_request` opens `with conn:`
    before executing, so both halves are stubbed (see test_metrics_recorder)."""

    def __enter__(self):
        raise sqlite3.OperationalError("disk full")

    def __exit__(self, *a):
        return False

    def execute(self, *a, **k):
        raise sqlite3.OperationalError("disk full")

    def executemany(self, *a, **k):
        raise sqlite3.OperationalError("disk full")


@pytest.fixture
def deps(populated_db):
    c = sqlite3.connect(":memory:")
    c.executescript(m.SCHEMA)
    d = make_deps(populated_db, StubBackend(reply="ok"))
    d.metrics = Recorder(c)
    d.metrics_conn = c
    return d


def test_failures_are_counted_not_just_latched(deps):
    """A boolean cannot distinguish "one failure hours ago" from "failing on
    every request right now", and that difference is the whole signal."""

    deps.metrics._conn = Unwritable()
    for _ in range(3):
        with deps.metrics.record("works list", "GET") as span:
            span.status = 200
    body = _handle_metrics_summary(deps, {"window": "all"})
    assert body["health"]["write_failures"] == 3


def test_a_healthy_recorder_reports_zero_and_persisting(deps):
    with deps.metrics.record("works list", "GET") as span:
        span.status = 200
    health = _handle_metrics_summary(deps, {"window": "all"})["health"]
    assert health == {"write_failures": 0, "persisting": True}


def test_metrics_switched_off_is_distinguishable_from_failing(deps):
    """`--no-metrics` leaves no connection. Rows are empty for a reason that
    is a configuration, not a fault — and it must not read as a fault."""

    deps.metrics_conn = None
    deps.metrics = Recorder(None)
    body = _handle_metrics_summary(deps, {"window": "all"})
    assert body["rows"] == []
    assert body["health"] == {"write_failures": 0, "persisting": False}


def test_the_four_existing_keys_are_untouched(deps):
    """Additive only: existing consumers keep working unchanged."""

    body = _handle_metrics_summary(deps, {"window": "24h"})
    assert {"window", "since", "until", "rows"} <= set(body)
    assert set(body) == {"window", "since", "until", "rows", "health"}


def test_the_log_still_fires_once_even_though_the_count_climbs(deps, caplog):
    """A full disk fails on every request; one log line each would bury the
    log. Counting and logging are now separate concerns."""

    deps.metrics._conn = Unwritable()
    with caplog.at_level("WARNING"):
        for _ in range(5):
            with deps.metrics.record("works list", "GET") as span:
                span.status = 200
    assert len([r for r in caplog.records if "metrics write failed" in r.message]) == 1
    assert deps.metrics.write_failures == 5
