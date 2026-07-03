"""Validate ingested chunk totals against manifest-declared ranges.

``data/authors/manifest.yaml`` carries an optional top-level
``expected_chunks`` map keyed by corpus id::

    expected_chunks:
      theognis:
        min: 1214
        max: 1861

Counts are read from ``chunks_full.corpus``, which stores
``LOWER(works.author)`` (e.g. ``hebrew bible``), not the corpus slug
(``hebrew_mt``). Each manifest author row's ``display_name`` is
lower-cased and summed for its ``corpus_id``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "data" / "index.sqlite"
MANIFEST_PATH = REPO_ROOT / "data" / "authors" / "manifest.yaml"


def _load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


load_manifest = _load_manifest


def corpus_db_labels(manifest: dict[str, Any], corpus_id: str) -> tuple[str, ...]:
    """Lower-case author labels stored in ``chunks_full.corpus``."""

    return tuple(
        str(a["display_name"]).lower()
        for a in manifest.get("authors") or []
        if a.get("corpus_id") == corpus_id
    )


def expected_ranges(manifest: dict[str, Any]) -> dict[str, tuple[int, int]]:
    raw = manifest.get("expected_chunks") or {}
    out: dict[str, tuple[int, int]] = {}
    for corpus_id, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        lo, hi = spec.get("min"), spec.get("max")
        if lo is None or hi is None:
            continue
        out[str(corpus_id)] = (int(lo), int(hi))
    return out


def count_chunks_for_corpus(
    conn: sqlite3.Connection,
    labels: tuple[str, ...],
) -> int:
    if not labels:
        return 0
    placeholders = ",".join("?" for _ in labels)
    row = conn.execute(
        f"SELECT COUNT(*) FROM chunks_full WHERE corpus IN ({placeholders})",
        labels,
    ).fetchone()
    return int(row[0])


def validate_chunk_counts(
    conn: sqlite3.Connection,
    manifest: dict[str, Any],
    *,
    corpus_ids: tuple[str, ...] | None = None,
) -> list[str]:
    """Return human-readable errors for out-of-range corpora."""

    ranges = expected_ranges(manifest)
    if not ranges:
        return ["expected_chunks missing or empty in manifest.yaml"]

    targets = corpus_ids or tuple(sorted(ranges))
    errors: list[str] = []
    for corpus_id in targets:
        spec = ranges.get(corpus_id)
        if spec is None:
            continue
        lo, hi = spec
        labels = corpus_db_labels(manifest, corpus_id)
        if not labels:
            errors.append(
                f"{corpus_id}: no manifest author rows — cannot map DB labels"
            )
            continue
        count = count_chunks_for_corpus(conn, labels)
        if count < lo:
            errors.append(
                f"{corpus_id}: {count:,} chunks below minimum {lo:,} "
                f"(labels={labels!r})"
            )
        elif count > hi:
            errors.append(
                f"{corpus_id}: {count:,} chunks above maximum {hi:,} "
                f"(labels={labels!r})"
            )
    return errors


def chunk_count_report(
    conn: sqlite3.Connection,
    manifest: dict[str, Any],
) -> list[tuple[str, int, int, int, str]]:
    """Return ``(corpus_id, count, min, max, status)`` rows for reporting."""

    rows: list[tuple[str, int, int, int, str]] = []
    for corpus_id, (lo, hi) in sorted(expected_ranges(manifest).items()):
        labels = corpus_db_labels(manifest, corpus_id)
        count = count_chunks_for_corpus(conn, labels)
        if count < lo:
            status = "below_min"
        elif count > hi:
            status = "above_max"
        else:
            status = "ok"
        rows.append((corpus_id, count, lo, hi, status))
    return rows
