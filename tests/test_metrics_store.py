"""The durable timing store: upsert accumulation and read aggregation."""

from __future__ import annotations

import sqlite3

import pytest

from minerva.metrics import store as m


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(m.SCHEMA)
    yield c
    c.close()


def _sample(**kw):
    base = {
        "at": 1_700_000_000.0,
        "label": "work range",
        "method": "GET",
        "kind": "total",
        "span": "",
        "status_class": 2,
        "ms": 12.0,
    }
    base.update(kw)
    return m.Sample(**base)


def test_write_accumulates_into_one_row(conn):
    m.write(conn, [_sample(), _sample(), _sample()])
    rows = conn.execute("SELECT count, sum_ms FROM request_timings").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 3


def test_write_never_leaves_a_null_span(conn):
    # NULL in the composite PK silently defeats the upsert: ON CONFLICT
    # never matches NULL, so each write would insert a duplicate row whose
    # count stays at 1. Guarding it here because the failure is silent.
    m.write(conn, [_sample(), _sample()])
    spans = [r[0] for r in conn.execute("SELECT span FROM request_timings")]
    assert spans == [""]
    assert None not in spans


def test_write_separates_kinds(conn):
    m.write(conn, [_sample(kind="total"), _sample(kind="ttfe")])
    assert conn.execute("SELECT count(*) FROM request_timings").fetchone()[0] == 2


def test_write_floors_to_the_bucket(conn):
    # Both timestamps must sit INSIDE one 300s bucket. 1_700_000_001 and
    # 1_700_000_299 are 298s apart but straddle a boundary (they floor to
    # 1699999800 and 1700000100) — verified, and the reason these values
    # are not those.
    m.write(conn, [_sample(at=1_700_000_100.0), _sample(at=1_700_000_399.0)])
    starts = [r[0] for r in conn.execute("SELECT DISTINCT bucket_start FROM request_timings")]
    assert starts == [1_700_000_100]


def test_write_splits_across_bucket_boundary(conn):
    m.write(conn, [_sample(at=1_700_000_000.0), _sample(at=1_700_000_400.0)])
    assert conn.execute("SELECT count(*) FROM request_timings").fetchone()[0] == 2


def test_write_tracks_min_and_max(conn):
    m.write(conn, [_sample(ms=5.0), _sample(ms=90.0), _sample(ms=40.0)])
    lo, hi = conn.execute("SELECT min_ms, max_ms FROM request_timings").fetchone()
    assert (lo, hi) == (5.0, 90.0)


def test_write_empty_is_a_noop(conn):
    m.write(conn, [])
    assert conn.execute("SELECT count(*) FROM request_timings").fetchone()[0] == 0


def test_summary_reports_exact_mean(conn):
    m.write(conn, [_sample(ms=10.0), _sample(ms=20.0), _sample(ms=30.0)])
    rows = m.summary(conn, since=0, until=2_000_000_000)
    assert len(rows) == 1
    assert rows[0]["count"] == 3
    assert rows[0]["mean_ms"] == pytest.approx(20.0)


def test_summary_error_rate(conn):
    m.write(conn, [_sample(status_class=2)] * 3 + [_sample(status_class=5)])
    rows = m.summary(conn, since=0, until=2_000_000_000)
    # Rows collapse per (label, method, kind, span); error_rate is the 5xx share.
    assert rows[0]["error_rate"] == pytest.approx(0.25)


def test_summary_respects_the_window(conn):
    m.write(conn, [_sample(at=1_000_000_000.0), _sample(at=1_700_000_000.0)])
    rows = m.summary(conn, since=1_600_000_000, until=2_000_000_000)
    assert rows[0]["count"] == 1


def test_summary_label_filter_returns_sub_spans(conn):
    m.write(conn, [_sample(span=""), _sample(span="stanza_parse")])
    rows = m.summary(conn, since=0, until=2_000_000_000, label="work range")
    assert {r["span"] for r in rows} == {"stanza_parse"}


def test_series_groups_by_requested_granularity(conn):
    m.write(conn, [_sample(at=1_700_000_000.0), _sample(at=1_700_001_000.0)])
    points = m.series(
        conn, label="work range", kind="total", span="",
        since=0, until=2_000_000_000, bucket_seconds=3600,
    )
    assert len(points) == 1
    assert points[0]["count"] == 2


def test_series_is_ordered_by_time(conn):
    m.write(conn, [_sample(at=1_700_100_000.0), _sample(at=1_700_000_000.0)])
    points = m.series(
        conn, label="work range", kind="total", span="",
        since=0, until=2_000_000_000, bucket_seconds=300,
    )
    assert [p["t"] for p in points] == sorted(p["t"] for p in points)


def test_series_empty_when_nothing_matches(conn):
    m.write(conn, [_sample()])
    points = m.series(
        conn, label="nonexistent", kind="total", span="",
        since=0, until=2_000_000_000, bucket_seconds=300,
    )
    assert points == []
