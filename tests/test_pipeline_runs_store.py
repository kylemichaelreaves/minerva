"""`pipeline_runs`: where batch distributions are kept.

NOT `request_timings`. That table's vocabulary is route, method and status,
and a pipeline run has none of them — borrowing it would make `label` mean
two different things depending on the row.
"""

from __future__ import annotations

import sqlite3

import pytest

from minerva.metrics import store as m
from minerva.metrics.pipeline_stats import PipelineStats


@pytest.fixture
def conn(tmp_path):
    return m.open_db(tmp_path / "metrics.sqlite")


def _stats():
    s = PipelineStats()
    for _ in range(10):
        s.record_batch(lang="lat", backend="spacy", model="la_core_web_sm", ms=12.0, size=64)
        for _ in range(64):
            s.record_tokens(lang="lat", backend="spacy", model="la_core_web_sm", tokens=400)
    s.record_batch(lang="grc", backend="stanza", model="grc", ms=90.0, size=1)
    s.record_tokens(lang="grc", backend="stanza", model="grc", tokens=120)
    return s


def test_rows_round_trip(conn):
    m.write_pipeline_rows(conn, _stats().rows(at=1_700_000_000.0, pipeline="lemmatize"))
    got = {
        (r["lang"], r["backend"], r["model"], r["kind"]): r
        for r in m.pipeline_runs(conn)
    }
    assert ("lat", "spacy", "la_core_web_sm", "batch_duration") in got
    assert got[("lat", "spacy", "la_core_web_sm", "batch_duration")]["count"] == 10
    assert got[("grc", "stanza", "grc", "batch_duration")]["count"] == 1


def test_throughput_survives_the_round_trip(conn):
    """`items` has to come back, or chunks-per-second is unrecoverable."""

    m.write_pipeline_rows(conn, _stats().rows(at=1.0, pipeline="lemmatize"))
    row = next(
        r for r in m.pipeline_runs(conn)
        if r["lang"] == "lat" and r["kind"] == "batch_duration"
    )
    assert row["items"] == 640
    assert row["items_per_s"] == pytest.approx(640 / (120.0 / 1000.0))


def test_quantiles_are_recoverable_after_the_round_trip(conn):
    """Histogram columns are the reason this is stored at all."""

    m.write_pipeline_rows(conn, _stats().rows(at=1_700_000_000.0, pipeline="lemmatize"))
    row = next(
        r for r in m.pipeline_runs(conn)
        if r["lang"] == "lat" and r["kind"] == "batch_duration"
    )
    assert 0 < row["p50_ms"] < 100
    assert row["mean"] == pytest.approx(12.0)


def test_request_timings_is_untouched(conn):
    before = conn.execute("SELECT count(*) FROM request_timings").fetchone()[0]
    m.write_pipeline_rows(conn, _stats().rows(at=1.0, pipeline="lemmatize"))
    assert conn.execute("SELECT count(*) FROM request_timings").fetchone()[0] == before


def test_two_runs_accumulate_rather_than_overwrite(conn):
    """A distribution across the corpus means history, not last-run-wins."""

    m.write_pipeline_rows(conn, _stats().rows(at=1.0, pipeline="lemmatize"))
    m.write_pipeline_rows(conn, _stats().rows(at=2.0, pipeline="lemmatize"))
    ats = {r["at"] for r in m.pipeline_runs(conn)}
    assert ats == {1.0, 2.0}


def test_writing_nothing_is_a_no_op(conn):
    m.write_pipeline_rows(conn, [])
    assert m.pipeline_runs(conn) == []


def test_an_old_metrics_database_gains_the_table(tmp_path):
    """Operator machines already have metrics.sqlite without this table."""

    path = tmp_path / "metrics.sqlite"
    plain = sqlite3.connect(path)
    plain.executescript("CREATE TABLE request_timings (bucket_start INTEGER);")
    plain.commit()
    plain.close()
    conn = m.open_db(path)
    assert m.pipeline_runs(conn) == []       # table exists, and is empty
