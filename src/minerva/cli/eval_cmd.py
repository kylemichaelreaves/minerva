"""``minerva eval`` — score retrieval against the gold set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .. import store
from ._shared import add_common_db_arg, add_retrieval_args, maybe_embedder


def cmd_eval(args: argparse.Namespace) -> int:
    from .. import eval_runner

    conn = store.open_db(args.db)
    embedder = maybe_embedder(args, conn)
    summary = eval_runner.run(
        conn=conn,
        gold_path=args.gold,
        top_k=args.top_k,
        embedder=embedder,
        lang=None if args.lang == "any" else args.lang,
        corpus=None if args.corpus == "any" else args.corpus,
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["pass"] else 1


def register(parent_subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    pv = parent_subparsers.add_parser("eval", help="Score retrieval against the gold set.")
    add_common_db_arg(pv)
    add_retrieval_args(pv)
    # Gold set is Plato-only; default the corpus filter to match.
    pv.set_defaults(corpus="plato")
    pv.add_argument(
        "--gold",
        type=Path,
        # `cli/eval_cmd.py` is at src/minerva/cli/; eval_data lives one
        # level up at src/minerva/eval_data/.
        default=Path(__file__).resolve().parent.parent / "eval_data" / "gold.jsonl",
        help="Path to a gold JSONL eval file.",
    )
    pv.set_defaults(func=cmd_eval)
