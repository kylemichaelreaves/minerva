"""Drive TEI ingestion for configured corpora and emit JSONL."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path

from .. import tei
from ..paths import REPO_ROOT
from .registry import (
    INGEST_SOURCES,
    build_iter_corpus_kwargs,
    iter_registered_chunks,
)

DEFAULT_OUTPUT = REPO_ROOT / "data" / "chunks.jsonl"

# The legacy ``DEFAULT_<SOURCE>_DIR`` constants (injected via a
# hand-maintained globals() map that had already drifted from the
# registry) are gone — use ``registry.default_paths_by_param()`` or
# ``IngestSource.default_path`` instead.


def iter_corpus_chunks(
    *,
    only: frozenset[str] | None = None,
    per_source_timing: bool = False,
    allow_missing_sources: bool = False,
    run_log: object | None = None,
    **paths: Path | None,
) -> Iterator[tei.Chunk]:
    """Yield chunks from all configured corpora whose paths exist.

    ``only`` restricts to the named ``IngestSource.id``s (Phase 1b);
    ``per_source_timing`` prints a stderr ``timing: ingest:<id>``
    line per source (Phase 0). Both flags forward to
    ``iter_registered_chunks``.
    """

    kwargs = build_iter_corpus_kwargs(**paths)
    yield from iter_registered_chunks(
        kwargs,
        only=only,
        per_source_timing=per_source_timing,
        allow_missing_sources=allow_missing_sources,
        run_log=run_log,
    )


def write_jsonl(chunks: Iterable[tei.Chunk], output_path: Path) -> tuple[int, dict[str, int]]:
    """Write ``chunks`` to ``output_path`` via temp-file + atomic rename.

    ``chunks`` is usually a lazy parser iterator, so any exception it
    raises lands mid-write — writing straight to ``output_path`` would
    leave a truncated ``chunks.jsonl`` that the next ``index --reset``
    happily loads, mass-deleting every chunk past the truncation point.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    counts: dict[str, int] = {}
    n = 0
    try:
        with tmp_path.open("w", encoding="utf-8") as fh:
            for ch in chunks:
                fh.write(json.dumps(ch.to_json_dict(), ensure_ascii=False) + "\n")
                n += 1
                key = f"{ch.corpus}/{ch.lang}"
                counts[key] = counts.get(key, 0) + 1
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    tmp_path.replace(output_path)
    return n, counts


def merge_jsonl(
    new_chunks: Iterable[tei.Chunk],
    output_path: Path,
) -> tuple[int, int, dict[str, int]]:
    """Overlay freshly-parsed ``new_chunks`` onto an existing
    ``chunks.jsonl``, replacing all rows for the corpora present in
    the new batch.

    Phase 1b of the 2026-05-29 remediation plan: ``minerva ingest
    --only <id>`` should re-parse just the named sources without
    discarding every other corpus's chunks. Semantics:

    * Stream the new chunks once to discover which ``corpus`` values
      they span (the "touched" corpora).
    * Read existing rows; keep only those whose ``corpus`` is NOT in
      the touched set — that's the "preserved" pile.
    * Write preserved + new together. Chunks for the touched corpora
      are replaced wholesale: old IDs that aren't in the new batch
      get dropped (they correspond to stale text that's been re-OCR'd
      or recleaned).

    Why corpus-level rather than chunk-id-level: chunk_ids are
    content-hashed, so a cleanup pass changes both the text AND the
    chunk_id of every affected chunk. Per-chunk-id overlay would
    leave the old garbage chunks orphaned in the JSONL forever (this
    is exactly the bug that left 720 stale EPUB-era ``Essai`` chunks
    in the corpus after the PDF-source re-ingest on 2026-05-29).

    Returns ``(total_after_merge, touched_count, counts_by_corpus_lang)``.
    """

    if not output_path.exists():
        n, counts = write_jsonl(new_chunks, output_path)
        return n, n, counts

    # Materialise the new batch so we can scan it twice (once to find
    # touched corpora, once to write). Memory is bounded by the
    # ``--only`` selection — at worst a single full re-ingest's worth
    # (~10 MB-1 GB), which is acceptable for the offline CLI.
    new_batch = [ch.to_json_dict() for ch in new_chunks]
    touched_corpora = {d.get("corpus") for d in new_batch if d.get("corpus")}
    return _merge_dicts_to_jsonl(new_batch, touched_corpora, output_path)


def _merge_dicts_to_jsonl(
    new_batch: list[dict],
    touched_corpora: set[str | None],
    output_path: Path,
) -> tuple[int, int, dict[str, int]]:
    """Stream the merge: write preserved rows from the existing JSONL
    and the new batch into a sibling temp file, then atomic-rename
    onto ``output_path``.

    Phase 1b Fix B of the 2026-05-30 remediation II plan — the prior
    implementation materialised the entire preserved set in memory
    (`preserved.append(obj)`), which for a re-ingest of corpus B
    against a 50K-chunk JSONL held ~250 MB unnecessarily. The temp-
    file + atomic-rename pattern keeps RAM flat: only the new batch
    (the small, ``--only``-scoped side) stays resident.

    Pre-condition: ``output_path`` exists (caller's responsibility).
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    counts: dict[str, int] = {}
    preserved = 0
    with tmp_path.open("w", encoding="utf-8") as fh:
        for obj in load_jsonl(output_path):
            if obj.get("corpus") in touched_corpora:
                continue
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
            preserved += 1
            key = f"{obj.get('corpus')}/{obj.get('lang')}"
            counts[key] = counts.get(key, 0) + 1
        for obj in new_batch:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
            key = f"{obj.get('corpus')}/{obj.get('lang')}"
            counts[key] = counts.get(key, 0) + 1
    tmp_path.replace(output_path)
    return preserved + len(new_batch), len(new_batch), counts


def load_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


__all__ = [
    "DEFAULT_OUTPUT",
    "INGEST_SOURCES",
    "REPO_ROOT",
    "_merge_dicts_to_jsonl",
    "iter_corpus_chunks",
    "load_jsonl",
    "merge_jsonl",
    "write_jsonl",
]
