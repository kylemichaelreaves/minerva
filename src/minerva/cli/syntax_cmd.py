"""``minerva syntax parse`` — warm the dependency-tree cache in bulk.

The overlay parses on demand, so this is never required. It exists for the
case where you know you are about to read a whole work and would rather not
pay ~0.15s on each chunk's first open — and for reparsing after a model
upgrade.

Writes the same `chunk_syntax` rows the endpoint reads, so a warmed chunk is
simply a cache hit. Hand corrections are untouched: they live in a separate
append-only table and are replayed over whatever parse is current.
"""

from __future__ import annotations

import argparse
import sys
import time

from .. import store
from ..syntax import queries as syntax_queries
from ._shared import add_common_db_arg


def _current_parser_id() -> str | None:
    """The installed parser's id, or None when it cannot be determined.

    None drops the staleness clause entirely, leaving only "never
    parsed" — the same conservative choice `queries._is_stale_parser`
    makes, and for the same reason: Stanza is an optional extra, and
    without it there is no evidence any stored tree is stale.

    It must not be passed to the clause as a parameter. `s.parser IS NOT
    NULL` is **true** for every parsed row, so doing that would select
    the entire corpus for reparse rather than nothing.
    """

    from ..syntax.parse import parser_id

    try:
        return parser_id()
    except Exception:
        return None


def _selection_clause(args: argparse.Namespace) -> tuple[list[str], list[object]]:
    """The WHERE fragments and bound parameters for "what needs parsing"."""

    where = ["c.lang = ?"]
    params: list[object] = [args.lang]
    if args.work is not None:
        where.append("cf.work_id = ?")
        params.append(args.work)
    if args.reparse:
        return where, params

    current = _current_parser_id()
    if current is None:
        # No installed parser to compare against, so no evidence any stored
        # tree is stale: select only genuinely unparsed chunks.
        where.append("s.chunk_id IS NULL")
        return where, params

    # Unparsed, or parsed by a model that is no longer installed. Without the
    # second clause a stale tree is never selected and `syntax parse` reports
    # "nothing to do" while serving it — even though this command's own
    # docstring offers itself "for reparsing after a model upgrade" (#531).
    where.append("(s.chunk_id IS NULL OR s.parser IS NOT ?)")
    params.append(current)
    return where, params


def register(parent_subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    ps = parent_subparsers.add_parser(
        "syntax",
        help="Dependency-syntax trees for the reader overlay.",
    )
    sub = ps.add_subparsers(dest="syntax_cmd", required=True)

    parse_p = sub.add_parser(
        "parse",
        help="Parse and cache dependency trees for chunks that lack them.",
    )
    add_common_db_arg(parse_p)
    parse_p.add_argument(
        "--work",
        type=int,
        help="Restrict to one works.id. Omit to cover every eligible chunk.",
    )
    parse_p.add_argument(
        "--lang",
        default="deu",
        help=(
            "Language to parse. Only 'deu' is wired up — Stanza's German "
            "models are the ones this feature was built against."
        ),
    )
    parse_p.add_argument(
        "--limit",
        type=int,
        help="Stop after this many chunks. Useful for a first smoke run.",
    )
    parse_p.add_argument(
        "--reparse",
        action="store_true",
        help=(
            "Re-parse chunks that already have trees, replacing them. Use "
            "after a model upgrade. Corrections survive — they are replayed "
            "over whatever parse is current."
        ),
    )
    parse_p.set_defaults(func=cmd_syntax_parse)


def cmd_syntax_parse(args: argparse.Namespace) -> int:
    if args.lang != "deu":
        print(
            f"syntax parse: only 'deu' is supported, got {args.lang!r}. "
            "Stanza models for other languages exist but the deprel "
            "inventory and the topological-field heuristic are German-specific.",
            file=sys.stderr,
        )
        return 2

    conn = store.open_db(args.db)

    where, params = _selection_clause(args)

    sql = (
        "SELECT c.chunk_id FROM chunks c "
        "JOIN chunks_full cf ON cf.chunk_id = c.chunk_id "
        "LEFT JOIN chunk_syntax_state s ON s.chunk_id = c.chunk_id "
        f"WHERE {' AND '.join(where)} ORDER BY c.chunk_id"
    )
    if args.limit is not None:
        sql += f" LIMIT {int(args.limit)}"

    chunk_ids = [str(row[0]) for row in conn.execute(sql, params)]
    if not chunk_ids:
        print("syntax parse: nothing to do.")
        return 0

    print(f"syntax parse: {len(chunk_ids):,} chunks ({args.lang})…", flush=True)
    started = time.monotonic()
    done = 0
    for chunk_id in chunk_ids:
        if args.reparse:
            # Drop the state row so load_or_parse treats it as uncached.
            conn.execute("DELETE FROM chunk_syntax_state WHERE chunk_id = ?", (chunk_id,))
            conn.commit()
        syntax_queries.load_or_parse(conn, chunk_id)
        done += 1
        if done % 100 == 0:
            rate = done / max(time.monotonic() - started, 1e-6)
            print(f"  {done:,}/{len(chunk_ids):,}  ({rate:.1f} chunks/s)", flush=True)

    elapsed = time.monotonic() - started
    print(f"syntax parse: {done:,} chunks in {elapsed:.1f}s")
    return 0
