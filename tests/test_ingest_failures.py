"""Loud-failure plumbing for ingest (2026-06-10 audit).

Per-file parse failures used to be a bare print-and-continue in
``corpus.pipeline.parse_dir``, and a parallel-ingest source that
failed outright was silently excluded from the shard merge — a full
ingest would overwrite ``chunks.jsonl`` WITHOUT that corpus and exit
0. These tests pin the new contract: partial output still gets
written, but failures are recorded, surfaced on stderr, and
``cmd_ingest`` exits non-zero.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from minerva import tei
from minerva.corpus import pipeline
from minerva.corpus_works import CorpusWork


def _chunk(chunk_id: str = "ok-1", text: str = "some text") -> tei.Chunk:
    return tei.Chunk(
        chunk_id=chunk_id,
        corpus="plato",
        author="Plato",
        work="Republic",
        lang="eng",
        section="509d",
        book=None,
        page=None,
        speaker=None,
        text=text,
        source_file="x.txt",
        translator=None,
        edition_year=None,
    )


def _work(*, filenames: tuple[str, ...], locator: str) -> CorpusWork:
    return CorpusWork(
        code="bad",
        title="Broken Work",
        translator="Nobody",
        edition_year="1900",
        filenames=filenames,
        fmt="txt",
        locator=locator,
    )


# ---------- pipeline.parse_dir failure recording ----------


def test_parse_dir_records_per_file_failures(tmp_path: Path, capsys):
    """A file whose parse blows up is skipped (the generator keeps
    yielding for other files) but the failure lands in the per-run
    log and on stderr."""

    (tmp_path / "broken.txt").write_text("any content", encoding="utf-8")
    # A locator that isn't in _SPLITTERS raises KeyError inside
    # parse_file — the catch-all in parse_dir must record it.
    work = _work(filenames=("broken.txt",), locator="no-such-locator")

    pipeline.reset_parse_failures()
    chunks = list(
        pipeline.parse_dir(
            tmp_path,
            lambda name: work if name == "broken.txt" else None,
            label="testcorpus",
        )
    )
    assert chunks == []
    failures = pipeline.parse_failures()
    assert len(failures) == 1
    assert "broken.txt" in failures[0]
    assert "testcorpus" in failures[0]
    assert "broken.txt" in capsys.readouterr().err


def test_structured_parser_zero_chunks_warns(tmp_path: Path, capsys, monkeypatch):
    """Structure-aware splitters (yield-from branches) must warn when
    they emit nothing — unlike _SPLITTERS locators there is no chapter
    fallback."""

    from minerva.corpus import split_ekgwb

    monkeypatch.setattr(split_ekgwb, "split_ekgwb", lambda _raw, _work, _path: iter([]))

    html = tmp_path / "page.html"
    html.write_text("<html><body><div>stub</div></body></html>", encoding="utf-8")
    work = _work(filenames=(html.name,), locator="ekgwb")

    chunks = list(pipeline.parse_file(html, work))
    assert chunks == []
    out = capsys.readouterr()
    assert "0 chunks" in out.out
    assert "ekgwb" in out.out
    assert "structured parser" in out.out


def test_tei_parse_dir_records_per_file_failures(tmp_path: Path, capsys):
    """TEI Perseus bundles share the pipeline failure log so one bad
    XML file doesn't abort the whole Plato/Aristotle ingest."""

    (tmp_path / "good.xml").write_text(
        """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>T</title></titleStmt></fileDesc></teiHeader>
<text><body><div1 type="book" n="1">
<milestone unit="section" n="1a"/>Hello.</div1></body></text></TEI.2>""",
        encoding="utf-8",
    )
    (tmp_path / "bad.xml").write_text("not xml at all", encoding="utf-8")

    pipeline.reset_parse_failures()
    chunks = list(tei.parse_dir(tmp_path, corpus="plato", author="Plato"))
    assert len(chunks) == 1
    failures = pipeline.parse_failures()
    assert len(failures) == 1
    assert "bad.xml" in failures[0]
    assert "plato" in failures[0]
    assert "bad.xml" in capsys.readouterr().err


def test_guarded_parse_file_records_and_isolates(tmp_path: Path, capsys):
    """The shared guard yields whatever ``produce()`` emits before it
    fails, then records the failure instead of propagating — this is
    the isolation contract every dir-walker now uses (issue #45)."""

    def produce():
        yield _chunk("ok-1")
        raise ValueError("boom mid-file")

    pipeline.reset_parse_failures()
    got = list(tei.guarded_parse_file("mycorpus", tmp_path / "f.xml", produce))

    assert [c.chunk_id for c in got] == ["ok-1"]
    failures = pipeline.parse_failures()
    assert len(failures) == 1
    assert "f.xml" in failures[0]
    assert "mycorpus" in failures[0]
    assert "boom mid-file" in failures[0]
    assert "f.xml" in capsys.readouterr().err


def test_osis_parse_dir_isolates_bad_file(tmp_path: Path):
    """A malformed OSIS XML must be recorded and skipped, not abort the
    whole (multi-corpus) ingest (issue #45)."""

    from minerva.sources import osis_bible

    (tmp_path / "bad.xml").write_text("this is not xml", encoding="utf-8")

    pipeline.reset_parse_failures()
    chunks = list(
        osis_bible.parse_dir(
            tmp_path,
            corpus="kjv",
            author="King James Version",
            lang="eng",
            edition_year="1769",
            translator="KJV",
        )
    )
    assert chunks == []
    failures = pipeline.parse_failures()
    assert len(failures) == 1
    assert "bad.xml" in failures[0]
    assert "kjv" in failures[0]


def test_tei_p5_flat_parse_dir_isolates_bad_file(tmp_path: Path):
    """The First1KGreek flat single-work layout must isolate a bad XML
    the same way (issue #45)."""

    from minerva.sources import tei_p5

    (tmp_path / "broken_grc.xml").write_text("<not-valid", encoding="utf-8")

    pipeline.reset_parse_failures()
    chunks = list(tei_p5.parse_dir(tmp_path))
    assert chunks == []
    failures = pipeline.parse_failures()
    assert len(failures) == 1
    assert "broken_grc.xml" in failures[0]


def test_reset_parse_failures_clears_the_log(tmp_path: Path):
    (tmp_path / "broken.txt").write_text("any content", encoding="utf-8")
    work = _work(filenames=("broken.txt",), locator="no-such-locator")

    pipeline.reset_parse_failures()
    list(pipeline.parse_dir(tmp_path, lambda _: work, label="t"))
    assert pipeline.parse_failures()

    pipeline.reset_parse_failures()
    assert pipeline.parse_failures() == []


# ---------- worker result shape ----------


def test_worker_parse_source_ships_pipeline_failures(tmp_path: Path, monkeypatch):
    """The parallel worker resets the pipeline failure log before its
    parse and returns whatever accumulated, so the orchestrator can
    aggregate per-file failures across subprocesses."""

    from minerva.ingest import parallel
    from minerva.ingest.registry import IngestSource

    def fake_parse(path: Path):
        pipeline._PARSE_FAILURES.append("t: failed to parse 'f.pdf' as 'w': boom")
        yield _chunk()

    src = IngestSource("fake", tmp_path, fake_parse)
    monkeypatch.setattr(parallel, "INGEST_SOURCES", (src,))

    shard = tmp_path / "shard.jsonl"
    res = parallel._worker_parse_source("fake", str(tmp_path), str(shard))
    assert res["error"] is None
    assert res["count"] == 1
    assert res["parse_failures"] == ["t: failed to parse 'f.pdf' as 'w': boom"]
    # The shard still contains the chunk that parsed fine.
    assert json.loads(shard.read_text().strip())["chunk_id"] == "ok-1"


def test_worker_parse_source_reports_source_level_error(tmp_path: Path, monkeypatch):
    from minerva.ingest import parallel
    from minerva.ingest.registry import IngestSource

    def exploding_parse(path: Path):
        raise RuntimeError("parser died")
        yield  # pragma: no cover - makes this a generator

    src = IngestSource("fake", tmp_path, exploding_parse)
    monkeypatch.setattr(parallel, "INGEST_SOURCES", (src,))

    res = parallel._worker_parse_source("fake", str(tmp_path), str(tmp_path / "s.jsonl"))
    assert res["error"] == "RuntimeError: parser died"
    assert res["parse_failures"] == []


# ---------- cmd_ingest exit code ----------


def _ingest_args(tmp_path: Path, **overrides) -> argparse.Namespace:
    base: dict = {
        "only": None,
        "allow_partial_corpus": False,
        # The test Namespace carries no per-source path overrides, so
        # every registered source resolves to a missing path — opt in
        # so the upfront missing-path gate doesn't exit 2 before the
        # behavior under test runs.
        "allow_missing_sources": True,
        "output": tmp_path / "chunks.jsonl",
        "db": tmp_path / "index.sqlite",
        "jobs": 1,
        "timing": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_cmd_ingest_writes_partial_output_and_exits_nonzero(tmp_path: Path, monkeypatch, capsys):
    """Sequential path: parse failures don't abort the write — the
    JSONL contains everything that succeeded — but the run exits 1
    with a stderr summary instead of pretending all is well."""

    from minerva.cli import ingest_cmd

    def fake_iter(*, only=None, per_source_timing=False, **paths):
        yield _chunk("good-1")
        pipeline._PARSE_FAILURES.append("hegel: failed to parse 'phg.pdf' as 'phg': boom")
        yield _chunk("good-2")

    monkeypatch.setattr(ingest_cmd, "iter_corpus_chunks", fake_iter)

    args = _ingest_args(tmp_path)
    rc = ingest_cmd.cmd_ingest(args)
    assert rc == 1

    written = [json.loads(line) for line in args.output.read_text().splitlines()]
    assert [c["chunk_id"] for c in written] == ["good-1", "good-2"]

    err = capsys.readouterr().err
    assert "1 failure(s)" in err
    assert "phg.pdf" in err


def test_cmd_ingest_clean_run_exits_zero(tmp_path: Path, monkeypatch, capsys):
    from minerva.cli import ingest_cmd

    def fake_iter(*, only=None, per_source_timing=False, **paths):
        yield _chunk("good-1")

    monkeypatch.setattr(ingest_cmd, "iter_corpus_chunks", fake_iter)
    # A stale failure from a previous run in the same process must not
    # leak into this run's verdict — cmd_ingest resets the log.
    pipeline._PARSE_FAILURES.append("stale: failure from another run")

    rc = ingest_cmd.cmd_ingest(_ingest_args(tmp_path))
    assert rc == 0
    assert "failure" not in capsys.readouterr().err


def test_cmd_ingest_parallel_full_aborts_on_dropped_source(tmp_path: Path, monkeypatch, capsys):
    """Full parallel path: a source-level failure means its corpus is
    absent from the shard list — the write must ABORT (existing
    chunks.jsonl untouched) instead of rewriting the JSONL without
    that corpus, and the run exits non-zero."""

    from minerva.cli import ingest_cmd

    def fake_parallel_ingest(source_ids, paths_by_kwarg, shard_dir, *, jobs, per_source_timing):
        shard = shard_dir / "chunks.plato.jsonl"
        shard.write_text(json.dumps(_chunk("good-1").to_json_dict()) + "\n", encoding="utf-8")
        failures = {"hegel": ["ValueError: bad PDF"]}
        return [shard], 1, {"plato/eng": 1}, failures, ["hegel"]

    monkeypatch.setattr(ingest_cmd, "parallel_ingest", fake_parallel_ingest)

    args = _ingest_args(tmp_path, jobs=2)
    args.output.write_text('{"chunk_id": "pre-existing"}\n', encoding="utf-8")
    rc = ingest_cmd.cmd_ingest(args)
    assert rc == 1

    # The pre-existing output survives byte-for-byte.
    written = [json.loads(line) for line in args.output.read_text().splitlines()]
    assert [c["chunk_id"] for c in written] == ["pre-existing"]

    err = capsys.readouterr().err
    assert "aborting full write" in err
    assert "ingest:hegel" in err
    assert "bad PDF" in err


def test_cmd_ingest_parallel_per_file_failures_still_write(tmp_path: Path, monkeypatch, capsys):
    """Parallel path: per-FILE failures (shard still produced) keep the
    partial-output-plus-exit-1 contract — only whole-source drops
    abort the write."""

    from minerva.cli import ingest_cmd

    def fake_parallel_ingest(source_ids, paths_by_kwarg, shard_dir, *, jobs, per_source_timing):
        shard = shard_dir / "chunks.plato.jsonl"
        shard.write_text(json.dumps(_chunk("good-1").to_json_dict()) + "\n", encoding="utf-8")
        failures = {"plato": ["plato: failed to parse 'r.xml' as 'Republic': boom"]}
        return [shard], 1, {"plato/eng": 1}, failures, []

    monkeypatch.setattr(ingest_cmd, "parallel_ingest", fake_parallel_ingest)

    args = _ingest_args(tmp_path, jobs=2)
    rc = ingest_cmd.cmd_ingest(args)
    assert rc == 1

    written = [json.loads(line) for line in args.output.read_text().splitlines()]
    assert [c["chunk_id"] for c in written] == ["good-1"]
    assert "r.xml" in capsys.readouterr().err


def test_cmd_ingest_missing_source_paths_refused(tmp_path: Path, capsys):
    """A registered source with no data on disk must abort the run
    (exit 2) before anything is written, unless the operator passes
    --allow-missing-sources. The test Namespace carries no source
    paths at all, so every source counts as missing."""

    from minerva.cli import ingest_cmd

    args = _ingest_args(tmp_path, allow_missing_sources=False)
    rc = ingest_cmd.cmd_ingest(args)
    assert rc == 2
    assert not args.output.exists()

    err = capsys.readouterr().err
    assert "SKIPPED" in err
    assert "--allow-missing-sources" in err
