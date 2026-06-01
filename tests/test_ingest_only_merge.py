"""Tests for ``minerva ingest --only`` JSONL merge semantics (Phase 1b
of the 2026-05-29 ingestion-bottleneck remediation plan).

Partial ingest re-parses just the named sources and overlays their
chunks onto ``chunks.jsonl`` by ``chunk_id``. Every other corpus
must be preserved bit-for-bit.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import make_chunk

from minerva import tei
from minerva.ingest import merge_jsonl, write_jsonl


def _chunk_obj(**overrides) -> tei.Chunk:
    """Build a real ``tei.Chunk`` from ``make_chunk`` overrides so
    ``merge_jsonl`` exercises the ``.to_json_dict()`` path the CLI
    uses. Only the dataclass fields that exist in the make_chunk
    fixture are forwarded; the rest take Chunk's own defaults
    (``citation_system`` was added later than the test fixture, etc.)."""

    d = make_chunk(**overrides)
    kwargs = {
        k: d[k] for k in tei.Chunk.__dataclass_fields__ if k in d
    }
    return tei.Chunk(**kwargs)


def test_merge_jsonl_replaces_touched_corpora_wholesale(tmp_path: Path):
    """A partial re-ingest replaces ALL chunks for the corpora present
    in the new batch — not just the matching chunk_ids.

    Rationale: chunk_ids are content-hashed, so a cleanup pass changes
    both the text AND the chunk_id of every affected chunk. The
    previous "overlay by chunk_id" behavior left stale old-id chunks
    orphaned in the JSONL alongside the new ones. The 2026-05-29
    Essai re-ingest from a cleaner PDF source surfaced this: 720
    garbage chunks from the prior EPUB source persisted because their
    chunk_ids didn't collide with the new PDF-derived chunks.
    """

    out = tmp_path / "chunks.jsonl"
    # Seed two chunks from corpus A.
    seeded = [
        _chunk_obj(chunk_id="a1", corpus="plato", text="Original A1 text."),
        _chunk_obj(chunk_id="a2", corpus="plato", text="Original A2 text."),
    ]
    write_jsonl(seeded, out)

    # Re-ingest corpus A with completely different chunk_ids (simulates
    # a re-source / re-clean that changed the content-hash of every
    # chunk). The new batch is the COMPLETE new state for corpus A;
    # old chunks (a1, a2) should NOT survive.
    new = [
        _chunk_obj(chunk_id="b1", corpus="plato", text="Fresh chunk 1."),
        _chunk_obj(chunk_id="b2", corpus="plato", text="Fresh chunk 2."),
    ]
    total, touched, _counts = merge_jsonl(iter(new), out)
    assert total == 2, "old a1/a2 should be replaced wholesale; only b1/b2 remain"
    assert touched == 2

    rows = [json.loads(line) for line in out.read_text().splitlines() if line]
    by_id = {r["chunk_id"]: r for r in rows}
    assert set(by_id) == {"b1", "b2"}, "stale chunks a1/a2 dropped"
    assert by_id["b1"]["text"] == "Fresh chunk 1."
    assert by_id["b2"]["text"] == "Fresh chunk 2."


def test_merge_jsonl_preserves_other_corpora(tmp_path: Path):
    """The core property: a partial re-ingest of corpus B must NOT
    touch corpus A's chunks even when chunk_ids differ."""

    out = tmp_path / "chunks.jsonl"
    seeded = [
        _chunk_obj(chunk_id="hegel-1", corpus="hegel", lang="deu", text="Phänomenologie."),
        _chunk_obj(chunk_id="kant-1", corpus="kant", lang="deu", text="Kritik."),
    ]
    write_jsonl(seeded, out)

    # Now re-ingest just Kant.
    new = [
        _chunk_obj(chunk_id="kant-1", corpus="kant", lang="deu", text="REVISED Kritik."),
        _chunk_obj(chunk_id="kant-2", corpus="kant", lang="deu", text="Second Kant chunk."),
    ]
    total, _touched, counts = merge_jsonl(iter(new), out)
    assert total == 3
    assert counts == {"hegel/deu": 1, "kant/deu": 2}

    rows = [json.loads(line) for line in out.read_text().splitlines() if line]
    by_id = {r["chunk_id"]: r for r in rows}
    assert by_id["hegel-1"]["text"] == "Phänomenologie.", "Hegel chunk preserved"
    assert by_id["kant-1"]["text"] == "REVISED Kritik."


def test_merge_jsonl_writes_fresh_when_no_existing(tmp_path: Path):
    """First-time ingest with no ``chunks.jsonl`` shouldn't error;
    the merge degrades to a regular write."""

    out = tmp_path / "first-time.jsonl"
    assert not out.exists()
    chunks = [_chunk_obj(chunk_id="x", text="hello")]
    total, touched, counts = merge_jsonl(iter(chunks), out)
    assert total == 1
    assert touched == 1
    assert counts == {"plato/eng": 1}
    assert out.exists()
