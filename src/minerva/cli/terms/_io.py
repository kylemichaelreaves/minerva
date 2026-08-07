"""Shared I/O helpers for the `terms` CLI subcommands.

`_open` opens the curator DB and `_with_db` wraps a subcommand so the
connection it opens is closed again; `_read_text_input` resolves long-form
text from one of three inputs (inline string, file path, stdin);
`_print_table` / `_emit` handle the curator-facing output shape.
`_add_common_db_arg` is a thin shim over the canonical
`cli/_shared.py:add_common_db_arg` kept for the existing
`terms/__init__.py` call sites.
"""

from __future__ import annotations

import argparse
import functools
import json
import sqlite3
import sys
from collections.abc import Callable, Sequence
from contextlib import closing
from pathlib import Path
from typing import Any

from ... import store


def _open(args: argparse.Namespace) -> sqlite3.Connection:
    conn = store.open_db(args.db)
    return conn


def _with_db(
    fn: Callable[[argparse.Namespace, sqlite3.Connection], int],
) -> Callable[[argparse.Namespace], int]:
    """Open the curator DB for the duration of one subcommand, and close
    it on the way out — including on the early `return 1` paths, which is
    why this is a wrapper rather than a `close()` at the end of each body.

    The handlers are plain functions taking a `Namespace`, which is what
    makes them testable and equally what invites calling them in a loop;
    without this, every such call would strand a connection (#227).

    The wrapped handler keeps its one-argument call shape, so callers and
    the argparse `set_defaults(func=...)` wiring are unaffected."""

    @functools.wraps(fn)
    def wrapper(args: argparse.Namespace) -> int:
        with closing(_open(args)) as conn:
            return fn(args, conn)

    # Read by the lifecycle test, which asserts every `cmd_terms_*`
    # handler either carries this decorator or closes its own
    # connection — so a handler added later can't quietly leak again.
    wrapper._closes_db = True  # type: ignore[attr-defined]
    return wrapper


def _read_text_input(value: str | None, file_path: Path | None) -> str | None:
    """Resolve a piece of long-form text from one of three sources:
    an inline string (``--foo "..."``), a file (``--foo-file path``),
    or stdin (``--foo -``). Returns None when nothing was supplied."""

    if value == "-":
        return sys.stdin.read()
    if value is not None:
        return value
    if file_path is not None:
        return file_path.read_text(encoding="utf-8")
    return None


def _print_table(rows: Sequence[Sequence[Any]], headers: Sequence[str]) -> None:
    """Tab-aligned table with right-trimmed columns. Long cells wrap
    by truncation with an ellipsis rather than overflowing the line —
    a CLI listing isn't a place for word wrap."""

    str_rows = [[str(c) if c is not None else "" for c in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in str_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], min(len(cell), 60))

    def fmt(cells: Sequence[str]) -> str:
        out = []
        for i, cell in enumerate(cells):
            if len(cell) > widths[i]:
                cell = cell[: widths[i] - 1] + "…"
            out.append(cell.ljust(widths[i]))
        return "  ".join(out).rstrip()

    print(fmt(headers))
    print(fmt(["-" * w for w in widths]))
    for row in str_rows:
        print(fmt(row))


def _emit(rows: Sequence[Sequence[Any]], headers: Sequence[str], as_json: bool) -> None:
    if as_json:
        payload = [dict(zip(headers, row, strict=True)) for row in rows]
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        _print_table(rows, headers)


def _add_common_db_arg(p: argparse.ArgumentParser) -> None:
    """Shim over the canonical helper in ``cli/_shared.py`` — the two
    used to be duplicate implementations. Local import to avoid a
    top-level cycle: the parent `cli` package imports from this
    subpackage as part of `register_subparsers`."""

    from .._shared import add_common_db_arg

    add_common_db_arg(p)
