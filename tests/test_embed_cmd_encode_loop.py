"""End-to-end tests for `cmd_embed`'s encode loop.

`test_embed_incremental.py` covers the *store helpers* the loop selects
its rows from (`iter_chunks_without_embeddings` and friends) and
`test_embed_lang_empty.py` covers one early exit, but nothing exercised
the loop itself — the batching, the periodic commit, the final drain, or
that rows actually land in `embeddings`. It was the least-covered module
in `src/minerva/cli` at 41%.

Written while fixing the `cmd_embed` connection leak for #246: the leak
fix wraps the loop in `with closing(...)`, and touching ~90 lines of
untested code is how a formatting-shaped change turns into a regression
nobody notices.

The embedder is faked throughout — a real one would download a model.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pytest
from conftest import make_chunk  # type: ignore[import-not-found]

from minerva import store
from minerva.cli import embed_cmd


class _CountingEmbedder:
    """Returns deterministic unit vectors and records each batch it saw.

    The recorded shapes are what let a test distinguish "one batch of 12"
    from "twelve batches of 1" — i.e. whether `--batch-size` is honoured.
    """

    dim = 4

    def __init__(self) -> None:
        self.batches: list[int] = []
        self.encode_batch_sizes: list[int] = []

    def encode(self, texts, batch_size=32):  # type: ignore[no-untyped-def]
        self.batches.append(len(texts))
        self.encode_batch_sizes.append(batch_size)
        return [np.full((self.dim,), i + 1, dtype=np.float32) for i in range(len(texts))]


def _seed(tmp_path: Path, n: int, *, lang: str = "eng") -> Path:
    db = tmp_path / "embed.sqlite"
    jsonl = tmp_path / "seed.jsonl"
    jsonl.write_text(
        "\n".join(
            json.dumps(make_chunk(chunk_id=f"c{i}", lang=lang, text=f"Chunk number {i}."))
            for i in range(n)
        )
    )
    conn = store.open_db(db)
    store.insert_chunks(conn, jsonl)
    conn.close()
    return db


@pytest.fixture
def embedder(monkeypatch: pytest.MonkeyPatch) -> _CountingEmbedder:
    fake = _CountingEmbedder()
    monkeypatch.setattr(embed_cmd.embed, "Embedder", lambda _model: fake)
    monkeypatch.setattr(embed_cmd, "record_timing", lambda *a, **k: None)
    return fake


def _args(db: Path, **over: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "db": db,
        "model": "fake-model",
        "lang": "any",
        "all": False,
        "batch_size": 64,
        "encode_batch_size": 32,
        "timing": False,
    }
    base.update(over)
    return argparse.Namespace(**base)


def _embedded_ids(db: Path) -> list[str]:
    conn = store.open_db(db)
    try:
        rows = conn.execute("SELECT chunk_id FROM embeddings ORDER BY chunk_id").fetchall()
    finally:
        conn.close()
    return [r["chunk_id"] for r in rows]


def test_writes_an_embedding_row_for_every_pending_chunk(tmp_path, embedder, capsys):
    db = _seed(tmp_path, 3)

    assert embed_cmd.cmd_embed(_args(db)) == 0

    out = capsys.readouterr().out
    assert _embedded_ids(db) == ["c0", "c1", "c2"]
    assert "Embedding 3 missing chunks" in out
    assert "Done." in out


def test_batch_size_controls_how_many_texts_reach_the_encoder_at_once(tmp_path, embedder, capsys):
    db = _seed(tmp_path, 5)

    assert embed_cmd.cmd_embed(_args(db, batch_size=2)) == 0
    capsys.readouterr()

    # 5 rows at batch=2 → two full slabs, then the final drain of 1.
    assert embedder.batches == [2, 2, 1]
    assert len(_embedded_ids(db)) == 5


def test_encode_batch_size_is_passed_through_to_the_encoder(tmp_path, embedder, capsys):
    db = _seed(tmp_path, 2)

    assert embed_cmd.cmd_embed(_args(db, encode_batch_size=8)) == 0
    capsys.readouterr()

    assert embedder.encode_batch_sizes == [8]


def test_periodic_commit_fires_and_prints_progress_every_ten_batches(tmp_path, embedder, capsys):
    """`commit_every = 10` is expressed as `(written // batch) % 10 == 0`,
    so at batch=1 the branch fires on the 10th and 20th row. Twelve rows
    reach it once — the only shape short of 640 chunks that does."""

    db = _seed(tmp_path, 12)

    assert embed_cmd.cmd_embed(_args(db, batch_size=1)) == 0

    out = capsys.readouterr().out
    # One mid-run progress line at 10/12, plus the final drain's 12/12.
    assert "  ... 10/12" in out
    assert "  ... 12/12" in out
    assert len(_embedded_ids(db)) == 12


def test_every_row_is_committed_when_the_final_drain_is_empty(tmp_path, embedder, capsys):
    """Regression: `total` an exact multiple of `batch` lost the tail.

    Every row is flushed inside the loop, so `pending` is empty at the
    drain and `flush(final=True)` returned early — without the commit and
    cache invalidation `upsert_embeddings` defers to "once at the end".
    Rows written since the last periodic commit were rolled back when the
    connection closed.

    `total == batch` is the worst shape: the whole run is discarded. Found
    while covering this loop for #246; reproduces on the pre-fix code.
    """

    db = _seed(tmp_path, 4)

    assert embed_cmd.cmd_embed(_args(db, batch_size=4)) == 0
    capsys.readouterr()

    # One slab of 4, nothing left to drain — and all 4 rows persisted.
    assert embedder.batches == [4]
    assert _embedded_ids(db) == ["c0", "c1", "c2", "c3"]


def test_incremental_run_skips_chunks_already_embedded(tmp_path, embedder, capsys):
    db = _seed(tmp_path, 3)
    assert embed_cmd.cmd_embed(_args(db)) == 0
    capsys.readouterr()
    embedder.batches.clear()

    # Second run: everything is already embedded under this model, so the
    # loop is never entered and the handler takes the `total == 0` exit.
    assert embed_cmd.cmd_embed(_args(db)) == 0

    out = capsys.readouterr().out
    assert "All chunks already embedded with fake-model" in out
    assert embedder.batches == []


def test_all_forces_a_re_encode_of_already_embedded_chunks(tmp_path, embedder, capsys):
    db = _seed(tmp_path, 3)
    assert embed_cmd.cmd_embed(_args(db)) == 0
    capsys.readouterr()
    embedder.batches.clear()

    assert embed_cmd.cmd_embed(_args(db, all=True)) == 0

    out = capsys.readouterr().out
    assert "Embedding 3 all chunks" in out
    assert embedder.batches == [3]


def test_all_on_an_empty_index_says_to_run_index_first(tmp_path, embedder, capsys):
    db = tmp_path / "empty.sqlite"
    store.open_db(db).close()

    assert embed_cmd.cmd_embed(_args(db, all=True)) == 2

    assert "No chunks present" in capsys.readouterr().err


def test_timing_lines_are_printed_when_requested(tmp_path, embedder, capsys):
    db = _seed(tmp_path, 2)

    assert embed_cmd.cmd_embed(_args(db, timing=True)) == 0

    assert "timing: embed" in capsys.readouterr().err


def test_timing_line_is_printed_on_the_nothing_to_do_exit(tmp_path, embedder, capsys):
    db = _seed(tmp_path, 2)
    assert embed_cmd.cmd_embed(_args(db)) == 0
    capsys.readouterr()

    assert embed_cmd.cmd_embed(_args(db, timing=True)) == 0

    assert "timing: embed" in capsys.readouterr().err


def test_unavailable_embeddings_backend_exits_two(tmp_path, monkeypatch, capsys):
    db = _seed(tmp_path, 1)

    def boom(_model):  # type: ignore[no-untyped-def]
        raise embed_cmd.embed.EmbeddingsUnavailable("sentence-transformers not installed")

    monkeypatch.setattr(embed_cmd.embed, "Embedder", boom)

    assert embed_cmd.cmd_embed(_args(db)) == 2

    assert "sentence-transformers not installed" in capsys.readouterr().err
