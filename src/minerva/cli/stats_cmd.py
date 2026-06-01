"""``minerva stats`` — print index statistics."""

from __future__ import annotations

import argparse
import json

from .. import store
from ._shared import add_common_db_arg


def cmd_stats(args: argparse.Namespace) -> int:
    conn = store.open_db(args.db)
    out = store.stats(conn)
    if args.tables:
        # Per-table row counts — one COUNT(*) per table, fast but not
        # free. Kept behind a flag because the default stats payload
        # is meant to be cheap enough to print on every re-index.
        out["tables"] = store.tables_summary(conn)
    print(json.dumps(out, indent=2, default=str))
    return 0


def register(parent_subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    ps = parent_subparsers.add_parser("stats", help="Print index statistics.")
    add_common_db_arg(ps)
    ps.add_argument(
        "--tables",
        action="store_true",
        help=(
            "Include a per-table row-count inventory in the output. "
            "Useful after a re-ingest to confirm nothing was silently "
            "dropped. For physical / schema-level info (DB size, page "
            "count, migrations), use `minerva db inspect` instead."
        ),
    )
    ps.set_defaults(func=cmd_stats)
