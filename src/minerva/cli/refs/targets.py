"""`minerva refs targets` — list / filter reference_targets rows.

Useful for finding a target_id to pass to `minerva refs add` and for
auditing the seed (which is populated by migration 0012 from the
existing works table plus a hand-listed out-of-corpus catalogue).
"""

from __future__ import annotations

import argparse
import sqlite3

from ..terms._io import _emit, _open


def cmd_refs_targets(args: argparse.Namespace) -> int:
    conn = _open(args)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row

    clauses: list[str] = []
    params: list[object] = []
    if args.author is not None:
        clauses.append("canonical_author = ?")
        params.append(args.author)
    if args.in_corpus and args.out_of_corpus:
        # Both flags pass through as if neither were set — show all.
        pass
    elif args.in_corpus:
        clauses.append("in_corpus_work_id IS NOT NULL")
    elif args.out_of_corpus:
        clauses.append("in_corpus_work_id IS NULL")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = (
        f"SELECT id, canonical_author, canonical_work, citation_system, "
        f"       in_corpus_work_id, notes "
        f"FROM reference_targets "
        f"{where} "
        f"ORDER BY canonical_author, canonical_work "
        f"LIMIT ?"
    )
    params.append(args.limit)
    rows = list(conn.execute(sql, params))

    headers = ("id", "author", "work", "citation_system", "in_corpus_work_id", "notes")
    table = [
        (
            r["id"],
            r["canonical_author"],
            r["canonical_work"],
            r["citation_system"],
            r["in_corpus_work_id"],
            r["notes"],
        )
        for r in rows
    ]
    _emit(table, headers, as_json=args.json)
    return 0
