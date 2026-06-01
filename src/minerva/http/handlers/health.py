"""GET /api/health — store stats + backend name."""

from __future__ import annotations

from typing import Any

from ... import store
from ...reader import queries as reader_queries
from ..server_core import ServerDeps
from ._locks import with_corpus_lock


@with_corpus_lock
def _handle_health(deps: ServerDeps) -> dict[str, Any]:
    s = store.stats(deps.conn)
    s["backend"] = deps.backend.name
    return s


@with_corpus_lock
def _handle_landing_stats(deps: ServerDeps) -> dict[str, Any]:
    return reader_queries.landing_stats(deps.conn)
