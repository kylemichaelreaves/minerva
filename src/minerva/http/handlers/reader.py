"""Reader endpoints: works list, work range, chunk context."""

from __future__ import annotations

from typing import Any

from ...errors import NotFoundError
from ...reader import queries as reader_queries
from ...reader.slugs import resolve_title_slug, resolve_work_slug
from ..server_core import ServerDeps
from ._locks import with_corpus_lock


@with_corpus_lock
def _handle_works_list(deps: ServerDeps) -> dict[str, Any]:
    return reader_queries.works_list(deps.conn)


@with_corpus_lock
def _handle_work_range(deps: ServerDeps, work_id: str, query: dict[str, str]) -> dict[str, Any]:
    """`/api/works/<work>`, where `<work>` is an exact title OR a title slug.

    The exact title is tried first and is never reinterpreted — this shape
    predates slugs (#602) and has callers older than them. The slug pass is a
    fallback on the failure path only, so it costs nothing on a hit; it exists
    because a citation deep-link carries a title but no author and therefore
    emits the one-segment form.
    """

    try:
        return reader_queries.work_range(deps.conn, work_id, query)
    except NotFoundError:
        title = resolve_title_slug(deps.conn, work_id)
        if title is None or title == work_id:
            raise
        return reader_queries.work_range(deps.conn, title, query)


@with_corpus_lock
def _handle_work_range_by_slug(
    deps: ServerDeps,
    author_slug: str,
    title_slug: str,
    query: dict[str, str],
) -> dict[str, Any]:
    """`/api/works/<authorSlug>/<titleSlug>` — the readable reader URL (#602).

    The author moves out of `?author=` and into identity, so the pair is
    resolved here and `work_range` is handed the canonical strings it has
    always taken. Anything that resolves off the QUERY rather than the path —
    `around=`, `edition=` — is untouched by this and keeps its precedence.
    """

    author, title = resolve_work_slug(deps.conn, author_slug, title_slug)
    return reader_queries.work_range(deps.conn, title, {**query, "author": author})


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
