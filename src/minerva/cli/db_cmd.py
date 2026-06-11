"""``minerva db`` — DB-level introspection (and a hook for future
maintenance subcommands like `vacuum` / `analyze` / `integrity-check`).

Today only ``inspect`` is implemented. It complements ``minerva stats``:

* ``minerva stats``       — data-shaped: total chunks, per-corpus/lang
                           counts, embedding presence. Add ``--tables``
                           for a per-table row inventory.
* ``minerva db inspect``  — storage- and schema-shaped: file size,
                           page count + free pages, journal mode,
                           schema-object counts (tables / indexes /
                           views / triggers), latest applied migration.
"""

from __future__ import annotations

import argparse
import json
import sys

from .. import store
from ._shared import add_common_db_arg


def cmd_db(args: argparse.Namespace) -> int:
    if args.action == "inspect":
        return _cmd_db_inspect(args)
    # Unreachable today (argparse's required subparser only admits
    # "inspect") but kept as a guard for future actions; return an
    # exit code like every other cmd_* instead of raising SystemExit.
    print(f"unknown db action: {args.action!r}", file=sys.stderr)
    return 2


def _cmd_db_inspect(args: argparse.Namespace) -> int:
    conn = store.open_db(args.db)
    print(json.dumps(store.db_inspect(conn, args.db), indent=2, default=str))
    return 0


def register(parent_subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    pd = parent_subparsers.add_parser(
        "db",
        help="Database inspection and maintenance.",
    )
    sub = pd.add_subparsers(dest="action", required=True)

    pi = sub.add_parser(
        "inspect",
        help=(
            "Print storage- and schema-level info: DB file size, "
            "SQLite page count + free pages, journal mode, schema "
            "object counts, latest applied migration."
        ),
    )
    add_common_db_arg(pi)
    pi.set_defaults(func=cmd_db)
