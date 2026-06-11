"""Corpus-wide cross-reference list and source/target author queries."""

from __future__ import annotations

import sqlite3
from typing import Any

from .filters import parse_filters, parse_limit_offset, status_clause
from .row_utils import xref_row_to_dict


def references_list(
    conn: sqlite3.Connection,
    query: dict[str, str],
) -> dict[str, Any]:
    """``GET /api/references``."""

    limit, offset = parse_limit_offset(query, default_limit=100, max_limit=500)

    statuses, min_conf = parse_filters(query)
    status_sql, status_params = status_clause(statuses, min_conf)

    clauses: list[str] = [status_sql]
    params: list[Any] = list(status_params)
    if query.get("source_author"):
        clauses.append("src_work.author = ?")
        params.append(query["source_author"])
    if query.get("target_author"):
        clauses.append("rt.canonical_author = ?")
        params.append(query["target_author"])
    if query.get("target_work"):
        clauses.append("rt.canonical_work = ?")
        params.append(query["target_work"])
    if query.get("reference_type"):
        clauses.append("xr.reference_type = ?")
        params.append(query["reference_type"])

    where = "WHERE " + " AND ".join(clauses)

    base_from = (
        "FROM cross_references xr "
        "JOIN reference_targets rt ON rt.id = xr.target_id "
        "JOIN chunks c ON c.chunk_id = xr.source_chunk_id "
        "LEFT JOIN editions e ON e.id = c.edition_id "
        "LEFT JOIN translations t ON t.id = c.translation_id "
        "LEFT JOIN works src_work "
        "       ON src_work.id = COALESCE(e.work_id, t.work_id) "
    )

    sql = (
        f"SELECT xr.*, "
        f"       rt.canonical_author, rt.canonical_work, "
        f"       rt.in_corpus_work_id, "
        f"       src_work.author AS _src_author, "
        f"       src_work.title AS _src_work, "
        f"       c.section AS _src_section "
        f"{base_from}"
        f"{where} "
        f"ORDER BY xr.id "
        f"LIMIT ? OFFSET ?"
    )
    page_params = [*params, limit, offset]

    count_sql = f"SELECT COUNT(*) {base_from}{where}"

    rows = conn.execute(sql, page_params).fetchall()
    total = conn.execute(count_sql, params).fetchone()[0]

    refs: list[dict[str, Any]] = []
    for r in rows:
        d = xref_row_to_dict(r)
        d["source"] = {
            "author": r["_src_author"],
            "work": r["_src_work"],
            "section": r["_src_section"],
        }
        refs.append(d)

    return {
        "limit": limit,
        "offset": offset,
        "total": int(total),
        "filters": {
            "source_author": query.get("source_author"),
            "target_author": query.get("target_author"),
            "target_work": query.get("target_work"),
            "reference_type": query.get("reference_type"),
        },
        "references": refs,
    }


def references_sources(
    conn: sqlite3.Connection,
    query: dict[str, str] | None = None,
) -> dict[str, Any]:
    """``GET /api/references/sources``."""

    from ..author_ordering import author_sort_key

    if query is None:
        query = {}
    statuses, min_conf = parse_filters(query)
    status_sql, status_params = status_clause(statuses, min_conf)

    src_sql = (
        "SELECT DISTINCT src_work.author "
        "FROM cross_references xr "
        "JOIN chunks c ON c.chunk_id = xr.source_chunk_id "
        "LEFT JOIN editions e ON e.id = c.edition_id "
        "LEFT JOIN translations t ON t.id = c.translation_id "
        "LEFT JOIN works src_work "
        "       ON src_work.id = COALESCE(e.work_id, t.work_id) "
        f"WHERE {status_sql} AND src_work.author IS NOT NULL"
    )
    tgt_sql = (
        "SELECT DISTINCT rt.canonical_author "
        "FROM cross_references xr "
        "JOIN reference_targets rt ON rt.id = xr.target_id "
        f"WHERE {status_sql} AND rt.canonical_author IS NOT NULL"
    )

    sources = [row[0]
               for row in conn.execute(src_sql, status_params).fetchall()]
    targets = [row[0] for row in conn.execute(tgt_sql, status_params).fetchall()]

    sources.sort(key=author_sort_key)
    targets.sort()

    return {
        "sources": sources,
        "targets": targets,
    }
