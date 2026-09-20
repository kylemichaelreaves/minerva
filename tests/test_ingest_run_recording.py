"""Both ingest paths feed the same recorder.

`--jobs` defaults to 1, so the SEQUENTIAL path is the default. Instrumenting
only the parallel path would mean the ordinary invocation records nothing,
silently — and recording is unconditional rather than following `--timing`,
because a history assembled from the runs where someone remembered a flag is
not a history.
"""

from __future__ import annotations

from minerva.ingest.parallel import ingest_runs_from_results
from minerva.metrics.ingest_runs import IngestRunLog


def test_a_successful_worker_result_becomes_an_ok_row():
    log = IngestRunLog(run_id="r1")
    ingest_runs_from_results(
        {"plato_grc": {"source_id": "plato_grc", "elapsed": 41.2, "count": 12043}}, log
    )
    (row,) = log.rows()
    assert row.status == "ok"
    assert row.elapsed_ms == 41200.0
    assert row.chunks == 12043
    assert row.error is None


def test_a_skipped_worker_result_becomes_a_skipped_row():
    log = IngestRunLog(run_id="r1")
    ingest_runs_from_results(
        {"marx_pgde": {"source_id": "marx_pgde", "skipped": True, "reason": "no-path",
                       "elapsed": 0.0, "count": 0}},
        log,
    )
    (row,) = log.rows()
    assert row.status == "skipped"
    assert row.chunks == 0


def test_a_failed_worker_result_keeps_its_error():
    log = IngestRunLog(run_id="r1")
    ingest_runs_from_results(
        {"theognis": {"source_id": "theognis", "elapsed": 3.1, "count": 0,
                      "error": "HTTPError: 403"}},
        log,
    )
    (row,) = log.rows()
    assert row.status == "failed"
    assert row.error == "HTTPError: 403"


def test_failure_wins_over_skipped():
    """A result can carry both. A source that failed is not a source that was
    skipped, and reporting it as skipped would hide the failure."""

    log = IngestRunLog(run_id="r1")
    ingest_runs_from_results(
        {"x": {"source_id": "x", "skipped": True, "elapsed": 0.0, "count": 0,
               "error": "boom"}},
        log,
    )
    assert log.rows()[0].status == "failed"


def test_every_source_in_the_run_gets_a_row():
    log = IngestRunLog(run_id="r1")
    ingest_runs_from_results(
        {
            "a": {"source_id": "a", "elapsed": 1.0, "count": 10},
            "b": {"source_id": "b", "skipped": True, "elapsed": 0.0, "count": 0},
            "c": {"source_id": "c", "elapsed": 2.0, "count": 0, "error": "nope"},
        },
        log,
    )
    assert {r.source_id: r.status for r in log.rows()} == {
        "a": "ok", "b": "skipped", "c": "failed"
    }
    assert len({r.run_id for r in log.rows()}) == 1
