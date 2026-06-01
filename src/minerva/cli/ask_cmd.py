"""``minerva ask`` — one-shot grounded question against the corpus."""

from __future__ import annotations

import argparse
import sys

from .. import agent, llm, store
from ._shared import (
    add_common_db_arg,
    add_llm_args,
    add_reply_lang_arg,
    add_retrieval_args,
    make_backend,
    maybe_embedder,
)


def cmd_ask(args: argparse.Namespace) -> int:
    conn = store.open_db(args.db)
    embedder = maybe_embedder(args, conn)
    try:
        backend = make_backend(args)
    except llm.LLMError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    reply_lang = None if args.reply_lang == "auto" else args.reply_lang
    ans = agent.answer(
        conn=conn,
        query=args.question,
        backend=backend,
        top_k=args.top_k,
        lang=None if args.lang == "any" else args.lang,
        corpus=None if args.corpus == "any" else args.corpus,
        speaker=args.speaker,
        embedder=embedder,
        reply_lang=reply_lang,
    )
    print(agent.render_answer(ans))
    return 0


def register(parent_subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    pa = parent_subparsers.add_parser("ask", help="One-shot grounded question.")
    add_common_db_arg(pa)
    add_retrieval_args(pa)
    add_reply_lang_arg(pa)
    add_llm_args(pa)
    pa.add_argument("question", help="Natural-language question.")
    pa.set_defaults(func=cmd_ask)
