"""Tests for the chat HTTP surface — JSON marshalling (`chat_service`,
`citations`), history parsing, and the private `_handle_chat` /
`_handle_health` entry points. The HTTP layer itself is exercised
end-to-end by the Vitest suite in web/tests/e2e/."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from conftest import (
    StubBackend,
    _conv_conn,
    _trans_conn,
    make_deps,
    make_hit,
)

from minerva import agent, chat_service, llm
from minerva.citations import (
    _PASSAGE_PREVIEW_CHARS,
    _dominant_from_hits,
    _dominant_from_response,
    _hit_to_citation,
)
from minerva.http.handlers import _handle_chat, _handle_health
from minerva.http.serve import _MAX_REQUEST_BYTES, _parse_content_length
from minerva.http.server_core import ServerDeps, _HTTPError

# ---------- _history_from_payload ----------


def test_history_from_payload_keeps_valid_messages():
    out = chat_service.history_from_payload(
        [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
    )
    assert len(out) == 2
    assert out[0].role == "user"
    assert out[1].role == "assistant"


def test_history_from_payload_drops_unknown_roles():
    out = chat_service.history_from_payload(
        [
            {"role": "system", "content": "shouldn't appear"},
            {"role": "user", "content": "ok"},
        ]
    )
    assert [m.role for m in out] == ["user"]


def test_history_from_payload_drops_malformed_entries():
    out = chat_service.history_from_payload(
        [
            "not a dict",
            {"role": "user"},  # missing content
            {"content": "lone"},  # missing role
            {"role": "user", "content": ""},  # empty content
            {"role": "user", "content": "kept"},
        ]
    )
    assert [m.content for m in out] == ["kept"]


def test_history_from_payload_returns_empty_for_non_list():
    assert chat_service.history_from_payload(None) == []
    assert chat_service.history_from_payload("not a list") == []
    assert chat_service.history_from_payload({"role": "user", "content": "x"}) == []


# ---------- _hit_to_citation ----------


def test_hit_to_citation_includes_locator_and_score():
    hit = make_hit(text="short text")
    cite = _hit_to_citation(hit, n=3)
    assert cite["n"] == 3
    assert cite["chunk_id"] == hit.chunk_id
    assert cite["src"] == "Plato, Republic 509d Bk 6"
    assert cite["text"] == "short text"
    assert cite["score"] == 1.0


def test_hit_to_citation_truncates_long_text():
    long = "x" * 1000
    hit = make_hit(text=long)
    cite = _hit_to_citation(hit, n=1)
    assert len(cite["text"]) <= _PASSAGE_PREVIEW_CHARS + 10
    assert cite["text"].endswith("[…]")


# ---------- _dominant_from_hits ----------


def test_dominant_from_hits_plato_top():
    assert _dominant_from_hits([make_hit(corpus="plato")]) == "P"


def test_dominant_from_hits_aristotle_top():
    assert _dominant_from_hits([make_hit(corpus="aristotle", author="Aristotle")]) == "A"


def test_dominant_from_hits_empty_falls_back_to_p():
    assert _dominant_from_hits([]) == "P"


# ---------- _answer_to_json ----------


def test_answer_to_json_splits_paragraphs_on_double_newline():
    ans = agent.Answer(
        query="q",
        response="First [1].\n\nSecond paragraph.\n\nThird.",
        hits=[make_hit()],
        abstained=False,
        backend="stub",
        pinned=[],
    )
    body = chat_service.answer_to_json(ans)
    assert body["paragraphs"] == ["First [1].", "Second paragraph.", "Third."]
    assert body["dominant"] == "P"
    assert body["abstained"] is False
    assert body["backend"] == "stub"


def test_answer_to_json_preserves_response_text_verbatim():
    raw = "Hello [1].\n\nWorld."
    ans = agent.Answer(query="q", response=raw, hits=[], abstained=False, backend="stub")
    body = chat_service.answer_to_json(ans)
    assert body["response"] == raw


def test_answer_to_json_collapses_no_llm_response_to_a_placeholder():
    ans = agent.Answer(
        query="q",
        response="[1] (locator)\nfull passage text from _format_passages",
        hits=[make_hit()],
        abstained=False,
        backend="none",
    )
    body = chat_service.answer_to_json(ans)
    assert body["paragraphs"] == ["(retrieval-only mode — see citations below.)"]
    assert len(body["citations"]) == 1


def test_answer_to_json_keeps_abstain_message_intact():
    ans = agent.Answer(
        query="q",
        response="I could not find enough evidence.",
        hits=[],
        abstained=True,
        backend="none",
    )
    body = chat_service.answer_to_json(ans)
    assert body["abstained"] is True
    assert body["paragraphs"] == ["I could not find enough evidence."]
    assert body["citations"] == []


def test_answer_to_json_numbers_citations_from_one():
    hits = [make_hit(chunk_id=f"c{i}", section=f"5{i}0a") for i in range(3)]
    ans = agent.Answer(query="q", response="text", hits=hits, abstained=False, backend="stub")
    body = chat_service.answer_to_json(ans)
    assert [c["n"] for c in body["citations"]] == [1, 2, 3]


# ---------- _handle_chat / _handle_health ----------

# `_make_deps` was lifted to `conftest.make_deps` so other test files
# can share it. Kept as a local alias to minimize churn in this file.
_make_deps = make_deps


def test_handle_chat_calls_agent_with_numeric_cite_style(populated_db):
    backend = StubBackend(reply="ok [1].")
    deps = _make_deps(populated_db, backend)
    body = _handle_chat(deps, {"query": "divided line", "history": []})
    # The system prompt threaded into the LLM call must use numeric markers.
    assert "[N]" in backend.last_system()
    assert body["abstained"] is False
    assert body["backend"] == "stub"


def test_handle_chat_threads_history_into_agent(populated_db):
    backend = StubBackend(reply="ok")
    deps = _make_deps(populated_db, backend)
    _handle_chat(
        deps,
        {
            "query": "and then?",
            "history": [
                {"role": "user", "content": "What is the divided line?"},
                {"role": "assistant", "content": "Republic 509d."},
            ],
        },
    )
    msgs = backend.captured[-1][0]
    # [system, user, assistant, user]
    assert [m.role for m in msgs] == ["system", "user", "assistant", "user"]


def test_handle_chat_rejects_missing_query(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    with pytest.raises(_HTTPError) as exc_info:
        _handle_chat(deps, {})
    assert exc_info.value.status == HTTPStatus.BAD_REQUEST


def test_handle_chat_rejects_blank_query(populated_db):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend)
    with pytest.raises(_HTTPError):
        _handle_chat(deps, {"query": "   "})


def test_handle_health_includes_backend_name(populated_db):
    backend = llm.NullBackend()
    deps = _make_deps(populated_db, backend)
    body = _handle_health(deps)
    assert body["backend"] == "none"
    assert body["chunks_total"] >= 5


# ---------- Content-Length validation ----------


def test_parse_content_length_handles_missing_and_zero():
    assert _parse_content_length(None) == 0
    assert _parse_content_length("") == 0
    assert _parse_content_length("0") == 0


def test_parse_content_length_accepts_normal_value():
    assert _parse_content_length("128") == 128


def test_parse_content_length_rejects_negative():
    with pytest.raises(_HTTPError) as info:
        _parse_content_length("-1")
    assert info.value.status == HTTPStatus.BAD_REQUEST
    assert "negative" in info.value.message


def test_parse_content_length_rejects_non_numeric():
    with pytest.raises(_HTTPError) as info:
        _parse_content_length("not-a-number")
    assert info.value.status == HTTPStatus.BAD_REQUEST
    assert "invalid" in info.value.message.lower()


def test_parse_content_length_rejects_oversize():
    with pytest.raises(_HTTPError) as info:
        _parse_content_length(str(_MAX_REQUEST_BYTES + 1))
    assert info.value.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


def test_parse_content_length_strips_surrounding_whitespace():
    """Some padded-header clients send `Content-Length: 128 ` with trailing
    whitespace. Python's `int("128 ", 10)` would raise; we strip both
    sides for symmetric handling."""
    assert _parse_content_length(" 128") == 128
    assert _parse_content_length("128 ") == 128
    assert _parse_content_length(" 128 ") == 128
    # Whitespace-only header normalizes to "no body".
    assert _parse_content_length("   ") == 0
    # Negative with padding still rejected — strip first, then validate.
    with pytest.raises(_HTTPError) as info:
        _parse_content_length(" -1 ")
    assert info.value.status == HTTPStatus.BAD_REQUEST


# ---------- rewrite gating ----------


def test_handle_chat_honors_client_rewrite_when_allowed(populated_db):
    backend = StubBackend(reply="divided line")
    deps = _make_deps(populated_db, backend)
    deps = ServerDeps(
        conn=deps.conn,
        conversations_conn=deps.conversations_conn,
        translations_conn=deps.translations_conn,
        concept_cache_conn=deps.concept_cache_conn,
        backend=backend,
        embedder=None,
        lang="eng",
        corpus=None,
        speaker=None,
        top_k=3,
        static_dir=deps.static_dir,
        allow_client_rewrite=True,
        force_rewrite=False,
    )
    history = [
        {"role": "user", "content": "What is the divided line?"},
        {"role": "assistant", "content": "Republic 509d."},
    ]
    _handle_chat(deps, {"query": "and after?", "history": history, "rewrite": True})
    # Rewrite call + answer call.
    assert len(backend.captured) == 2


def test_handle_chat_ignores_client_rewrite_when_disallowed(populated_db):
    backend = StubBackend(reply="ok")
    deps = ServerDeps(
        conn=populated_db,
        conversations_conn=_conv_conn(),
        translations_conn=_trans_conn(),
        concept_cache_conn=None,
        backend=backend,
        embedder=None,
        lang="eng",
        corpus=None,
        speaker=None,
        top_k=3,
        static_dir=None,  # type: ignore[arg-type]
        allow_client_rewrite=False,
        force_rewrite=False,
    )
    history = [
        {"role": "user", "content": "What is the divided line?"},
        {"role": "assistant", "content": "Republic 509d."},
    ]
    _handle_chat(deps, {"query": "divided line", "history": history, "rewrite": True})
    # Only the answer call; rewrite was suppressed by the server flag.
    assert len(backend.captured) == 1
    assert "rewrite follow-up questions" not in backend.captured[0][0][0].content


def test_handle_chat_request_speaker_overrides_server_default(speaker_db):
    backend = StubBackend(reply="ok")
    deps = ServerDeps(
        conn=speaker_db,
        conversations_conn=_conv_conn(),
        translations_conn=_trans_conn(),
        concept_cache_conn=None,
        backend=backend,
        embedder=None,
        lang="eng",
        corpus=None,
        speaker="Socrates",  # server default
        top_k=10,
        static_dir=None,  # type: ignore[arg-type]
    )
    body = _handle_chat(
        deps,
        {
            "query": "knowledge perception",
            "speaker": "Theaetetus",  # per-request override
        },
    )
    assert all(c["speaker"] == "Theaetetus" for c in body["citations"])


def test_handle_chat_falls_back_to_deps_speaker_when_request_omits_it(speaker_db):
    backend = StubBackend(reply="ok")
    deps = ServerDeps(
        conn=speaker_db,
        conversations_conn=_conv_conn(),
        translations_conn=_trans_conn(),
        concept_cache_conn=None,
        backend=backend,
        embedder=None,
        lang="eng",
        corpus=None,
        speaker="Theaetetus",
        top_k=10,
        static_dir=None,  # type: ignore[arg-type]
    )
    body = _handle_chat(deps, {"query": "knowledge perception"})
    assert all(c["speaker"] == "Theaetetus" for c in body["citations"])


def test_hit_to_citation_includes_speaker():
    hit = make_hit()
    hit.meta["speaker"] = "Socrates"
    cite = _hit_to_citation(hit, n=1)
    assert cite["speaker"] == "Socrates"


def test_hit_to_citation_speaker_is_none_when_metadata_missing():
    hit = make_hit()
    hit.meta["speaker"] = None
    cite = _hit_to_citation(hit, n=1)
    assert cite["speaker"] is None


# ---------- retrieval_query parity with the CLI ----------


def test_handle_chat_threads_recent_user_turns_into_retrieval(populated_db):
    """The server should mirror cmd_chat's `recent_user + [q]` concat so
    follow-ups retrieve from the right neighborhood."""
    backend = StubBackend(reply="ok")
    deps = _make_deps(populated_db, backend)
    history = [
        {"role": "user", "content": "Where is the divided line introduced?"},
        {"role": "assistant", "content": "Republic 509d."},
    ]
    body = _handle_chat(deps, {"query": "what comes right after?", "history": history})
    # The retrieval_query is "Where is the divided line introduced? what comes right after?",
    # so Republic 509-510 should land in the citations even though the bare query has no "line" tokens.
    sources = [c["src"] for c in body["citations"]]
    assert any("Republic 509" in s or "Republic 510" in s for s in sources)


def test_build_retrieval_query_uses_last_two_user_turns():
    history = [
        llm.Message(role="user", content="first"),
        llm.Message(role="assistant", content="reply"),
        llm.Message(role="user", content="second"),
        llm.Message(role="assistant", content="reply2"),
        llm.Message(role="user", content="third"),
        llm.Message(role="assistant", content="reply3"),
    ]
    out = chat_service.build_retrieval_query("now", history)
    assert out == "second third now"


def test_build_retrieval_query_with_empty_history():
    assert chat_service.build_retrieval_query("hello", []) == "hello"


# ---------- rewrite flag ----------


def test_handle_chat_rewrite_flag_invokes_agent_rewrite_query(populated_db):
    # Reply has to retrieve against the corpus so the answer call fires too.
    backend = StubBackend(reply="divided line")
    deps = _make_deps(populated_db, backend)
    history = [
        {"role": "user", "content": "What is the divided line?"},
        {"role": "assistant", "content": "Republic 509d."},
    ]
    _handle_chat(
        deps,
        {
            "query": "and after?",
            "history": history,
            "rewrite": True,
        },
    )
    # Two backend calls: one for rewrite, one for the answer.
    assert len(backend.captured) == 2
    # The rewrite call has the rewrite-specific system prompt.
    assert "rewrite follow-up questions" in backend.captured[0][0][0].content


def test_handle_chat_rewrite_skipped_when_no_history(populated_db):
    backend = StubBackend(reply="ok")
    deps = _make_deps(populated_db, backend)
    _handle_chat(deps, {"query": "divided line", "rewrite": True})
    # Only the answer call; no rewrite when there's no prior history to anchor on.
    assert len(backend.captured) == 1
    # And it's the answer prompt, not the rewrite one.
    assert "rewrite follow-up questions" not in backend.captured[0][0][0].content


# ---------- auto-rewrite (server-side default) ----------


def test_handle_chat_auto_rewrites_followup_when_force_rewrite_set(populated_db):
    """The production default runs `rewrite_query` on every multi-turn
    chat without the client having to opt in. That's the whole point of
    the server-side flag — recall on follow-ups like "what about for
    Hegel?" depends on it."""

    backend = StubBackend(reply="divided line")
    deps = _make_deps(populated_db, backend, force_rewrite=True)
    history = [
        {"role": "user", "content": "What is the divided line?"},
        {"role": "assistant", "content": "Republic 509d."},
    ]
    # Note: payload omits `rewrite: true`. The server should still rewrite.
    _handle_chat(deps, {"query": "and after?", "history": history})
    assert len(backend.captured) == 2
    assert "rewrite follow-up questions" in backend.captured[0][0][0].content


def test_handle_chat_auto_rewrite_skipped_when_no_history(populated_db):
    """force_rewrite still needs a prior turn to be meaningful — first-
    turn questions go straight to retrieval."""

    backend = StubBackend(reply="ok")
    deps = _make_deps(populated_db, backend, force_rewrite=True)
    _handle_chat(deps, {"query": "divided line"})
    assert len(backend.captured) == 1
    assert "rewrite follow-up questions" not in backend.captured[0][0][0].content


def test_handle_chat_auto_rewrite_off_leaves_followups_unrewritten(populated_db):
    """When the operator disables auto-rewrite (--no-auto-rewrite), and
    the client doesn't ask for rewrite either, follow-ups fall back to
    the naive concat-history retrieval query."""

    backend = StubBackend(reply="ok")
    deps = _make_deps(populated_db, backend, force_rewrite=False)
    history = [
        {"role": "user", "content": "What is the divided line?"},
        {"role": "assistant", "content": "Republic 509d."},
    ]
    _handle_chat(deps, {"query": "and after?", "history": history})
    assert len(backend.captured) == 1
    assert "rewrite follow-up questions" not in backend.captured[0][0][0].content


# ---------- author-aware corpus routing ----------


def test_handle_chat_routes_to_named_author_corpus(populated_db):
    """When the query unambiguously names one canonical author and the
    operator hasn't pinned a corpus, retrieval should scope to that
    author so follow-ups don't fight over top_k slots."""

    backend = StubBackend(reply="ok")
    deps = _make_deps(populated_db, backend)
    body = _handle_chat(deps, {"query": "What does Aristotle say about ergon?"})
    # `src` locators look like "Aristotle, Nicomachean Ethics 1097b" —
    # all returned citations should start with the named author.
    srcs = [c["src"] for c in body["citations"]]
    assert srcs, "expected at least one Aristotle citation"
    assert all(s.startswith("Aristotle") for s in srcs)


def test_handle_chat_operator_corpus_overrides_detection(populated_db):
    """`deps.corpus` is a hard filter set by the operator (e.g. `serve
    --corpus plato`). Even if the user types "Aristotle," retrieval
    must stay inside the operator's scope."""

    backend = StubBackend(reply="ok")
    deps = _make_deps(populated_db, backend, corpus="plato")
    body = _handle_chat(deps, {"query": "What does Aristotle say about ergon?"})
    # Operator pin keeps us in Plato even though "Aristotle" appears in
    # the query. No Aristotle citations should leak in.
    srcs = [c["src"] for c in body["citations"]]
    assert not any(s.startswith("Aristotle") for s in srcs)


def test_handle_chat_multi_author_query_does_not_narrow(populated_db):
    """When the query names two authors the detector returns None so the
    retriever can pull from both. A naive "first author wins" would
    silently drop half the question."""

    backend = StubBackend(reply="ok")
    deps = _make_deps(populated_db, backend)
    # `top_k=3` (the test default) + only one Aristotle chunk in the
    # fixture means we can't deterministically force a mix. Instead
    # assert the detector itself returns None for this phrasing — the
    # handler trusts that signal.
    assert agent.detect_corpus("Compare Plato and Aristotle on virtue") is None


# ---------- pinned_chunk_ids ----------


def test_handle_chat_resolves_pinned_chunk_ids_into_hits(populated_db):
    backend = StubBackend(reply="ok")
    deps = _make_deps(populated_db, backend)
    body = _handle_chat(
        deps,
        {
            "query": "anchored discussion",
            "pinned_chunk_ids": ["rep-509d", "rep-510a"],
        },
    )
    pinned_cites = [c for c in body["citations"] if c.get("pinned")]
    assert len(pinned_cites) == 2
    pinned_ids = {c["chunk_id"] for c in pinned_cites}
    assert pinned_ids == {"rep-509d", "rep-510a"}


def test_handle_chat_silently_drops_unknown_pinned_ids(populated_db):
    backend = StubBackend(reply="ok")
    deps = _make_deps(populated_db, backend)
    body = _handle_chat(
        deps,
        {
            "query": "anchored",
            "pinned_chunk_ids": ["rep-509d", "does-not-exist"],
        },
    )
    pinned_ids = {c["chunk_id"] for c in body["citations"] if c.get("pinned")}
    assert pinned_ids == {"rep-509d"}


def test_pinned_ids_from_payload_filters_garbage():
    out = chat_service.pinned_ids_from_payload(["a", "", None, "b", 42, "a", "c"])
    # de-duped, strings only
    assert out == ["a", "b", "c"]


def test_pinned_ids_from_payload_returns_empty_for_non_list():
    assert chat_service.pinned_ids_from_payload(None) == []
    assert chat_service.pinned_ids_from_payload("a,b,c") == []


# ---------- weighted dominant heuristic ----------


def test_dominant_from_hits_weighted_vote_overrides_top_hit():
    """One Plato hit at the top can be outweighed by Aristotle hits below."""
    hits = [
        make_hit(corpus="plato", author="Plato", work="Republic"),
        make_hit(
            corpus="aristotle", author="Aristotle", work="Nicomachean Ethics", section="1097a"
        ),
        make_hit(
            corpus="aristotle", author="Aristotle", work="Nicomachean Ethics", section="1097b"
        ),
    ]
    assert _dominant_from_hits(hits) == "A"


def test_max_request_bytes_is_finite_and_sane():
    # Sanity: the limit should exist and be small enough to reject obvious abuse.
    assert isinstance(_MAX_REQUEST_BYTES, int)
    assert 0 < _MAX_REQUEST_BYTES <= 10 * 1024 * 1024  # ≤ 10 MiB


def test_dominant_from_hits_recognizes_hegel():
    hits = [make_hit(corpus="hegel", author="Hegel", work="PR", section="§258")]
    assert _dominant_from_hits(hits) == "H"


def test_dominant_from_hits_recognizes_kant():
    hits = [make_hit(corpus="kant", author="Kant", work="KrV", section="A19")]
    assert _dominant_from_hits(hits) == "K"


def test_dominant_from_hits_breaks_ties_with_top_hit_corpus():
    """When two corpora tie on count, the top hit's corpus wins so a strong
    Hegel result isn't shadowed by an equal number of Plato hits below."""
    hits = [
        make_hit(corpus="hegel", author="Hegel", work="PhG", section="¶1"),
        make_hit(corpus="plato", author="Plato", work="Republic", section="509a"),
        make_hit(corpus="hegel", author="Hegel", work="PhG", section="¶2"),
        make_hit(corpus="plato", author="Plato", work="Republic", section="509b"),
    ]
    # 2 hegel, 2 plato within top_n=4; top hit is Hegel → H wins.
    assert _dominant_from_hits(hits, top_n=4) == "H"


def test_dominant_from_hits_falls_back_to_p_for_unknown_corpus():
    hits = [make_hit(corpus="totally_unknown_corpus", author="Nobody", work="X")]
    assert _dominant_from_hits(hits) == "P"


def test_dominant_from_hits_respects_top_n_window():
    hits = [
        make_hit(corpus="plato", author="Plato", work="Republic", section="509a"),
        make_hit(corpus="plato", author="Plato", work="Republic", section="509b"),
        make_hit(corpus="aristotle", author="Aristotle", work="NE", section="1"),
        make_hit(corpus="aristotle", author="Aristotle", work="NE", section="2"),
        make_hit(corpus="aristotle", author="Aristotle", work="NE", section="3"),
    ]
    # Default top_n=3 → 2 Plato vs 1 Aristotle → Plato
    assert _dominant_from_hits(hits) == "P"
    # Larger window pulls in 3 Aristotle, only 2 Plato → Aristotle
    assert _dominant_from_hits(hits, top_n=5) == "A"


# ---------- _dominant_from_response (cited-hit dominance) ----------


def test_dominant_from_response_follows_cited_hits_not_retrieval_rank():
    """The fix for the "Aristotle dominant" mislabel: when retrieval
    ranks two Aristotle chunks at the top but the LLM only cites the
    four Plato chunks below, dominance should reflect what the answer
    actually quotes."""

    hits = [
        make_hit(chunk_id="a1", corpus="aristotle", author="Aristotle", work="Politics"),
        make_hit(chunk_id="a2", corpus="aristotle", author="Aristotle", work="Ath. Const."),
        make_hit(chunk_id="p1", corpus="plato", author="Plato", work="Republic", section="557a"),
        make_hit(chunk_id="p2", corpus="plato", author="Plato", work="Republic", section="562a"),
        make_hit(chunk_id="p3", corpus="plato", author="Plato", work="Republic", section="565a"),
        make_hit(chunk_id="p4", corpus="plato", author="Plato", work="Republic", section="445a"),
    ]
    # Hits are numbered 1..6 in `_answer_to_json` (no pinned). The
    # response cites only the Plato passages (#3, #4, #5, #6).
    response = (
        "Democracy is unstable [3]. The poor displace the rich [5]. "
        "Tyranny grows from democracy [4]. The democratic soul is disordered [6]."
    )
    assert _dominant_from_response(response, pinned=[], hits=hits) == "P"


def test_dominant_from_response_falls_back_to_retrieval_when_no_cites():
    """Abstentions and null-backend mode produce responses with no [N]
    markers — fall back to top-3 retrieval ranking so the badge still
    reflects something useful."""

    hits = [
        make_hit(corpus="aristotle", author="Aristotle", work="Politics"),
        make_hit(corpus="aristotle", author="Aristotle", work="Ath. Const."),
        make_hit(corpus="plato", author="Plato", work="Republic"),
    ]
    response = "I could not find enough evidence in the indexed corpus."
    assert _dominant_from_response(response, pinned=[], hits=hits) == "A"


def test_dominant_from_response_counts_pinned_in_numbering():
    """`_answer_to_json` numbers pinned hits first, then retrieval hits.
    `_dominant_from_response` must use the same indexing so [1] points
    at the first pinned hit, not the first retrieval hit."""

    pinned = [make_hit(corpus="hegel", author="Hegel", work="PR", section="§258")]
    hits = [
        make_hit(corpus="plato", author="Plato", work="Republic", section="509a"),
        make_hit(corpus="plato", author="Plato", work="Republic", section="509b"),
    ]
    # [1] = the pinned Hegel chunk; LLM only cites it.
    response = "On the state, see [1]."
    assert _dominant_from_response(response, pinned=pinned, hits=hits) == "H"


def test_dominant_from_response_ignores_out_of_range_cites():
    """Defensive: if the LLM hallucinates a [99], skip it rather than
    crashing or counting it."""

    hits = [
        make_hit(corpus="plato", author="Plato", work="Republic"),
        make_hit(corpus="aristotle", author="Aristotle", work="Politics"),
    ]
    response = "Plato [1] is also discussed in [99]."
    assert _dominant_from_response(response, pinned=[], hits=hits) == "P"


# ---------- missing_pinned_ids surfacing ----------


def test_handle_chat_surfaces_unknown_pinned_ids(populated_db):
    backend = StubBackend(reply="ok")
    deps = _make_deps(populated_db, backend)
    body = _handle_chat(
        deps,
        {
            "query": "anchored discussion",
            "pinned_chunk_ids": ["rep-509d", "totally-fake-id"],
        },
    )
    # The valid pin is resolved; the fake one is reported back so the
    # client can drop it from local state.
    assert "missing_pinned_ids" in body
    assert body["missing_pinned_ids"] == ["totally-fake-id"]


def test_handle_chat_omits_missing_pinned_ids_when_all_resolve(populated_db):
    backend = StubBackend(reply="ok")
    deps = _make_deps(populated_db, backend)
    body = _handle_chat(
        deps,
        {
            "query": "anchored discussion",
            "pinned_chunk_ids": ["rep-509d"],
        },
    )
    assert "missing_pinned_ids" not in body
