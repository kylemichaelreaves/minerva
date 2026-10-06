"""Term-glossary read endpoints (writes via CLI only)."""

from __future__ import annotations

from typing import Any

from ... import terms_queries
from ..server_core import ServerDeps
from ._locks import with_corpus_lock


@with_corpus_lock
def _handle_term_by_id(deps: ServerDeps, term_id: int) -> dict[str, Any]:
    return terms_queries.term_by_id(deps.conn, term_id)


@with_corpus_lock
def _handle_work_occurrence_map(
    deps: ServerDeps,
    work_id: int,
    query: dict[str, str],
) -> dict[str, Any]:
    return terms_queries.work_occurrence_map(deps.conn, work_id, query)
