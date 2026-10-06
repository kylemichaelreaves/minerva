"""Per-chunk and per-work cross-reference map queries."""

from __future__ import annotations

import sqlite3
from typing import Any

from ..reader.window import (
    empty_window_response,
    fetch_chunk_ids_in_window,
    parse_window_params,
)
from .filters import parse_filters, status_clause
from .row_utils import xref_row_to_dict


def work_references_map(
    conn: sqlite3.Connection,
    work_id: int,
    query: dict[str, str],
) -> dict[str, Any]:
    """``GET /api/works/:work_id/references_map``."""

    window = parse_window_params(query)
    statuses, min_conf = parse_filters(query)
    status_sql, status_params = status_clause(statuses, min_conf)

    chunk_ids = fetch_chunk_ids_in_window(
        conn,
        work_id,
        window.lang,
        window.from_ord,
        window.limit,
    )
    if not chunk_ids:
        return empty_window_response(work_id, window)
    placeholders = ",".join("?" * len(chunk_ids))
    rows = conn.execute(
        f"SELECT xr.*, "
        f"       rt.canonical_author, rt.canonical_work, "
        f"       rt.in_corpus_work_id "
        f"FROM cross_references xr "
        f"JOIN reference_targets rt ON rt.id = xr.target_id "
        f"WHERE xr.source_chunk_id IN ({placeholders}) "
        f"  AND {status_sql} "
        f"ORDER BY xr.source_chunk_id, xr.confidence DESC, xr.id",
        (*chunk_ids, *status_params),
    ).fetchall()

    by_chunk: dict[str, dict[str, Any]] = {}
    for r in rows:
        d = by_chunk.setdefault(
            r["source_chunk_id"],
            {"count": 0, "top": []},
        )
        d["count"] += 1
        if len(d["top"]) < 3:
            d["top"].append(xref_row_to_dict(r))

    return {
        "work_id": work_id,
        "lang": window.lang,
        "from": window.from_ord,
        "limit": window.limit,
        "by_chunk": by_chunk,
    }
