"""``minerva chat`` — interactive REPL against the corpus.

Largest of the top-level commands by line count — keeps the
follow-up-rewrite path, pin/unpin/reset commands, and history
threading all in one place so the REPL's behavior is auditable from
a single ``while True`` loop.
"""

from __future__ import annotations

import argparse
import sys

from .. import agent, llm, retrieve, store
from ._shared import (
    add_common_db_arg,
    add_llm_args,
    add_reply_lang_arg,
    add_retrieval_args,
    make_backend,
    maybe_embedder,
)


def cmd_chat(args: argparse.Namespace) -> int:
    conn = store.open_db(args.db)
    embedder = maybe_embedder(args, conn)
    try:
        backend = make_backend(args)
    except llm.LLMError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"minerva chat ({backend.name} backend, lang={args.lang}, corpus={args.corpus}).")
    print(
        "  exit | /reset | /pin <i> | /unpin <i|all> | /pinned"
        + ("  [rewrite ON]" if getattr(args, "rewrite", False) else "")
    )
    history: list[llm.Message] = []
    # Mirrors all user queries (including ones where backend is `none`
    # or the answer abstained — neither populates `history`, but those
    # turns still inform the retrieval context).
    recent_user: list[str] = []
    pinned: list[retrieve.Hit] = []
    last_hits: list[retrieve.Hit] = []
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not q:
            continue
        ql = q.lower()
        if ql in {"exit", "quit", ":q"}:
            return 0
        if ql in {"/reset", ":reset"}:
            history.clear()
            recent_user.clear()
            pinned.clear()
            last_hits = []
            print("(history and pins cleared)")
            continue
        if ql == "/pinned":
            if not pinned:
                print("(no pins)")
            else:
                for i, h in enumerate(pinned, 1):
                    print(f"  [P{i}] {retrieve.format_locator(h.meta)}")
            continue
        if ql.startswith("/pin "):
            arg = q[len("/pin ") :].strip()
            if not last_hits:
                print("(nothing to pin yet — ask a question first)")
                continue
            try:
                idx = int(arg)
            except ValueError:
                print(f"(usage: /pin <index 1..{len(last_hits)}>)")
                continue
            if not 1 <= idx <= len(last_hits):
                print(f"(index out of range; have {len(last_hits)} hits)")
                continue
            hit = last_hits[idx - 1]
            if any(p.chunk_id == hit.chunk_id for p in pinned):
                print(f"(already pinned: {retrieve.format_locator(hit.meta)})")
            else:
                pinned.append(hit)
                print(f"(pinned [P{len(pinned)}] {retrieve.format_locator(hit.meta)})")
            continue
        if ql.startswith("/unpin"):
            arg = q[len("/unpin") :].strip()
            if arg in {"", "all"}:
                pinned.clear()
                print("(all pins cleared)")
                continue
            try:
                idx = int(arg)
            except ValueError:
                print("(usage: /unpin <index> | /unpin all)")
                continue
            if not 1 <= idx <= len(pinned):
                print(f"(index out of range; have {len(pinned)} pins)")
                continue
            removed = pinned.pop(idx - 1)
            print(f"(unpinned {retrieve.format_locator(removed.meta)})")
            continue

        if getattr(args, "rewrite", False) and history and backend.name != "none":
            rewritten = agent.rewrite_query(backend, history, q)
            if rewritten:
                retrieval_query = rewritten
                print(f"  (rewrote → {rewritten!r})", file=sys.stderr)
            else:
                retrieval_query = agent.build_retrieval_query(q, recent_user)
                print(
                    "  (rewrite failed; falling back to naive concatenation)",
                    file=sys.stderr,
                )
        else:
            retrieval_query = agent.build_retrieval_query(q, recent_user)
        reply_lang = None if args.reply_lang == "auto" else args.reply_lang
        ans = agent.answer(
            conn=conn,
            query=q,
            backend=backend,
            top_k=args.top_k,
            lang=None if args.lang == "any" else args.lang,
            corpus=None if args.corpus == "any" else args.corpus,
            speaker=args.speaker,
            embedder=embedder,
            history=history,
            retrieval_query=retrieval_query,
            pinned=pinned,
            reply_lang=reply_lang,
        )
        print(agent.render_answer(ans))
        print()
        if not ans.abstained:
            last_hits = ans.hits
        if not ans.abstained and backend.name != "none":
            history.append(llm.Message(role="user", content=q))
            history.append(llm.Message(role="assistant", content=ans.response))
        recent_user.append(q)


def register(parent_subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    pc = parent_subparsers.add_parser("chat", help="Interactive REPL.")
    add_common_db_arg(pc)
    add_retrieval_args(pc)
    add_reply_lang_arg(pc)
    add_llm_args(pc)
    pc.add_argument(
        "--rewrite",
        action="store_true",
        help=(
            "Use the LLM to rewrite each follow-up into a standalone "
            "retrieval query (extra LLM call per turn)."
        ),
    )
    pc.set_defaults(func=cmd_chat)
