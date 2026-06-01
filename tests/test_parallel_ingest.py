"""Tests for parallel ingest (Phase 2 of the 2026-05-29 ingestion-
bottleneck remediation plan).

We can't easily exercise ``parallel_ingest`` end-to-end without
spinning up subprocesses that import the registry; that's expensive
under pytest. Instead the tests focus on the deterministic-merge
property of the orchestrator (the bit that matters for correctness)
and the shard-concat helper. End-to-end behavior was smoke-tested
against the real corpus by running ``minerva ingest --jobs 4`` and
diffing byte-for-byte against ``--jobs 1`` — see the commit message.
"""

from __future__ import annotations

import json
from pathlib import Path

from minerva.cli.ingest_cmd import _overlay_shards
from minerva.ingest.parallel import concat_shards


def test_concat_shards_preserves_order_and_count(tmp_path: Path):
    """Concat must stream shards in the given list order, preserving
    every line exactly. ``store.insert_chunks`` assigns the ``ord``
    column from JSONL position, so order is load-bearing."""

    shard_a = tmp_path / "a.jsonl"
    shard_a.write_text(json.dumps({"chunk_id": "a1", "lang": "eng"}) + "\n")
    shard_b = tmp_path / "b.jsonl"
    shard_b.write_text(
        "\n".join(
            [
                json.dumps({"chunk_id": "b1", "lang": "lat"}),
                json.dumps({"chunk_id": "b2", "lang": "lat"}),
            ]
        )
        + "\n"
    )

    out = tmp_path / "merged.jsonl"
    n = concat_shards([shard_a, shard_b], out)
    assert n == 3

    lines = out.read_text().splitlines()
    ids = [json.loads(line)["chunk_id"] for line in lines]
    assert ids == ["a1", "b1", "b2"], "shards must concat in list order"


def test_concat_shards_empty_input(tmp_path: Path):
    """Edge case: zero shards (every source skipped). The output
    file must exist and be empty rather than absent — downstream
    ``insert_chunks`` opens it unconditionally."""

    out = tmp_path / "empty.jsonl"
    n = concat_shards([], out)
    assert n == 0
    assert out.exists()
    assert out.read_text() == ""


def test_concat_shards_handles_shard_with_blank_line(tmp_path: Path):
    """JSONL writers occasionally leave a trailing newline — concat
    should not silently drop or duplicate it."""

    shard = tmp_path / "trailing.jsonl"
    shard.write_text(json.dumps({"chunk_id": "x"}) + "\n")
    out = tmp_path / "merged.jsonl"
    n = concat_shards([shard], out)
    assert n == 1
    assert out.read_text() == shard.read_text()


def test_overlay_shards_replaces_touched_corpora_wholesale(tmp_path: Path):
    """Parallel ``--only`` reingest must match sequential merge_jsonl
    semantics — when a shard contains corpus A with new content-hashed
    chunk_ids, the OLD corpus-A chunk_ids must be dropped, and other
    corpora must be preserved bit-for-bit.

    Fix A of the 2026-05-30 remediation II plan: the prior
    chunk-id-keyed overlay left stale chunk_ids orphaned in the
    JSONL exactly the same way the sequential path did before 1b
    landed (the 720-Essai-chunks bug).
    """

    output = tmp_path / "chunks.jsonl"
    output.write_text(
        "\n".join(
            json.dumps(o)
            for o in [
                {"chunk_id": "old-a1", "corpus": "plato", "lang": "eng", "text": "old"},
                {"chunk_id": "old-a2", "corpus": "plato", "lang": "eng", "text": "old"},
                {"chunk_id": "hegel-1", "corpus": "hegel", "lang": "deu", "text": "phen"},
            ]
        )
        + "\n"
    )

    shard = tmp_path / "plato.shard.jsonl"
    shard.write_text(
        "\n".join(
            json.dumps(o)
            for o in [
                {"chunk_id": "new-b1", "corpus": "plato", "lang": "eng", "text": "fresh"},
                {"chunk_id": "new-b2", "corpus": "plato", "lang": "eng", "text": "fresh"},
            ]
        )
        + "\n"
    )

    total, touched, counts = _overlay_shards([shard], output)
    assert touched == 2  # new chunks added
    assert total == 3    # hegel-1 + new-b1 + new-b2

    rows = [json.loads(line) for line in output.read_text().splitlines() if line]
    ids = {r["chunk_id"] for r in rows}
    assert ids == {"hegel-1", "new-b1", "new-b2"}, "stale old-a* chunks must be dropped"
    assert counts == {"plato/eng": 2, "hegel/deu": 1}


def test_overlay_shards_first_time_writes_fresh(tmp_path: Path):
    """No existing JSONL — should cat shards and report counts."""

    output = tmp_path / "fresh.jsonl"
    shard = tmp_path / "s.jsonl"
    shard.write_text(
        json.dumps({"chunk_id": "x", "corpus": "plato", "lang": "eng"}) + "\n"
    )
    total, touched, counts = _overlay_shards([shard], output)
    assert total == 1 and touched == 1
    assert counts == {"plato/eng": 1}
    assert output.exists()
