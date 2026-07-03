"""Chat service unit tests (no HTTP)."""

from __future__ import annotations

import pytest

from minerva import agent, chat_service
from minerva.errors import PayloadTooLargeError
from minerva.http.handlers import citations


def test_citations_from_retrieval_deduped():
    retrieval = agent.RetrievalResult(hits=[], pinned=[], abstain=False)
    assert chat_service.citations_from_retrieval(retrieval) == []


def test_citations_from_hits_matches_citations_module():
    # Empty lists should agree between modules.
    assert citations.citations_from_hits([], []) == []


def test_history_from_payload_skips_invalid():
    assert chat_service.history_from_payload(None) == []
    assert chat_service.history_from_payload([{"role": "user", "content": "hi"}]) != []


def test_validate_history_rejects_too_many_turns():
    from minerva import llm

    history = [llm.Message(role="user", content="x") for _ in range(41)]
    with pytest.raises(PayloadTooLargeError):
        chat_service._validate_history(history)


def test_validate_history_rejects_oversize_content():
    from minerva import llm

    history = [llm.Message(role="user", content="a" * (chat_service._MAX_HISTORY_CHARS + 1))]
    with pytest.raises(PayloadTooLargeError):
        chat_service._validate_history(history)


def test_parse_chat_payload_rejects_oversize_query(populated_db):
    from conftest import StubBackend, make_deps

    from minerva.chat_context import ChatContext

    deps = make_deps(populated_db, StubBackend())
    ctx = ChatContext(
        index_conn=deps.conn,
        conversations_conn=deps.conversations_conn,
        concept_cache_conn=deps.concept_cache_conn,
        backend=deps.backend,
        embedder=deps.embedder,
        lang=deps.lang,
        corpus=deps.corpus,
        speaker=deps.speaker,
        top_k=deps.top_k,
        allow_client_rewrite=deps.allow_client_rewrite,
        force_rewrite=deps.force_rewrite,
        enable_concept_expand=deps.enable_concept_expand,
    )
    huge = "x" * (chat_service._MAX_QUERY_CHARS + 1)
    with pytest.raises(PayloadTooLargeError):
        chat_service.parse_chat_payload(ctx, {"query": huge})
