"""Curator review queue queries."""

from __future__ import annotations

import sqlite3
from typing import Any

from ..errors import BadRequestError
from .constants import SOURCE_AUTHOR
from .filters import parse_limit_offset
from .row_utils import xref_row_to_dict


def review_queue(
    conn: sqlite3.Connection,
    query: dict[str, str],
) -> dict[str, Any]:
    """``GET /api/references/review_queue``.

    Lists the curator triage queue — every row with
    ``curator_status='auto'``, lowest-confidence first so the
    reviewer hits the borderline cases first. Joined with source
    chunk + work metadata so the reviewer can read the source text
    on-screen without a second fetch.

    Query params:

    - ``limit`` (default 50, max 200) — page size.
    - ``offset`` (default 0).
    - ``source_author`` (optional) — narrow to one author's auto-rows.
    - ``min_confidence`` / ``max_confidence`` (optional) — band filter.
    - ``reference_type`` (optional).

    A normal session iterates `offset=0, 50, 100, …` until the
    response carries fewer rows than `limit`.
    """

    limit, offset = parse_limit_offset(query, default_limit=50, max_limit=200)

    clauses: list[str] = ["xr.curator_status = 'auto'"]
    params: list[Any] = []
    if query.get("source_author"):
        clauses.append(f"{SOURCE_AUTHOR} = ?")
        params.append(query["source_author"])
    if query.get("reference_type"):
        clauses.append("xr.reference_type = ?")
        params.append(query["reference_type"])
    if query.get("min_confidence"):
        try:
            params.append(float(query["min_confidence"]))
            clauses.append("xr.confidence >= ?")
        except ValueError:
            raise BadRequestError("invalid 'min_confidence' query param",
            ) from None
    if query.get("max_confidence"):
        try:
            params.append(float(query["max_confidence"]))
            clauses.append("xr.confidence <= ?")
        except ValueError:
            raise BadRequestError("invalid 'max_confidence' query param",
            ) from None

    where = "WHERE " + " AND ".join(clauses)
    sql = (
        f"SELECT xr.*, "
        f"       rt.canonical_author, rt.canonical_work, "
        f"       rt.in_corpus_work_id, "
        f"       {SOURCE_AUTHOR} AS _src_author, "
        f"       src_work.title AS _src_work, "
        f"       c.section AS _src_section, "
        f"       c.text AS _src_text "
        f"FROM cross_references xr "
        f"JOIN reference_targets rt ON rt.id = xr.target_id "
        f"JOIN chunks c ON c.chunk_id = xr.source_chunk_id "
        f"LEFT JOIN editions e ON e.id = c.edition_id "
        f"LEFT JOIN translations t ON t.id = c.translation_id "
        f"LEFT JOIN works src_work "
        f"       ON src_work.id = COALESCE(e.work_id, t.work_id) "
        f"{where} "
        # Lowest-confidence first — those are the rows where curator
        # judgment most needs to be paid in. Tie-break by id so paging
        # is stable.
        f"ORDER BY xr.confidence ASC, xr.id ASC "
        f"LIMIT ? OFFSET ?"
    )
    params.extend([limit, offset])

    rows = conn.execute(sql, params).fetchall()
    # Cheap total-pending count so the UI can show "27 of 4,050 left"
    # without paging every row. Recomputed every request; the auto
    # set is small (≤10k) so a COUNT is fine.
    total_pending = conn.execute(
        "SELECT COUNT(*) FROM cross_references WHERE curator_status='auto'"
    ).fetchone()[0]

    refs: list[dict[str, Any]] = []
    for r in rows:
        d = xref_row_to_dict(r)
        d["source"] = {
            "author": r["_src_author"],
            "work": r["_src_work"],
            "section": r["_src_section"],
            "text": r["_src_text"],
        }
        refs.append(d)

    return {
        "limit": limit,
        "offset": offset,
        "total_pending": total_pending,
        "references": refs,
    }
