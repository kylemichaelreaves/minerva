"""Regression: ``embed --all --lang`` on an empty language slice."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from conftest import make_chunk

from minerva import store
from minerva.cli import embed_cmd


def test_embed_all_lang_reports_populated_db_when_lang_missing(
    tmp_path: Path, monkeypatch, capsys,
):
    db = tmp_path / "embed.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(
        json.dumps(make_chunk(chunk_id="e1", lang="eng", text="English only."))
        + "\n"
    )
    conn = store.open_db(db)
    store.insert_chunks(conn, jsonl)
    conn.close()

    class _FakeEmbedder:
        dim = 4

        def encode(self, texts, batch_size=32):
            return []

    monkeypatch.setattr(embed_cmd.embed, "Embedder", lambda _model: _FakeEmbedder())
    monkeypatch.setattr(embed_cmd, "record_timing", lambda *a, **k: None)

    args = argparse.Namespace(
        db=db,
        model="fake-model",
        lang="grc",
        all=True,
        batch_size=64,
        encode_batch_size=32,
        timing=False,
    )
    rc = embed_cmd.cmd_embed(args)
    err = capsys.readouterr().err

    assert rc == 2
    assert "No grc chunks in the index" in err
    assert "1 chunks of other languages present" in err
