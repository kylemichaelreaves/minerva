"""Reader endpoints: works list, work range, chunk context."""

from __future__ import annotations

from typing import Any

from ...reader import queries as reader_queries
from ..server_core import ServerDeps
from ._locks import with_corpus_lock


@with_corpus_lock
def _handle_works_list(deps: ServerDeps) -> dict[str, Any]:
    return reader_queries.works_list(deps.conn)


@with_corpus_lock
def _handle_work_range(deps: ServerDeps, work_id: str, query: dict[str, str]) -> dict[str, Any]:
    return reader_queries.work_range(deps.conn, work_id, query)


@with_corpus_lock
def _handle_word_lookup(deps: ServerDeps, query: dict[str, str]) -> dict[str, Any]:
    return reader_queries.word_lookup(deps.conn, query)


@with_corpus_lock
def _handle_lemma_highlights(
    deps: ServerDeps,
    work_id: int,
    query: dict[str, str],
) -> dict[str, Any]:
    return reader_queries.lemma_highlights(deps.conn, work_id, query)


@with_corpus_lock
def _handle_chunk_context(
    deps: ServerDeps,
    chunk_id: str,
    query: dict[str, str],
) -> dict[str, Any]:
    return reader_queries.chunk_context(deps.conn, chunk_id, query)
