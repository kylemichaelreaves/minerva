"""Shared types and primitives for the HTTP layer.

Lives separately from `server.py` and `http/handlers/` so neither
has to circular-import the other. `ServerDeps`, `_HTTPError`, and the
in-process `_RateLimiter` are the cross-cutting pieces.
"""

from __future__ import annotations

import dataclasses
import sqlite3
import threading
import time as _time
from collections import deque
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

from .. import embed as embed_mod
from .. import llm

if TYPE_CHECKING:
    # Imported lazily to avoid a circular dependency at runtime —
    # `chat_context` imports from `http.server_core`. The TYPE_CHECKING
    # guard makes the annotation visible to type-checkers and ruff
    # while keeping module load time circle-free.
    from ..chat_context import ChatContext

# ---------- Rate limiting ----------
# A sliding-window per-IP limiter for LLM-billable routes (POST /api/chat
# and POST /api/translate). Costs real money on the Anthropic backend, so
# even a single buggy client looping a request would matter. The window
# is intentionally short and the cap intentionally generous for one human
# operator; the goal is to catch runaway loops and reject obvious abuse,
# not to police legitimate usage. In-process only — useless behind
# multiple workers; for that, front the server with a real gateway.

# (requests, seconds) — capacity per IP per window.
#
# Keyed by router *label*, never by path: most paths carry ids
# (`/api/chunks/<id>/syntax`) and would never match a fixed string. Labels are
# the only stable name a route has.
_RATE_LIMITS: dict[str, tuple[int, float]] = {
    "chat": (30, 60.0),  # 30/min — chat is the costliest
    "translate": (60, 60.0),  # 60/min — translate is cache-hit-heavy
    # A cache miss here runs a Stanza parse: CPU-bound, ~0.15s per paragraph
    # after a ~4s one-time model load. Cache hits are cheap, but nothing in
    # the request tells us which it will be, so the cap covers the worst case
    # while staying far above what reading generates.
    "chunk syntax": (60, 60.0),
    # Same exposure: a correction to a chunk nobody has opened parses it
    # first, because validation needs the tree.
    "syntax correction create": (60, 60.0),
}


# Idle-bucket housekeeping. A bucket is only ever drained when that same
# (route, ip) sends again, so without a sweep an IP that goes quiet keeps
# its entry forever — unbounded growth keyed on a value the caller
# chooses, which matters on the `serve --host 0.0.0.0` bind the operator
# is warned about. The sweep is O(buckets) but runs at most once per
# interval; `_MAX_BUCKETS` is the backstop for an IP-rotating client that
# would otherwise grow the dict without bound *between* sweeps.
_BUCKET_SWEEP_INTERVAL = 300.0  # seconds
_MAX_BUCKETS = 10_000
# Where a size-triggered eviction trims back to, so the cost amortizes
# over the next ~1k new IPs instead of landing on every request.
_BUCKET_TRIM_TO = 9_000


class _RateLimiter:
    """In-process sliding-window rate limiter keyed by (route, ip)."""

    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()
        self._next_sweep = 0.0

    def _sweep(self, t: float) -> None:
        """Drop every bucket whose newest hit has aged out of its own
        route's window. Caller must hold the lock.

        Windows are per-route, so the cutoff is recomputed per key
        rather than taken from the request being served.
        """

        dead = [
            key
            for key, q in self._buckets.items()
            if not q
            or key[0] not in _RATE_LIMITS
            or q[-1] < t - _RATE_LIMITS[key[0]][1]
        ]
        for key in dead:
            del self._buckets[key]

    def allow(self, route: str, ip: str, *, now: float | None = None) -> bool:
        limit = _RATE_LIMITS.get(route)
        if limit is None:
            return True
        cap, window = limit
        t = _time.monotonic() if now is None else now
        cutoff = t - window
        with self._lock:
            if t >= self._next_sweep or len(self._buckets) >= _MAX_BUCKETS:
                self._sweep(t)
                self._next_sweep = t + _BUCKET_SWEEP_INTERVAL
                if len(self._buckets) >= _MAX_BUCKETS:
                    # Still saturated after sweeping: every bucket is
                    # live, so this is active IP rotation rather than
                    # accumulated cruft. Evict least-recently-active
                    # first — they're closest to expiring anyway.
                    #
                    # Trim well below the ceiling rather than by the one
                    # entry we need. This sort is O(n log n) while
                    # holding the lock; doing it per request once full
                    # would hand an IP-rotating client a cheap way to
                    # make every other request pay for it.
                    victims = sorted(
                        self._buckets, key=lambda k: self._buckets[k][-1]
                    )[: len(self._buckets) - _BUCKET_TRIM_TO + 1]
                    for key in victims:
                        del self._buckets[key]

            key = (route, ip)
            q = self._buckets.get(key)
            if q is None:
                q = deque()
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= cap:
                # cap >= 1, so q is non-empty here by construction —
                # the old `else: pop` branch was unreachable.
                self._buckets[key] = q
                return False
            q.append(t)
            self._buckets[key] = q
            return True


# ---------- ServerDeps ----------
# Three independent locks. The previous single-lock design serialized
# *every* DB access (corpus reads, conversation writes, translation
# cache hits) across the lifetime of any LLM round-trip, capping
# concurrency at one in-flight request at a time. Per-resource locks
# let translate's cache hit run while chat is mid-completion, let
# /api/conversations stream the sidebar list under chat load, etc.
# `lock` is retained as an alias to `corpus_lock` so any older code or
# test that touched `deps.lock` keeps working.


@dataclasses.dataclass
class ServerDeps:
    conn: sqlite3.Connection
    conversations_conn: sqlite3.Connection
    translations_conn: sqlite3.Connection
    # Persistent cache for `agent.concept_expand` LLM results. None
    # when --no-concept-expand is set or the cache file path was
    # disabled. Lookups before the LLM call short-circuit on a hit.
    concept_cache_conn: sqlite3.Connection | None
    backend: llm.LLMBackend
    embedder: embed_mod.Embedder | None
    lang: str | None
    corpus: str | None
    speaker: str | None
    top_k: int
    static_dir: Path
    # When False, ignore client-supplied `rewrite: true` in chat requests.
    # Defaults to True for the localhost-only single-user case; harden via
    # `minerva serve --no-client-rewrite` if the listener is exposed.
    allow_client_rewrite: bool = True
    # Always run `agent.rewrite_query` on follow-up turns, regardless of
    # what the client requests. Costs one extra LLM round-trip per turn
    # but dramatically improves retrieval recall on context-dependent
    # follow-ups ("what about for Hegel?") where the raw query has no
    # useful BM25 signal. Disable via `minerva serve --no-auto-rewrite`
    # if cost or latency matter more than recall.
    force_rewrite: bool = True
    # Run `agent.concept_expand` on queries whose resolved corpus has a
    # non-English original language. Adds 2–4 target-language technical
    # terms to the retrieval query so multilingual embedding retrieval
    # makes the cross-lingual concept jump (English "failures" →
    # German *Mißratenen*, etc.) that the bare MiniLM model can't do
    # on its own. Costs one extra LLM call per cross-lingual turn.
    # Disable via `minerva serve --no-concept-expand` for English-only
    # corpora or when latency / cost matter more than recall.
    enable_concept_expand: bool = True
    # `True` for `127.0.0.1` / `localhost` binds (default); `False` once
    # the operator binds to a public interface. Drives CORS handling.
    cors_wildcard: bool = True
    # When `cors_wildcard` is False, only these origins receive CORS
    # echo headers. Empty set → cross-origin clients can't read responses.
    allowed_origins: frozenset[str] = dataclasses.field(default_factory=frozenset)
    # Per-resource locks. SQLite connections aren't thread-safe; these
    # serialize access to each connection independently of the others.
    # An LLM call (network round-trip, may take tens of seconds) MUST
    # be released between locks — see `_handle_chat` / `_handle_translate`
    # in `http/handlers/` for the pattern.
    corpus_lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    conv_lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    trans_lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    # Guards `concept_cache_conn`. Independent so a cache write doesn't
    # block sibling translate / conversation traffic on the other DBs.
    concept_cache_lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    rate_limiter: _RateLimiter = dataclasses.field(default_factory=_RateLimiter)

    @property
    def lock(self) -> threading.Lock:
        """Back-compat alias for the old single-lock world. Points at
        `corpus_lock`. New code should pick the specific lock it needs."""

        return self.corpus_lock

    def to_chat_context(self) -> ChatContext:
        from ..chat_context import ChatContext

        return ChatContext(
            index_conn=self.conn,
            conversations_conn=self.conversations_conn,
            concept_cache_conn=self.concept_cache_conn,
            backend=self.backend,
            embedder=self.embedder,
            lang=self.lang,
            corpus=self.corpus,
            speaker=self.speaker,
            top_k=self.top_k,
            allow_client_rewrite=self.allow_client_rewrite,
            force_rewrite=self.force_rewrite,
            enable_concept_expand=self.enable_concept_expand,
            corpus_lock=self.corpus_lock,
            conv_lock=self.conv_lock,
            concept_cache_lock=self.concept_cache_lock,
        )


# ---------- HTTP error ----------


class _HTTPError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
