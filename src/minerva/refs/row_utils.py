"""Cross-reference row → JSON shaping."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def xref_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """One ``cross_references`` row joined against ``reference_targets``,
    flattened to the JSON shape the reader expects."""

    payload: dict[str, Any] | None = None
    if row["target_locator_payload"] is not None:
        try:
            payload = json.loads(row["target_locator_payload"])
        except (TypeError, ValueError):
            payload = None
    return {
        "id": row["id"],
        "source_chunk_id": row["source_chunk_id"],
        "source_span_start": row["source_span_start"],
        "source_span_end": row["source_span_end"],
        "source_form": row["source_form_snapshot"],
        "quoted_phrase": row["quoted_phrase"],
        "target": {
            "author": row["canonical_author"],
            "work": row["canonical_work"],
            "in_corpus_work_id": row["in_corpus_work_id"],
            "chunk_id": row["target_chunk_id"],
            "locator": row["target_locator"],
            "locator_payload": payload,
            "sort_key": row["target_sort_key"],
        },
        "reference_type": row["reference_type"],
        "confidence": row["confidence"],
        "source_method": row["source_method"],
        "curator_status": row["curator_status"],
        "note": row["curator_note"],
    }


_AUTHOR_SHORT: dict[str, str] = {
    "Hebrew Bible": "Heb. Bible",
    "New Testament": "NT",
    "Marcus Aurelius": "M. Aurelius",
    "Diogenes of Apollonia": "Diog. Apoll.",
    "Zeno of Elea": "Zeno",
    "Pseudo-Dionysius": "Ps.-Dionys.",
}


def short_author(name: str) -> str:
    if name in _AUTHOR_SHORT:
        return _AUTHOR_SHORT[name]
    if len(name) <= 12:
        return name
    return name[:11] + "…"
