"""``minerva serve`` — run the HTTP API + serve the SolidJS frontend.

Extracted from the original monolithic ``cli/__init__.py`` per the
maintainability audit; the dispatch wiring still happens in
``cli/__init__.py``'s ``build_parser``, which calls
:func:`register` to attach this subcommand.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .. import concept_cache, conversations, llm, store, translations
from ._shared import (
    DEFAULT_CONCEPT_CACHE_DB,
    DEFAULT_CONVERSATIONS_DB,
    DEFAULT_TRANSLATIONS_DB,
    REPO_ROOT,
    add_common_db_arg,
    add_llm_args,
    add_retrieval_args,
    auto_embedder,
    make_backend,
)


def cmd_serve(args: argparse.Namespace) -> int:
    from .. import server as _server

    conn = store.open_db(args.db, check_same_thread=False)
    conversations_conn = conversations.open_db(args.conversations_db, check_same_thread=False)
    translations_conn = translations.open_db(args.translations_db, check_same_thread=False)
    # Persistent concept-expansion cache. Skipped when --no-concept-expand
    # was passed (no point opening a cache for a feature that's off).
    concept_cache_conn = (
        None
        if args.no_concept_expand
        else concept_cache.open_db(args.concept_cache_db, check_same_thread=False)
    )
    # Auto-load the embedder when embeddings exist in the index —
    # the long-running server should always do hybrid retrieval if it
    # can, even without --use-vectors on the command line. The CLI
    # `ask` command still uses maybe_embedder (explicit opt-in).
    embedder = auto_embedder(args, conn)
    try:
        backend = make_backend(args)
    except llm.LLMError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    _server.serve(
        host=args.host,
        port=args.port,
        static_dir=args.static,
        conn=conn,
        conversations_conn=conversations_conn,
        translations_conn=translations_conn,
        concept_cache_conn=concept_cache_conn,
        backend=backend,
        embedder=embedder,
        lang=None if args.lang == "any" else args.lang,
        corpus=None if args.corpus == "any" else args.corpus,
        speaker=args.speaker,
        top_k=args.top_k,
        allow_client_rewrite=not args.no_client_rewrite,
        force_rewrite=not args.no_auto_rewrite,
        enable_concept_expand=not args.no_concept_expand,
        allowed_origins=frozenset(args.allow_origin),
    )
    return 0


def register(parent_subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    psv = parent_subparsers.add_parser(
        "serve", help="Run the HTTP API and serve the SolidJS frontend."
    )
    add_common_db_arg(psv)
    add_retrieval_args(psv)
    add_llm_args(psv)
    psv.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1).")
    psv.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000).")
    psv.add_argument(
        "--no-client-rewrite",
        action="store_true",
        help=(
            "Reject `rewrite: true` from clients. Stops untrusted callers "
            "from doubling LLM token spend per turn; recommended whenever "
            "the listener is not on 127.0.0.1."
        ),
    )
    psv.add_argument(
        "--no-auto-rewrite",
        action="store_true",
        help=(
            "Disable server-side automatic follow-up rewriting. By default "
            "every multi-turn chat request runs an extra LLM call to "
            "expand the latest message into a standalone retrieval query, "
            "which substantially improves recall on follow-ups like 'what "
            "about for Hegel?'. Pass this flag to skip that call when "
            "latency or token cost matter more than retrieval quality."
        ),
    )
    psv.add_argument(
        "--no-concept-expand",
        action="store_true",
        help=(
            "Disable LLM concept expansion. By default the server runs "
            "an extra LLM call when a query's resolved corpus has a "
            "non-English original language, asking the model to surface "
            "2-4 key target-language terms (e.g., English 'failures' for "
            "a Nietzsche query → German 'Mißratenen'). The terms are "
            "appended to the retrieval query so the multilingual "
            "embedding model can find passages it would otherwise miss. "
            "Pass this flag to skip the call when latency or token "
            "cost matter more than cross-lingual retrieval quality."
        ),
    )
    psv.add_argument(
        "--allow-origin",
        action="append",
        default=[],
        metavar="ORIGIN",
        help=(
            "Origin to allow via CORS when not bound to localhost. "
            "Pass multiple times for multiple origins, e.g. "
            "`--allow-origin https://example.com`. Localhost binds use a "
            "permissive `*` and ignore this flag."
        ),
    )
    psv.add_argument(
        "--static",
        type=Path,
        default=REPO_ROOT / "web" / "dist",
        help="Directory of built SolidJS assets (run `npm run build` in web/).",
    )
    psv.add_argument(
        "--conversations-db",
        type=Path,
        default=DEFAULT_CONVERSATIONS_DB,
        help=(
            "SQLite path for chat history. Kept separate from the corpus "
            f"index so re-ingests don't wipe conversations (default: "
            f"{DEFAULT_CONVERSATIONS_DB.relative_to(REPO_ROOT)})."
        ),
    )
    psv.add_argument(
        "--translations-db",
        type=Path,
        default=DEFAULT_TRANSLATIONS_DB,
        help=(
            "SQLite path for the reader's translation cache. Cache key is "
            "(source_text, target_lang); repeat selections skip the LLM. "
            f"Default: {DEFAULT_TRANSLATIONS_DB.relative_to(REPO_ROOT)}."
        ),
    )
    psv.add_argument(
        "--concept-cache-db",
        type=Path,
        default=DEFAULT_CONCEPT_CACHE_DB,
        help=(
            "SQLite path for the concept-expansion cache. Cache key is "
            "(normalized_query, corpus, target_lang); repeat questions skip "
            "the LLM concept-expansion call. Survives corpus re-ingests. "
            f"Default: {DEFAULT_CONCEPT_CACHE_DB.relative_to(REPO_ROOT)}."
        ),
    )
    psv.set_defaults(func=cmd_serve)
