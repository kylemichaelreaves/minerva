"""HTTP route tables for the Minerva API."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote

from .handlers import (
    _handle_chat,
    _handle_chunk_context,
    _handle_chunk_syntax,
    _handle_concordance_index,
    _handle_concordance_lemma,
    _handle_conversation_delete,
    _handle_conversation_get,
    _handle_conversations_list,
    _handle_health,
    _handle_landing_stats,
    _handle_lemma_highlights,
    _handle_metrics_requests,
    _handle_metrics_series,
    _handle_metrics_summary,
    _handle_network_summary,
    _handle_reference_update,
    _handle_references_list,
    _handle_references_sources,
    _handle_review_queue,
    _handle_syntax_correction_create,
    _handle_syntax_correction_delete,
    _handle_term_by_id,
    _handle_translate,
    _handle_word_lookup,
    _handle_work_occurrence_map,
    _handle_work_range,
    _handle_work_range_by_slug,
    _handle_work_references_map,
    _handle_works_list,
)
from .server_core import ServerDeps

_CONVERSATION_PATH_RE = re.compile(r"^/api/conversations/([^/]+)$")
_WORK_PATH_RE = re.compile(r"^/api/works/(.+)$")
# Readable reader URLs (#602). Must be registered AFTER every
# `/api/works/<int>/<name>` route — this pattern matches those too — and
# BEFORE the greedy `_WORK_PATH_RE`, which would swallow the pair.
_WORK_SLUG_PAIR_RE = re.compile(r"^/api/works/([^/]+)/([^/]+)$")
_CHUNK_CONTEXT_PATH_RE = re.compile(r"^/api/chunks/([^/]+)/context$")
_CHUNK_SYNTAX_PATH_RE = re.compile(r"^/api/chunks/([^/]+)/syntax$")
_CHUNK_SYNTAX_CORRECTIONS_RE = re.compile(r"^/api/chunks/([^/]+)/syntax/corrections$")
# Corrections are addressed by their own id, not by chunk: the client holds
# the id it got back from the POST, and undo should not have to know where the
# row came from.
_SYNTAX_CORRECTION_BY_ID_RE = re.compile(r"^/api/syntax/corrections/(\d+)$")
_TERM_BY_ID_RE = re.compile(r"^/api/terms/(\d+)$")
_WORK_OCCURRENCE_MAP_RE = re.compile(r"^/api/works/(\d+)/occurrence_map$")
_WORK_LEMMA_HIGHLIGHTS_RE = re.compile(r"^/api/works/(\d+)/lemma_highlights$")
_WORD_LOOKUP_PATH = "/api/words/lookup"
_WORK_REFERENCES_MAP_RE = re.compile(r"^/api/works/(\d+)/references_map$")
_REFERENCES_LIST_PATH = "/api/references"
_REFERENCES_SOURCES_PATH = "/api/references/sources"
_REVIEW_QUEUE_PATH = "/api/references/review_queue"
_REFERENCE_BY_ID_RE = re.compile(r"^/api/references/(\d+)$")
_NETWORK_SUMMARY_PATH = "/api/network/summary"
_CONCORDANCE_INDEX_PATH = "/api/concordance/index"
_CONCORDANCE_LEMMA_PATH = "/api/concordance/lemma"

Route = tuple[Any, str, Callable[..., Any]]


def _match_route(
    path: str,
    routes: tuple[Route, ...],
) -> tuple[str, Callable[..., Any], tuple[Any, ...]] | None:
    for matcher, label, handler in routes:
        if isinstance(matcher, str):
            if path != matcher:
                continue
            return label, handler, ()
        m = matcher.match(path)
        if m is None:
            continue
        return label, handler, (m,)
    return None


def build_get_routes(
    deps: ServerDeps,
    qs: Callable[[], dict[str, str]],
) -> tuple[Route, ...]:
    """Return the ordered GET route table for *deps*."""

    return (
        ("/api/health", "health", lambda: _handle_health(deps)),
        ("/api/landing/stats", "landing stats", lambda: _handle_landing_stats(deps)),
        ("/api/conversations", "conversations list", lambda: _handle_conversations_list(deps)),
        (
            _CONVERSATION_PATH_RE,
            "conversation get",
            lambda m: _handle_conversation_get(deps, m.group(1)),
        ),
        ("/api/works", "works list", lambda: _handle_works_list(deps)),
        (_WORD_LOOKUP_PATH, "word lookup", lambda: _handle_word_lookup(deps, qs())),
        (
            _CHUNK_CONTEXT_PATH_RE,
            "chunk context",
            lambda m: _handle_chunk_context(deps, unquote(m.group(1)), qs()),
        ),
        (
            _CHUNK_SYNTAX_PATH_RE,
            "chunk syntax",
            lambda m: _handle_chunk_syntax(deps, unquote(m.group(1))),
        ),
        (
            _WORK_REFERENCES_MAP_RE,
            "work references map",
            lambda m: _handle_work_references_map(deps, int(m.group(1)), qs()),
        ),
        (_REFERENCES_LIST_PATH, "references list", lambda: _handle_references_list(deps, qs())),
        (
            _REFERENCES_SOURCES_PATH,
            "references sources",
            lambda: _handle_references_sources(deps, qs()),
        ),
        (_REVIEW_QUEUE_PATH, "review queue", lambda: _handle_review_queue(deps, qs())),
        (_NETWORK_SUMMARY_PATH, "network summary", lambda: _handle_network_summary(deps, qs())),
        (
            _CONCORDANCE_INDEX_PATH,
            "concordance index",
            lambda: _handle_concordance_index(deps, qs()),
        ),
        (
            _CONCORDANCE_LEMMA_PATH,
            "concordance lemma",
            lambda: _handle_concordance_lemma(deps, qs()),
        ),
        (
            _WORK_OCCURRENCE_MAP_RE,
            "work-occurrence-map",
            lambda m: _handle_work_occurrence_map(deps, int(m.group(1)), qs()),
        ),
        (
            _WORK_LEMMA_HIGHLIGHTS_RE,
            "lemma-highlights",
            lambda m: _handle_lemma_highlights(deps, int(m.group(1)), qs()),
        ),
        (
            _TERM_BY_ID_RE,
            "term-by-id",
            lambda m: _handle_term_by_id(deps, int(m.group(1))),
        ),
        (
            "/api/metrics/summary",
            "metrics summary",
            lambda: _handle_metrics_summary(deps, qs()),
        ),
        (
            "/api/metrics/series",
            "metrics series",
            lambda: _handle_metrics_series(deps, qs()),
        ),
        (
            "/api/metrics/requests",
            "metrics requests",
            lambda: _handle_metrics_requests(deps, qs()),
        ),
        (
            _WORK_SLUG_PAIR_RE,
            "work range by slug",
            lambda m: _handle_work_range_by_slug(
                deps, unquote(m.group(1)), unquote(m.group(2)), qs()
            ),
        ),
        (
            _WORK_PATH_RE,
            "work range",
            lambda m: _handle_work_range(deps, unquote(m.group(1)), qs()),
        ),
    )


def build_post_routes(deps: ServerDeps) -> tuple[Route, ...]:
    return (
        ("/api/chat", "chat", lambda payload: _handle_chat(deps, payload)),
        ("/api/translate", "translate", lambda payload: _handle_translate(deps, payload)),
        (
            _CHUNK_SYNTAX_CORRECTIONS_RE,
            "syntax correction create",
            lambda m, payload: _handle_syntax_correction_create(deps, unquote(m.group(1)), payload),
        ),
    )


def build_patch_routes(deps: ServerDeps) -> tuple[Route, ...]:
    return (
        (
            _REFERENCE_BY_ID_RE,
            "reference update",
            lambda m, payload: _handle_reference_update(deps, int(m.group(1)), payload),
        ),
    )


def build_delete_routes(deps: ServerDeps) -> tuple[Route, ...]:
    return (
        (
            _CONVERSATION_PATH_RE,
            "conversation delete",
            lambda m: _handle_conversation_delete(deps, m.group(1)),
        ),
        (
            _SYNTAX_CORRECTION_BY_ID_RE,
            "syntax correction delete",
            lambda m: _handle_syntax_correction_delete(deps, int(m.group(1))),
        ),
    )


__all__ = [
    "_CHUNK_SYNTAX_CORRECTIONS_RE",
    "_CHUNK_SYNTAX_PATH_RE",
    "_CONVERSATION_PATH_RE",
    "_REFERENCE_BY_ID_RE",
    "_SYNTAX_CORRECTION_BY_ID_RE",
    "Route",
    "_match_route",
    "build_delete_routes",
    "build_get_routes",
    "build_patch_routes",
    "build_post_routes",
]
