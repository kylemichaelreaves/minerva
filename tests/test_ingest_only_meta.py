"""Tests for ``meta.ingest.only`` persistence and clearing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from conftest import make_chunk

from minerva import store
from minerva.cli import ingest_cmd
from minerva.ingest.registry import INGEST_SOURCES


def test_full_ingest_clears_stale_ingest_only_meta(tmp_path: Path, monkeypatch):
    db = tmp_path / "index.sqlite"
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text(json.dumps(make_chunk(chunk_id="p1")) + "\n")

    conn = store.open_db(db)
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('ingest.only', 'plato')")
    conn.commit()
    conn.close()

    def _fake_write(_chunks, output):
        output.write_text(jsonl.read_text())
        return 1, {"plato/eng": 1}

    monkeypatch.setattr(ingest_cmd, "write_jsonl", _fake_write)
    monkeypatch.setattr(ingest_cmd, "record_timing", lambda *a, **k: None)

    args = argparse.Namespace(
        only=None,
        output=jsonl,
        db=db,
        jobs=1,
        timing=False,
        allow_missing_sources=True,
        allow_partial_corpus=False,
        **{s.kwarg_name: None for s in INGEST_SOURCES},
    )
    rc = ingest_cmd.cmd_ingest(args)
    assert rc == 0

    conn = store.open_db(db)
    row = conn.execute("SELECT value FROM meta WHERE key='ingest.only'").fetchone()
    assert row is None


def test_partial_ingest_records_ingest_only_meta(tmp_path: Path, monkeypatch):
    db = tmp_path / "index.sqlite"
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text(json.dumps(make_chunk(chunk_id="p1")) + "\n")
    store.open_db(db).close()

    def _fake_merge(_chunks, output):
        return 1, 1, {"plato/eng": 1}

    monkeypatch.setattr(ingest_cmd, "merge_jsonl", _fake_merge)
    monkeypatch.setattr(ingest_cmd, "record_timing", lambda *a, **k: None)

    args = argparse.Namespace(
        only="plato",
        output=jsonl,
        db=db,
        jobs=1,
        timing=False,
        allow_missing_sources=True,
        allow_partial_corpus=True,
        **{s.kwarg_name: None for s in INGEST_SOURCES},
    )
    rc = ingest_cmd.cmd_ingest(args)
    assert rc == 0

    conn = store.open_db(db)
    row = conn.execute("SELECT value FROM meta WHERE key='ingest.only'").fetchone()
    assert row is not None
    assert row[0] == "plato"
