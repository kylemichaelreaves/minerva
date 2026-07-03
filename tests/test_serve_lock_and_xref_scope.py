"""Tests for serve-lock guard and incremental xref scoping."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from conftest import make_chunk

from minerva import serve_lock
from minerva.cli.index_cmd import cmd_index


def _run_index(
    db: Path,
    jsonl: Path,
    *,
    reset: bool = False,
    incremental: bool = False,
    corpora: str = "",
) -> int:
    args = argparse.Namespace(
        db=db,
        input=jsonl,
        reset=reset,
        incremental=incremental,
        corpora=corpora,
        from_ingest_only=False,
    )
    return cmd_index(args)


def test_index_reset_refused_while_server_running(tmp_path: Path):
    db = tmp_path / "index.sqlite"
    jsonl = tmp_path / "chunks.jsonl"
    jsonl.write_text(json.dumps(make_chunk(chunk_id="p1", corpus="plato")) + "\n")

    serve_lock.serve_lock_path(db).write_text("1\n127.0.0.1\n8000\n", encoding="utf-8")
    try:
        rc = _run_index(db, jsonl, reset=True)
    finally:
        serve_lock.clear_serve_lock(db)

    assert rc == 2
