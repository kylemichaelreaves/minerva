"""Tests for SSE streaming chat handler."""

from __future__ import annotations

from conftest import StubBackend
from conftest import make_deps as _make_deps

from minerva.http.handlers import _handle_chat, _handle_chat_stream


def _collect_stream(deps, payload):
    return list(_handle_chat_stream(deps, {**payload, "stream": True}))


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
    """The streamed path must return and persist what the blocking path does.

    This test previously asserted neither half of its own name (#163): it
    bound the terminal ``done`` payload to a local and never read it, so no
    stream-vs-blocking comparison happened at all. It also ran the two paths
    against *different* queries in one conversation, so they were not
    comparable even in principle, and closed on
    ``"Same reply" in s or "reply" in s`` — a disjunction whose first operand
    implies its second, leaving only "the word 'reply' appears somewhere".
    Nothing here would have failed had the two paths diverged completely.

    Now: same query, one conversation each, and every field the two paths
    share is compared for equality.
    """

    query = "What is the divided line?"
    # Two paragraphs, deliberately. With a single-paragraph reply the
    # persisted-content assertion below is vacuous — `"\n\n".join([p])` and
    # `" ".join([p])` are the same string, so a regression in the paragraph
    # separator would pass unnoticed. Verified by mutating the separator in
    # `_persist_assistant_turn`: with one paragraph the test stayed green,
    # with two it fails.
    reply = "Same reply [1].\n\nSecond paragraph [1]."

    blocking_backend = StubBackend(reply=reply)
    blocking = _handle_chat(
        _make_deps(populated_db, blocking_backend, conversations_conn=conversations_conn),
        {"query": query},
    )
    assert len(blocking["paragraphs"]) > 1, "fixture must produce >1 paragraph"

    stream_backend = StubBackend(reply=reply)
    events = _collect_stream(
        _make_deps(populated_db, stream_backend, conversations_conn=conversations_conn),
        {"query": query},
    )
    meta = events[0][1]
    done = events[-1][1]

    # Distinct conversations, so the persisted rows can be compared without
    # one path's turns being read as the other's.
    assert meta["conversation_id"] != blocking["conversation_id"]

    # The `done` event carries the answer body; compare every key it shares
    # with the blocking response.
    for key in ("response", "paragraphs", "dominant"):
        assert done[key] == blocking[key], f"{key} differs between stream and blocking"

    # `meta` carries what the blocking body returns alongside the answer.
    assert meta["citations"] == blocking["citations"]
    assert meta["abstained"] == blocking["abstained"]

    # And both must persist the same assistant content, since that is what a
    # reloaded conversation replays.
    def _rows(cid):
        return conversations_conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id",
            (cid,),
        ).fetchall()

    blocking_rows = _rows(blocking["conversation_id"])
    stream_rows = _rows(meta["conversation_id"])

    assert [r[0] for r in blocking_rows] == ["user", "assistant"]
    assert [r[0] for r in stream_rows] == ["user", "assistant"]
    assert stream_rows[-1][1] == blocking_rows[-1][1]
    assert blocking_rows[-1][1] == "\n\n".join(blocking["paragraphs"])


def test_handle_chat_stream_keeps_turn_on_client_disconnect(populated_db, conversations_conn):
    """Closing the SSE generator after persist must keep user + assistant rows."""
    backend = StubBackend(reply="Hello world [1].")
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    gen = _handle_chat_stream(deps, {"query": "What is justice?"})
    next(gen)  # meta
    while (
        conversations_conn.execute(
            "SELECT COUNT(*) FROM messages WHERE role='assistant'"
        ).fetchone()[0]
        == 0
    ):
        next(gen)
    gen.close()

    rows = conversations_conn.execute("SELECT role FROM messages ORDER BY id").fetchall()
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
        _handle_chat_stream(deps, {"stream": True})
    assert info.value.status == 400

    # Well-formed but unknown conversation id → NotFound at call time.
    with pytest.raises(_HTTPError) as info:
        _handle_chat_stream(deps, {"stream": True, "query": "hi", "conversation_id": "missing-cid"})
    assert info.value.status == 404
