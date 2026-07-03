"""Tests for SSE streaming chat handler."""

from __future__ import annotations

from conftest import StubBackend
from conftest import make_deps as _make_deps

from minerva import server


def _collect_stream(deps, payload):
    return list(server._handle_chat_stream(deps, {**payload, "stream": True}))


def test_handle_chat_stream_emits_meta_delta_done(populated_db, conversations_conn):
    backend = StubBackend(reply="Hello world [1].")
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    events = _collect_stream(deps, {"query": "What is justice?"})
    names = [n for n, _ in events]
    assert names[0] == "meta"
    assert "delta" in names
    assert names[-1] == "done"

    meta = events[0][1]
    assert meta["conversation_id"]
    assert meta["title"] == "What is justice"
    assert isinstance(meta["citations"], list)

    done = events[-1][1]
    assert "paragraphs" in done
    assert done["dominant"]

    cid = meta["conversation_id"]
    rows = conversations_conn.execute(
        "SELECT role FROM messages WHERE conversation_id=? ORDER BY id", (cid,)
    ).fetchall()
    assert [r[0] for r in rows] == ["user", "assistant"]


def test_handle_chat_stream_abstain_skips_deltas(populated_db, conversations_conn, monkeypatch):
    """Weak retrieval abstains: meta then done, no token deltas."""

    from minerva import agent

    weak = agent.RetrievalResult(hits=[], pinned=[], abstain=True)
    monkeypatch.setattr(
        "minerva.http.handlers.chat.agent.retrieve_passages",
        lambda **kwargs: weak,
    )
    backend = StubBackend(reply="should not be called")
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    events = _collect_stream(deps, {"query": "zxqv nonsense query"})
    names = [n for n, _ in events]
    assert names == ["meta", "done"]
    assert events[0][1]["abstained"] is True
    assert "delta" not in names


def test_handle_chat_stream_rolls_back_on_llm_failure(populated_db, conversations_conn):
    failing = StubBackend(reply=RuntimeError("simulated upstream"))
    deps = _make_deps(populated_db, failing, conversations_conn=conversations_conn)
    events = _collect_stream(deps, {"query": "What is the divided line?"})
    assert events[-1][0] == "error"
    assert conversations_conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0


def test_handle_chat_stream_persists_same_as_blocking(populated_db, conversations_conn):
    backend = StubBackend(reply="Same reply [1].")
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    blocking = server._handle_chat(deps, {"query": "divided line"})
    events = _collect_stream(deps, {"query": "divided line follow-up", "conversation_id": blocking["conversation_id"]})
    done = events[-1][1]
    cid = blocking["conversation_id"]
    rows = conversations_conn.execute(
        "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id",
        (cid,),
    ).fetchall()
    assert len(rows) == 4
    assert rows[-1][0] == "assistant"
    assert "Same reply" in rows[-1][1] or "reply" in rows[-1][1]


def test_handle_chat_stream_keeps_turn_on_client_disconnect(populated_db, conversations_conn):
    """Closing the SSE generator after persist must keep user + assistant rows."""
    backend = StubBackend(reply="Hello world [1].")
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    gen = server._handle_chat_stream(deps, {"query": "What is justice?"})
    next(gen)  # meta
    while (
        conversations_conn.execute(
            "SELECT COUNT(*) FROM messages WHERE role='assistant'"
        ).fetchone()[0]
        == 0
    ):
        next(gen)
    gen.close()

    rows = conversations_conn.execute(
        "SELECT role FROM messages ORDER BY id"
    ).fetchall()
    assert [r[0] for r in rows] == ["user", "assistant"]


def test_handle_chat_stream_validation_errors_raise_before_first_event(
    populated_db, conversations_conn
):
    """Regression: prepare_chat_turn used to run lazily inside the
    generator, so validation errors surfaced only on the first next() —
    AFTER the server had already written the 200 SSE headers, and the
    error JSON became a second status line inside the open stream. The
    call itself must raise, before any event is produced."""

    import pytest

    from minerva.http.serve import _HTTPError

    backend = StubBackend(reply="unused")
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)

    # Missing query → BadRequest at call time, not at iteration time.
    with pytest.raises(_HTTPError) as info:
        server._handle_chat_stream(deps, {"stream": True})
    assert info.value.status == 400

    # Well-formed but unknown conversation id → NotFound at call time.
    with pytest.raises(_HTTPError) as info:
        server._handle_chat_stream(
            deps, {"stream": True, "query": "hi", "conversation_id": "missing-cid"}
        )
    assert info.value.status == 404
