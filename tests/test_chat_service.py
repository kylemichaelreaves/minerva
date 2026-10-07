"""Chat service unit tests (no HTTP)."""

from __future__ import annotations

import pytest

from minerva import agent, chat_service, citations, retrieve
from minerva.errors import PayloadTooLargeError


def test_citations_from_retrieval_deduped():
    retrieval = agent.RetrievalResult(hits=[], pinned=[], abstain=False)
    assert chat_service.citations_from_retrieval(retrieval) == []


def _hit(chunk_id: str) -> retrieve.Hit:
    meta = {"text": f"text of {chunk_id}", "corpus": "plato", "work": "Republic", "section": "1"}
    return retrieve.Hit(chunk_id=chunk_id, score=0.5, bm25=0.0, cosine=0.0, meta=meta)


def test_citations_from_hits_numbers_pinned_first_then_hits():
    # Replaces a test that asserted `[] == []` through a re-export shim (#782).
    out = citations.citations_from_hits([_hit("p1")], [_hit("h1"), _hit("h2")])
    assert [(c["n"], c["chunk_id"], c["pinned"]) for c in out] == [
        (1, "p1", True),
        (2, "h1", False),
        (3, "h2", False),
    ]


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
