"""Shared helpers and constants for the top-level CLI commands.

Carved out of the original monolithic ``cli/__init__.py`` so each
``cmd_*`` lives in its own focused module under ``cli/`` (the
``ingest_cmd.py``, ``serve_cmd.py``, etc. files). The composer in
``cli/__init__.py`` is now a thin shell that wires the subparsers
together by importing each module's ``register`` function.

Helpers exposed here:

* :data:`REPO_ROOT`, :data:`DEFAULT_DB`, :data:`DEFAULT_CHUNKS`,
  :data:`DEFAULT_CONVERSATIONS_DB`, :data:`DEFAULT_TRANSLATIONS_DB`
* :func:`add_common_db_arg`, :func:`add_retrieval_args`,
  :func:`add_llm_args`
* :func:`maybe_embedder`, :func:`make_backend`,
  :func:`validate_base_url`
* :class:`Timer`, :func:`fmt_elapsed`, :func:`record_timing` —
  per-stage instrumentation (Phase 0 of the 2026-05-29
  ingestion-bottleneck remediation plan).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .. import embed, llm
from ..corpus_registry import corpus_ids
from ..paths import REPO_ROOT

# Retrieval language choices — the union of every corpus's original
# language plus the major translation langs we ship. Kept here (not
# hardcoded inline at the `--lang` argparse) so it stays in sync with
# any new corpus added to ``_ORIGINAL_LANG_BY_CORPUS``. ``any`` is
# the wide-open choice and the new default — it searches every
# language and is what the agent needs to find non-English-primary
# texts (Nietzsche/Marx in deu, Hebrew Bible in heb, Cicero/Spinoza
# in lat, the Quran in ara when D lands).
RETRIEVAL_LANG_CHOICES: tuple[str, ...] = (
    "any",
    "eng",
    "grc",
    "deu",
    "lat",
    "fra",
    "heb",
    "ara",
)

# Answer-language choices for chat/ask (retrieval ``any`` excluded).
REPLY_LANG_CHOICES: tuple[str, ...] = tuple(c for c in RETRIEVAL_LANG_CHOICES if c != "any")

# Retrieval corpus choices — the keys of ``_ORIGINAL_LANG_BY_CORPUS``
# (= every ingested corpus) plus the meta ``any``. Hard-coding an
# 8-author list here was the bug behind the multilingual-chat-retrieval
# fix: argparse silently rejected ``--corpus nietzsche`` / ``marx`` /
# ``cicero`` / ``hebrew_mt`` because they weren't listed, even though
# their chunks exist in the index. Driving this from the runtime map
# means new authors light up automatically.
RETRIEVAL_CORPUS_CHOICES: tuple[str, ...] = (
    "any",
    *sorted(corpus_ids()),
)
DEFAULT_DB = REPO_ROOT / "data" / "index.sqlite"
DEFAULT_CONVERSATIONS_DB = REPO_ROOT / "data" / "conversations.sqlite"
DEFAULT_TRANSLATIONS_DB = REPO_ROOT / "data" / "translations.sqlite"
DEFAULT_CONCEPT_CACHE_DB = REPO_ROOT / "data" / "concept_cache.sqlite"
DEFAULT_CHUNKS = REPO_ROOT / "data" / "chunks.jsonl"


def add_common_db_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"SQLite index path (default: {DEFAULT_DB.relative_to(REPO_ROOT)}).",
    )


def add_retrieval_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--top-k", type=int, default=6, help="Hits to return.")
    p.add_argument(
        "--lang",
        choices=RETRIEVAL_LANG_CHOICES,
        default="any",
        help=(
            "Restrict retrieval to one ISO 639-3 language code, or "
            "`any` (default) to search all. The default was `eng` for "
            "a long time and silently excluded German Nietzsche/Marx, "
            "Latin Cicero/Spinoza, Greek primary texts, and Hebrew MT "
            "from chat retrieval — switching to `any` is the right "
            "default for a multi-language corpus."
        ),
    )
    p.add_argument(
        "--corpus",
        choices=RETRIEVAL_CORPUS_CHOICES,
        default="any",
        help=(
            "Restrict retrieval to one author/corpus slug (default: "
            "any). The choices are driven by "
            "``runtime_helpers._ORIGINAL_LANG_BY_CORPUS`` so new "
            "authors light up automatically once they're added there."
        ),
    )
    p.add_argument(
        "--speaker",
        default=None,
        help=(
            "Restrict retrieval to passages spoken by this character "
            "(case-insensitive, e.g. 'Socrates'). Applies to dialogues; "
            "narrator-style works (Republic) attribute everything to the narrator."
        ),
    )
    p.add_argument(
        "--use-vectors",
        action="store_true",
        help="Use stored embeddings if present (requires `minerva embed` first).",
    )
    p.add_argument(
        "--embed-model",
        default=embed.DEFAULT_MODEL,
        help="Sentence-transformers model name for queries.",
    )


def add_reply_lang_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--reply-lang",
        choices=("auto", *REPLY_LANG_CHOICES),
        default="auto",
        help=(
            "Language for the assistant's answer prose (ISO 639-3). "
            "`auto` (default) matches the question; passages stay in "
            "their source language."
        ),
    )


# Vendor-default base URLs for the providers we trust. An override that
# doesn't match these is a way to leak credentials to an attacker-
# controlled host, so we warn loudly and refuse without an explicit
# `--unsafe-llm-base-url-host` opt-in. Localhost is always permitted
# (typical ollama / proxy setup).
_TRUSTED_BASE_URL_HOSTS: dict[str, set[str]] = {
    "openai": {"api.openai.com"},
    "anthropic": {"api.anthropic.com"},
    "ollama": set(),  # `--llm-base-url` is the host; localhost loop handles itself
}


def validate_base_url(args: argparse.Namespace) -> None:
    """Refuse non-trusted ``--llm-base-url`` hosts unless the user has
    explicitly accepted the risk. The credential goes to whatever host
    is named here; the user only sees a successful (or failing) HTTP
    call. A path-traversal / pastebin compromise becomes a credential
    leak otherwise.
    """

    url = args.llm_base_url
    if not url:
        return
    from urllib.parse import urlparse as _urlparse

    parsed = _urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return  # local proxy / ollama; safe
    trusted = _TRUSTED_BASE_URL_HOSTS.get(args.llm, set())
    if host in trusted:
        return
    if args.unsafe_llm_base_url_host:
        print(
            f"WARNING: sending {args.llm.upper()} credentials to non-default "
            f"host {host!r}. Confirmed by --unsafe-llm-base-url-host; "
            "double-check this is a host you control.",
            file=sys.stderr,
        )
        return
    print(
        f"refusing to send {args.llm.upper()} credentials to non-default "
        f"host {host!r}. Trusted defaults: {sorted(trusted) or '(localhost)'}. "
        "Re-run with --unsafe-llm-base-url-host if this is intentional.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def make_backend(args: argparse.Namespace) -> llm.LLMBackend:
    validate_base_url(args)
    return llm.make_backend(args.llm, model=args.llm_model, base_url=args.llm_base_url)


def add_llm_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--llm",
        choices=("none", "openai", "anthropic", "ollama"),
        default="none",
        help="Which LLM backend to use; `none` prints retrieved passages only.",
    )
    p.add_argument(
        "--llm-model",
        default=None,
        help="Model name passed to the chosen backend.",
    )
    p.add_argument(
        "--llm-base-url",
        default=None,
        help=(
            "Override the API base URL (OpenAI-compatible) or Ollama host. "
            "Non-default hosts require --unsafe-llm-base-url-host since "
            "the credential goes to whatever host is named here."
        ),
    )
    p.add_argument(
        "--unsafe-llm-base-url-host",
        action="store_true",
        help=(
            "Explicit opt-in to send the LLM credential to a non-default "
            "host via --llm-base-url. Required for anything outside the "
            "vendor's API host or localhost."
        ),
    )


def maybe_embedder(args: argparse.Namespace, conn: sqlite3.Connection) -> embed.Embedder | None:
    if not args.use_vectors:
        return None
    from .. import store

    if not store.has_embeddings(conn):
        print(
            "No embeddings present in store. Run `minerva embed` first or "
            "drop --use-vectors to fall back to lexical search.",
            file=sys.stderr,
        )
        return None
    try:
        return embed.Embedder(args.embed_model)
    except embed.EmbeddingsUnavailable as exc:
        print(f"Vector search unavailable: {exc}", file=sys.stderr)
        return None


class Timer:
    """Tiny ``perf_counter`` wall-clock timer.

    Usage::

        with Timer() as t:
            do_work()
        print(t.elapsed)  # float seconds, monotonic

    Or the context-manager form via :func:`timed`::

        with timed("ingest:plato") as t:
            list(parser.parse_dir(...))

    The class deliberately avoids logging side-effects so it composes
    cleanly inside loops; callers print or persist as they like.
    """

    __slots__ = ("_end", "_start")

    def __init__(self) -> None:
        self._start: float | None = None
        self._end: float | None = None

    def __enter__(self) -> Timer:
        self._start = time.perf_counter()
        self._end = None
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._end = time.perf_counter()

    @property
    def elapsed(self) -> float:
        if self._start is None:
            return 0.0
        end = self._end if self._end is not None else time.perf_counter()
        return end - self._start


@contextmanager
def timed(label: str, *, stream: object | None = None) -> Iterator[Timer]:
    """Run a block under a :class:`Timer` and print ``label  Xs`` on
    exit. ``stream`` defaults to stderr so timing output doesn't
    contaminate stdout pipelines (chunks JSONL, stats JSON)."""

    t = Timer()
    with t:
        yield t
    msg = f"timing: {label}  {fmt_elapsed(t.elapsed)}"
    print(msg, file=stream if stream is not None else sys.stderr)


def fmt_elapsed(seconds: float) -> str:
    """Format ``seconds`` as ``Xs`` for sub-minute, ``Xm Ys`` otherwise.
    The 2-decimal sub-minute precision keeps fast stages (the lemma
    aggregate at ~25s) readable while still distinguishing 0.4s from
    0.9s, which matters when comparing two parser implementations."""

    if seconds < 60:
        return f"{seconds:.2f}s"
    mins, secs = divmod(seconds, 60)
    return f"{int(mins)}m {secs:.1f}s"


def record_timing(
    db: Path,
    key: str,
    elapsed: float,
) -> None:
    """Persist a timing into the ``meta`` table under ``timing.<key>``
    so ``minerva stats`` and future tooling can read the last run
    without re-instrumenting. Idempotent (overwrites). Safely no-ops
    when the DB doesn't exist yet (e.g. a fresh ``ingest`` that
    hasn't been indexed) — timings are diagnostic, not load-bearing.
    """

    if not db.exists():
        return
    conn = sqlite3.connect(db)
    try:
        # `meta` is created by the schema; defensive check anyway so we
        # don't crash on a half-built DB. INSERT OR REPLACE handles
        # the idempotent-overwrite semantics.
        has_meta = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='meta'"
        ).fetchone()
        if has_meta is None:
            return
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (f"timing.{key}", f"{elapsed:.3f}"),
        )
        conn.commit()
    finally:
        conn.close()


def auto_embedder(args: argparse.Namespace, conn: sqlite3.Connection) -> embed.Embedder | None:
    """Load the embedder whenever embeddings are present in the DB.

    Used by ``minerva serve`` instead of ``maybe_embedder`` so the
    chat agent gets hybrid (BM25 + vector) retrieval by default. The
    CLI ``ask`` keeps the explicit ``--use-vectors`` opt-in (it's a
    one-shot command where the user may want to compare retrieval
    modes); the long-running server has no reason to fall back to
    lexical-only when vectors are sitting right there in the index.

    Without this, queries like "Who are the failures according to
    Nietzsche?" couldn't find Nietzsche's German *Mißratenen*
    passages — BM25 alone can't bridge an English query to German
    content. The user-visible bug surfaced after Hebrew MT + Quran
    landed; the same problem applied to Greek/Latin all along.
    """

    from .. import store

    if not store.has_embeddings(conn):
        return None
    try:
        return embed.Embedder(args.embed_model)
    except embed.EmbeddingsUnavailable as exc:
        print(f"Vector search unavailable: {exc}", file=sys.stderr)
        return None
