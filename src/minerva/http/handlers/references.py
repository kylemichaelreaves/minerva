"""Cross-reference read + curator PATCH endpoints."""

from __future__ import annotations

from typing import Any

from ...refs import queries as refs_queries
from ..server_core import ServerDeps
from ._locks import with_corpus_lock


@with_corpus_lock
def _handle_work_references_map(
    deps: ServerDeps,
    work_id: int,
    query: dict[str, str],
) -> dict[str, Any]:
    return refs_queries.work_references_map(deps.conn, work_id, query)


@with_corpus_lock
def _handle_references_list(
    deps: ServerDeps,
    query: dict[str, str],
) -> dict[str, Any]:
    return refs_queries.references_list(deps.conn, query)


@with_corpus_lock
def _handle_references_sources(
    deps: ServerDeps,
    query: dict[str, str],
) -> dict[str, Any]:
    return refs_queries.references_sources(deps.conn, query)


@with_corpus_lock
def _handle_network_summary(
    deps: ServerDeps,
    query: dict[str, str],
) -> dict[str, Any]:
    return refs_queries.network_summary(deps.conn, query)


@with_corpus_lock
def _handle_review_queue(
    deps: ServerDeps,
    query: dict[str, str],
) -> dict[str, Any]:
    return refs_queries.review_queue(deps.conn, query)


@with_corpus_lock
def _handle_reference_update(
    deps: ServerDeps,
    reference_id: int,
    body: dict[str, Any],
) -> dict[str, Any]:
    """PATCH /api/references/:id — curator update."""

    status, note, update_note = refs_queries.parse_reference_update_body(body)
    return refs_queries.update_reference(
        deps.conn,
        reference_id,
        status=status,
        note=note,
        update_note=update_note,
    )
