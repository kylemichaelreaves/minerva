"""Both ingest paths record, and recording never fails the ingest.

`--jobs` defaults to 1, so the SEQUENTIAL path is the default one. Recording
is also unconditional rather than following `--timing`: that flag controls the
stderr print, and a history built only from runs where someone remembered a
flag is a biased sample of runs, not a trend.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from minerva import tei
from minerva.cli.ingest_cmd import _record_ingest_run
from minerva.ingest.registry import IngestSource, iter_registered_chunks
from minerva.metrics import store as m
from minerva.metrics.ingest_runs import IngestRunLog


def _fake_source(tmp_path: Path, n: int = 3) -> IngestSource:
    src = tmp_path / "src.xml"
    src.write_text("<x/>", encoding="utf-8")

    def fake_parse(path: Path):
        for i in range(n):
            yield tei.Chunk(
                chunk_id=f"c{i}", corpus="plato", author="Plato", work="Republic",
                lang="eng", section=None, book=None, page=None, speaker=None,
                text="hello", source_file="x.xml", translator=None, edition_year=None,
            )

    # path_kind="file": the default is "dir", and `path_present` would
    # reject a file under it.
    return IngestSource("plato", src, fake_parse, path_kind="file")


def _run_sequential(monkeypatch, tmp_path, *, timing: bool, log):
    fake = _fake_source(tmp_path)
    monkeypatch.setattr("minerva.ingest.registry.INGEST_SOURCES", (fake,))
    return list(
        iter_registered_chunks(
            {fake.kwarg_name: fake.default_path},
            only=frozenset({"plato"}),
            per_source_timing=timing,
            run_log=log,
        )
    )


def test_the_sequential_path_records(monkeypatch, tmp_path):
    log = IngestRunLog(run_id="r1")
    chunks = _run_sequential(monkeypatch, tmp_path, timing=False, log=log)
    assert len(chunks) == 3
    (row,) = log.rows()
    assert row.source_id == "plato"
    assert row.status == "ok"
    assert row.chunks == 3
    assert row.elapsed_ms >= 0.0


def test_recording_does_not_require_the_timing_flag(monkeypatch, tmp_path, capsys):
    """The coupling this test exists to prevent. `--timing` prints; it must
    not decide whether history is kept."""

    log = IngestRunLog(run_id="r1")
    _run_sequential(monkeypatch, tmp_path, timing=False, log=log)
    assert len(log.rows()) == 1
    assert "timing: ingest:" not in capsys.readouterr().err


def test_the_timing_flag_still_prints(monkeypatch, tmp_path, capsys):
    log = IngestRunLog(run_id="r1")
    _run_sequential(monkeypatch, tmp_path, timing=True, log=log)
    assert "timing: ingest:plato" in capsys.readouterr().err
    assert len(log.rows()) == 1


def test_neither_wanted_skips_the_counting_loop(monkeypatch, tmp_path, capsys):
    """With no log and no flag, the fast path still yields every chunk."""

    chunks = _run_sequential(monkeypatch, tmp_path, timing=False, log=None)
    assert len(chunks) == 3
    assert "timing: ingest:" not in capsys.readouterr().err


def test_record_ingest_run_writes_the_rows(monkeypatch, tmp_path):
    log = IngestRunLog(run_id="r1")
    log.record("plato", status="ok", elapsed_ms=120.0, chunks=3)
    monkeypatch.setattr("minerva.cli.ingest_cmd.DEFAULT_METRICS_DB", tmp_path / "metrics.sqlite")
    _record_ingest_run(log)
    with closing(m.open_db(tmp_path / "metrics.sqlite")) as conn:
        assert [r["source_id"] for r in m.ingest_runs(conn)] == ["plato"]


def test_an_empty_log_writes_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr("minerva.cli.ingest_cmd.DEFAULT_METRICS_DB", tmp_path / "metrics.sqlite")
    _record_ingest_run(IngestRunLog())
    assert not (tmp_path / "metrics.sqlite").exists()


def test_a_metrics_failure_never_fails_the_ingest(monkeypatch, tmp_path, capsys):
    """Losing a measurement is strictly better than losing the work that
    produced it — same posture as Recorder and PipelineStats."""

    log = IngestRunLog(run_id="r1")
    log.record("plato", status="ok", elapsed_ms=1.0, chunks=1)

    def boom(*_a, **_k):
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr("minerva.cli.ingest_cmd.metrics_store.open_db", boom)
    _record_ingest_run(log)          # must not raise
    assert "could not record run history" in capsys.readouterr().err
