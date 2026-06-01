"""`minerva refs list` — filtered listing of cross-references.

Module name is `list_cmd` (not `list`) because Python's stdlib has a
`list` builtin and shadowing it from inside the package leads to
subtle import-order bugs. The exported function `cmd_refs_list` is
the only public surface.
"""

from __future__ import annotations

import argparse

from ...refs import schema as refs_schema
from ..terms._io import _emit, _open


def cmd_refs_list(args: argparse.Namespace) -> int:
    conn = _open(args)
    conn.execute("PRAGMA foreign_keys = ON")

    rows = refs_schema.list_references(
        conn,
        source_author=args.source_author,
        target_author=args.target_author,
        target_work=args.target_work,
        curator_status=args.status,
        limit=args.limit,
    )

    headers = (
        "id",
        "src_author",
        "src_work",
        "src_section",
        "target_author",
        "target_work",
        "target_locator",
        "type",
        "conf",
        "method",
        "status",
    )
    table_rows = [
        (
            r["id"],
            r["source_author"],
            r["source_work"],
            r["source_section"],
            r["target_author"],
            r["target_work"],
            r["target_locator"],
            r["reference_type"],
            f"{r['confidence']:.2f}",
            r["source_method"],
            r["curator_status"],
        )
        for r in rows
    ]
    _emit(table_rows, headers, as_json=args.json)
    return 0
