#!/usr/bin/env -S uv run python
"""Dump dashboard-design aggregates as JSON.

Produces a single JSON document covering every aggregate a
cross-references dashboard might want to chart:

* totals (corpus-wide row count, distinct authors, edges)
* per_source_author    — outgoing-degree table, chronologically ordered
* per_target_author    — incoming-degree table (includes out-of-corpus)
* source_target_matrix — N×M counts (source × target)
* reference_type_by_source
* source_method_by_source
* curator_status_by_source
* hub_authority         — (outgoing, incoming) per in-corpus author

Filter shape matches the default /api/references visibility:
  curator_status IN ('approved','manual')
  OR (curator_status='auto' AND confidence>=0.8)

Requires a populated ``data/index.sqlite``. Regenerate the committed
``docs/dashboard_aggregates.json`` after cross-reference work::

    uv run python scripts/dashboard_aggregates.py > docs/dashboard_aggregates.json

Role: workflow
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from minerva.author_ordering import AUTHOR_ORDINAL

DB = Path(__file__).resolve().parents[1] / "data" / "index.sqlite"

VISIBLE_CLAUSE = (
    "(xr.curator_status IN ('approved','manual') "
    " OR (xr.curator_status = 'auto' AND xr.confidence >= 0.8))"
)


def author_ordinal(name: str | None) -> int:
    if name is None:
        return 10_000
    return AUTHOR_ORDINAL.get(name, 10_000)


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    base_from = (
        "FROM cross_references xr "
        "JOIN reference_targets rt ON rt.id = xr.target_id "
        "JOIN chunks c ON c.chunk_id = xr.source_chunk_id "
        "LEFT JOIN editions e ON e.id = c.edition_id "
        "LEFT JOIN translations t ON t.id = c.translation_id "
        "LEFT JOIN works src_work "
        "       ON src_work.id = COALESCE(e.work_id, t.work_id) "
        f"WHERE {VISIBLE_CLAUSE}"
    )

    total = conn.execute(f"SELECT COUNT(*) {base_from}").fetchone()[0]

    # Per source author (outgoing degree).
    per_source: list[dict[str, Any]] = []
    for row in conn.execute(
        f"SELECT src_work.author AS author, COUNT(*) AS n "
        f"{base_from} AND src_work.author IS NOT NULL "
        "GROUP BY src_work.author ORDER BY n DESC"
    ):
        per_source.append(
            {
                "author": row["author"],
                "outgoing": row["n"],
                "ordinal": author_ordinal(row["author"]),
            }
        )

    # Set of authors who appear in the corpus's works table — used to
    # tag targets as in-corpus vs out-of-corpus. (Note: rt.in_corpus_work_id
    # is per-target-work; an author can be in-corpus but be referenced
    # at the bare-author level, with no in_corpus_work_id resolved.)
    in_corpus_authors = {
        row[0] for row in conn.execute("SELECT DISTINCT author FROM works").fetchall() if row[0]
    }

    # Per target author (incoming degree, including out-of-corpus).
    per_target: list[dict[str, Any]] = []
    for row in conn.execute(
        f"SELECT rt.canonical_author AS author, COUNT(*) AS n "
        f"{base_from} GROUP BY rt.canonical_author ORDER BY n DESC"
    ):
        per_target.append(
            {
                "author": row["author"],
                "incoming": row["n"],
                "in_corpus": row["author"] in in_corpus_authors,
                "ordinal": author_ordinal(row["author"]),
            }
        )

    # Source × Target matrix. Emit only non-zero cells; the consumer
    # can densify if it needs the full grid.
    matrix: list[dict[str, Any]] = []
    for row in conn.execute(
        f"SELECT src_work.author AS src, rt.canonical_author AS tgt, COUNT(*) AS n "
        f"{base_from} AND src_work.author IS NOT NULL "
        "GROUP BY src_work.author, rt.canonical_author ORDER BY n DESC"
    ):
        matrix.append({"source": row["src"], "target": row["tgt"], "n": row["n"]})

    # Reference-type breakdown per source.
    ref_type_by_src: dict[str, dict[str, int]] = defaultdict(dict)
    for row in conn.execute(
        f"SELECT src_work.author AS author, xr.reference_type AS rt, COUNT(*) AS n "
        f"{base_from} AND src_work.author IS NOT NULL "
        "GROUP BY src_work.author, xr.reference_type"
    ):
        ref_type_by_src[row["author"]][row["rt"]] = row["n"]

    # Source-method (verification provenance) per source.
    src_method_by_src: dict[str, dict[str, int]] = defaultdict(dict)
    for row in conn.execute(
        f"SELECT src_work.author AS author, xr.source_method AS sm, COUNT(*) AS n "
        f"{base_from} AND src_work.author IS NOT NULL "
        "GROUP BY src_work.author, xr.source_method"
    ):
        src_method_by_src[row["author"]][row["sm"]] = row["n"]

    # Curator status (independent of confidence-gated visibility, so
    # this query runs without VISIBLE_CLAUSE — gives the dashboard a
    # truthful "how much of each author is still pending" picture).
    cur_status_unfiltered = (
        "FROM cross_references xr "
        "JOIN chunks c ON c.chunk_id = xr.source_chunk_id "
        "LEFT JOIN editions e ON e.id = c.edition_id "
        "LEFT JOIN translations t ON t.id = c.translation_id "
        "LEFT JOIN works src_work "
        "       ON src_work.id = COALESCE(e.work_id, t.work_id) "
        "WHERE src_work.author IS NOT NULL"
    )
    cur_status_by_src: dict[str, dict[str, int]] = defaultdict(dict)
    for row in conn.execute(
        f"SELECT src_work.author AS author, xr.curator_status AS cs, COUNT(*) AS n "
        f"{cur_status_unfiltered} "
        "GROUP BY src_work.author, xr.curator_status"
    ):
        cur_status_by_src[row["author"]][row["cs"]] = row["n"]

    # Hub vs authority — joint outgoing + incoming per in-corpus author.
    out_map = {row["author"]: row["outgoing"] for row in per_source}
    in_map = {row["author"]: row["incoming"] for row in per_target if row["in_corpus"]}
    hub_authority = []
    for author in sorted(set(out_map) | set(in_map), key=author_ordinal):
        hub_authority.append(
            {
                "author": author,
                "outgoing": out_map.get(author, 0),
                "incoming": in_map.get(author, 0),
                "ordinal": author_ordinal(author),
            }
        )

    out_path = Path("docs/dashboard_aggregates.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "filter": (
                    "curator_status IN ('approved','manual') OR "
                    "(curator_status='auto' AND confidence>=0.8)"
                ),
                "total_visible_edges": total,
                "in_corpus_source_authors": len(per_source),
                "all_target_authors": len(per_target),
                "per_source_author": per_source,
                "per_target_author": per_target,
                "source_target_matrix": matrix,
                "reference_type_by_source": dict(ref_type_by_src),
                "source_method_by_source": dict(src_method_by_src),
                "curator_status_by_source": dict(cur_status_by_src),
                "hub_authority": hub_authority,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out_path}")
    print(f"  total visible edges:     {total:,}")
    print(f"  source authors:          {len(per_source)}")
    print(f"  target authors:          {len(per_target)}")
    print(f"  non-zero matrix cells:   {len(matrix)}")


if __name__ == "__main__":
    main()
