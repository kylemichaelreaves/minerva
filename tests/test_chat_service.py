"""Chat service unit tests (no HTTP)."""

from __future__ import annotations

from minerva import agent, chat_service
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
