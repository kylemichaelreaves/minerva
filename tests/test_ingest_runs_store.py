"""`ingest_runs`: per-source parse history, so "which source got slow" is
answerable across runs instead of scrolling back through stderr.

NOT `pipeline_runs`. That table is keyed (lang, backend, model) and holds
histograms; a source has no language, no engine and no model, and one elapsed
per run is a scalar. Forcing it in would make `count` mean two different
things depending on the row.
"""

from __future__ import annotations

import pytest

from minerva.metrics import store as m
from minerva.metrics.ingest_runs import IngestRun


@pytest.fixture
def conn(tmp_path):
    c = m.open_db(tmp_path / "metrics.sqlite")
    yield c
    c.close()


def _run(source_id, *, at=1.0, run_id="r1", status="ok", ms=1000.0, chunks=100, error=None):
    return IngestRun(
        at=at,
        run_id=run_id,
        source_id=source_id,
        status=status,
        elapsed_ms=ms,
        chunks=chunks,
        error=error,
    )


def test_rows_round_trip(conn):
    m.write_ingest_runs(conn, [_run("plato_grc", ms=41200.0, chunks=12043)])
    (row,) = m.ingest_runs(conn)
    assert row["source_id"] == "plato_grc"
    assert row["elapsed_ms"] == pytest.approx(41200.0)
    assert row["chunks"] == 12043
    assert row["status"] == "ok"


def test_history_for_one_source_is_ordered(conn):
    for i, ms in enumerate((1000.0, 2000.0, 1500.0)):
        m.write_ingest_runs(conn, [_run("plato_grc", at=float(i), run_id=f"r{i}", ms=ms)])
    got = m.ingest_runs(conn, source_id="plato_grc")
    assert [r["elapsed_ms"] for r in got] == [1500.0, 2000.0, 1000.0]  # newest first


def test_a_skipped_source_is_distinguishable_from_a_fast_one(conn):
    """The trap this column exists for. A skipped source returns elapsed=0,
    and stored without a status it reads as a source that suddenly got
    instant — the same not-measured/measured-zero confusion the request
    layer had to fix twice."""

    m.write_ingest_runs(
        conn,
        [
            _run("fast_one", ms=0.4, chunks=3),
            _run("marx_pgde", status="skipped", ms=0.0, chunks=0),
        ],
    )
    by = {r["source_id"]: r for r in m.ingest_runs(conn)}
    assert by["fast_one"]["status"] == "ok"
    assert by["marx_pgde"]["status"] == "skipped"


def test_a_failed_source_keeps_its_error(conn):
    m.write_ingest_runs(
        conn,
        [
            _run("theognis", status="failed", ms=3100.0, chunks=0, error="HTTPError: 403"),
        ],
    )
    (row,) = m.ingest_runs(conn)
    assert row["status"] == "failed"
    assert "403" in row["error"]


def test_a_successful_row_has_no_error(conn):
    m.write_ingest_runs(conn, [_run("plato_grc")])
    assert m.ingest_runs(conn)[0]["error"] is None


def test_a_partial_run_leaves_other_sources_history_alone(conn):
    """`ingest --only X` touches one source. Its history gains a point; every
    other source's history must be untouched, not zeroed or dropped."""

    m.write_ingest_runs(conn, [_run("a", at=1.0, run_id="full"), _run("b", at=1.0, run_id="full")])
    m.write_ingest_runs(conn, [_run("a", at=2.0, run_id="only", ms=900.0)])
    assert len(m.ingest_runs(conn, source_id="a")) == 2
    assert len(m.ingest_runs(conn, source_id="b")) == 1


def test_a_run_id_groups_one_invocation(conn):
    m.write_ingest_runs(
        conn,
        [
            _run("a", run_id="r1"),
            _run("b", run_id="r1"),
            _run("a", at=2.0, run_id="r2"),
        ],
    )
    assert len({r["run_id"] for r in m.ingest_runs(conn)}) == 2
    assert len([r for r in m.ingest_runs(conn) if r["run_id"] == "r1"]) == 2


def test_writing_nothing_is_a_no_op(conn):
    m.write_ingest_runs(conn, [])
    assert m.ingest_runs(conn) == []


def test_pipeline_runs_is_untouched(conn):
    m.write_ingest_runs(conn, [_run("plato_grc")])
    assert m.pipeline_runs(conn) == []
