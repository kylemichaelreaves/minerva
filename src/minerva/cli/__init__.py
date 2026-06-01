"""Command-line entry point.

The original monolith was split per the maintainability audit; each
subcommand now lives in its own ``cli/<name>_cmd.py`` module with a
``register(parent_subparsers)`` function. This file's only job is to
build the top-level argparse, call each command's ``register``, and
dispatch ``args.func``.

Re-exports of ``cmd_*`` and ``build_parser`` are preserved for
existing callers (``tests/test_cli_args.py`` patches a few of these
into argparse via module-level lookup).

Subcommands:

* ``ingest``    — :mod:`.ingest_cmd`
* ``index``     — :mod:`.index_cmd`
* ``embed``     — :mod:`.embed_cmd`
* ``ask``       — :mod:`.ask_cmd`
* ``chat``      — :mod:`.chat_cmd`
* ``stats``     — :mod:`.stats_cmd`
* ``serve``     — :mod:`.serve_cmd`
* ``eval``      — :mod:`.eval_cmd`
* ``terms ...`` — :mod:`.terms`
* ``refs ...``  — :mod:`.refs`
"""

from __future__ import annotations

import argparse
import sys

# Re-export the per-command handlers + shared helpers under the old
# module names so external callers (tests, scripts) don't break.
from . import (
    ask_cmd,
    chat_cmd,
    db_cmd,
    embed_cmd,
    eval_cmd,
    index_cmd,
    ingest_cmd,
    serve_cmd,
    stats_cmd,
)
from ._shared import (
    DEFAULT_CHUNKS,
    DEFAULT_CONVERSATIONS_DB,
    DEFAULT_DB,
    DEFAULT_TRANSLATIONS_DB,
    REPO_ROOT,
)

# Aliased re-exports — tests patch these via module-attribute lookup
# (e.g. `monkeypatch.setattr(cli, "_make_backend", ...)`). The leading
# underscore keeps them out of the public CLI surface while preserving
# the patch hook. Ruff F401 doesn't recognise renamed re-exports as
# intentional, so suppress per-line.
from ._shared import add_common_db_arg as _add_common_db_arg  # noqa: F401
from ._shared import add_llm_args as _add_llm_args  # noqa: F401
from ._shared import add_retrieval_args as _add_retrieval_args  # noqa: F401
from ._shared import make_backend as _make_backend  # noqa: F401
from ._shared import maybe_embedder as _maybe_embedder  # noqa: F401
from ._shared import validate_base_url as _validate_base_url  # noqa: F401
from .ask_cmd import cmd_ask
from .chat_cmd import cmd_chat
from .embed_cmd import cmd_embed
from .eval_cmd import cmd_eval
from .index_cmd import _maybe_snapshot_pre_index, cmd_index  # noqa: F401
from .ingest_cmd import cmd_ingest
from .serve_cmd import cmd_serve
from .stats_cmd import cmd_stats

__all__ = [
    "DEFAULT_CHUNKS",
    "DEFAULT_CONVERSATIONS_DB",
    "DEFAULT_DB",
    "DEFAULT_TRANSLATIONS_DB",
    "REPO_ROOT",
    "build_parser",
    "cmd_ask",
    "cmd_chat",
    "cmd_embed",
    "cmd_eval",
    "cmd_index",
    "cmd_ingest",
    "cmd_serve",
    "cmd_stats",
    "main",
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="minerva",
        description=(
            "Retrieval-grounded reader and agent over a multilingual corpus "
            "of philosophy and primary sources — Greek, Latin, German, "
            "French, English, Hebrew, and Arabic editions."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # Top-level subcommands — one register call per command module.
    ingest_cmd.register(sub)
    index_cmd.register(sub)
    embed_cmd.register(sub)
    ask_cmd.register(sub)
    chat_cmd.register(sub)
    stats_cmd.register(sub)
    db_cmd.register(sub)
    serve_cmd.register(sub)
    eval_cmd.register(sub)

    # Term-glossary curator commands (cli/terms subpackage).
    from .terms import register_subparsers as _register_terms

    _register_terms(sub)

    # Cross-reference curator commands (cli/refs subpackage).
    from .refs import register_subparsers as _register_refs

    _register_refs(sub)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
