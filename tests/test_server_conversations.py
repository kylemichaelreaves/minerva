"""Server tests for conversation persistence: the `/api/conversations`
endpoint family plus the side-effects of `_handle_chat` on the
conversations DB (title minting, message appending). Split from
`test_server.py` to keep that file focused on chat behaviour."""

from __future__ import annotations

import json
from http import HTTPStatus

import pytest
from conftest import StubBackend
from conftest import make_deps as _make_deps

from minerva import conversations
from minerva.http.handlers import (
    _handle_chat,
    _handle_conversation_delete,
    _handle_conversation_get,
    _handle_conversations_list,
)
from minerva.http.server_core import _HTTPError

# ---------- conversation persistence in /api/chat ----------


def test_handle_chat_creates_conversation_when_id_absent(populated_db, conversations_conn):
    backend = StubBackend(reply="reply [1].")
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    body = _handle_chat(deps, {"query": "What is the divided line?"})
    cid = body["conversation_id"]
    assert conversations.is_valid_id(cid)
    # Title is derived from the first user turn.
    assert body["title"] == "What is the divided line"
    # Both user + assistant rows persisted.
    rows = conversations_conn.execute(
        "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id", (cid,)
    ).fetchall()
    assert [r[0] for r in rows] == ["user", "assistant"]
    assert rows[0][1] == "What is the divided line?"


def test_handle_chat_appends_to_existing_conversation(populated_db, conversations_conn):
    backend = StubBackend(reply="reply.")
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    first = _handle_chat(deps, {"query": "What is the divided line?"})
    cid = first["conversation_id"]
    second = _handle_chat(
        deps,
        {
            "query": "And what comes after?",
            "conversation_id": cid,
        },
    )
    assert second["conversation_id"] == cid
    # No `title` on the second turn — only the first.
    assert "title" not in second
    rows = conversations_conn.execute(
        "SELECT role FROM messages WHERE conversation_id=? ORDER BY id", (cid,)
    ).fetchall()
    assert [r[0] for r in rows] == ["user", "assistant", "user", "assistant"]


def test_handle_chat_rejects_unknown_conversation_id(populated_db, conversations_conn):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    with pytest.raises(_HTTPError) as info:
        _handle_chat(
            deps,
            {
                "query": "x",
                "conversation_id": "doesnotexist1",
            },
        )
    assert info.value.status == HTTPStatus.NOT_FOUND


def test_handle_chat_rejects_malformed_conversation_id(populated_db, conversations_conn):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    with pytest.raises(_HTTPError) as info:
        _handle_chat(
            deps,
            {
                "query": "x",
                "conversation_id": "../etc/passwd",
            },
        )
    assert info.value.status == HTTPStatus.BAD_REQUEST


def test_handle_chat_persists_assistant_dominant_and_citations(populated_db, conversations_conn):
    backend = StubBackend(reply="ok [1].")
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    body = _handle_chat(deps, {"query": "divided line"})
    cid = body["conversation_id"]
    row = conversations_conn.execute(
        "SELECT dominant, citations_json FROM messages "
        "WHERE conversation_id=? AND role='assistant'",
        (cid,),
    ).fetchone()
    assert row[0] == body["dominant"]
    saved = json.loads(row[1])
    assert [c["n"] for c in saved] == [c["n"] for c in body["citations"]]


# ---------- compensating rollback on chat failure ----------
#
# When the LLM call fails after Phase 1 has already persisted the user
# turn, the handler must roll the user turn back so the conversation
# never lands in a half-finished state. Two sub-cases:
#   1. The chat call created a new conversation → drop the whole row.
#   2. The chat call appended to an existing one → drop only the user
#      message we just added.


def test_handle_chat_rolls_back_new_conversation_on_llm_failure(populated_db, conversations_conn):
    failing = StubBackend(reply=RuntimeError("simulated upstream"))
    deps = _make_deps(populated_db, failing, conversations_conn=conversations_conn)

    with pytest.raises(RuntimeError, match="simulated upstream"):
        _handle_chat(deps, {"query": "What is the divided line?"})

    # The conversation should have been deleted entirely — no orphan
    # user turn left behind.
    rows = conversations_conn.execute("SELECT COUNT(*) FROM conversations").fetchone()
    assert rows[0] == 0
    msg_rows = conversations_conn.execute("SELECT COUNT(*) FROM messages").fetchone()
    assert msg_rows[0] == 0


def test_handle_chat_rolls_back_appended_turn_on_llm_failure(populated_db, conversations_conn):
    # First call succeeds and creates a conversation with [user,
    # assistant] turns. Then a second call against the same
    # conversation fails — we should be left with just the original
    # pair, NOT a dangling user turn from the failed call. Both queries
    # match the populated_db fixture's "divided line" / "cave" chunks
    # so retrieval doesn't abstain — otherwise compose_answer short-
    # circuits without ever invoking the failing backend.
    ok = StubBackend(reply="answer [1].")
    deps = _make_deps(populated_db, ok, conversations_conn=conversations_conn)
    first = _handle_chat(deps, {"query": "What is the divided line?"})
    cid = first["conversation_id"]

    # Swap in a failing backend for the second call.
    failing = StubBackend(reply=RuntimeError("simulated upstream"))
    deps.backend = failing

    with pytest.raises(RuntimeError, match="simulated upstream"):
        _handle_chat(
            deps,
            {"query": "And the cave allegory?", "conversation_id": cid},
        )

    rows = conversations_conn.execute(
        "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id",
        (cid,),
    ).fetchall()
    assert [r[0] for r in rows] == ["user", "assistant"]
    assert "divided line" in rows[0][1]
    # The failed-call user turn is gone.
    assert all("cave allegory" not in r[1] for r in rows)


def test_handle_chat_rolls_back_on_retrieval_failure(populated_db, conversations_conn, monkeypatch):
    from minerva import agent

    def _boom(*_args, **_kwargs):
        raise RuntimeError("retrieval failed")

    monkeypatch.setattr(agent, "retrieve_passages", _boom)
    deps = _make_deps(
        populated_db,
        StubBackend(reply="answer [1]."),
        conversations_conn=conversations_conn,
    )

    with pytest.raises(RuntimeError, match="retrieval failed"):
        _handle_chat(deps, {"query": "What is the divided line?"})

    assert conversations_conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
    assert conversations_conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0


# ---------- /api/conversations endpoints ----------


def test_handle_conversations_list_returns_persisted_conversations(
    populated_db, conversations_conn
):
    backend = StubBackend(reply="ok")
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    _handle_chat(deps, {"query": "first"})
    _handle_chat(deps, {"query": "second"})
    body = _handle_conversations_list(deps)
    titles = [c["title"] for c in body["conversations"]]
    # Newest first.
    assert titles == ["second", "first"]


def test_handle_conversation_get_returns_messages(populated_db, conversations_conn):
    backend = StubBackend(reply="reply.")
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    cid = _handle_chat(deps, {"query": "What is virtue?"})["conversation_id"]
    body = _handle_conversation_get(deps, cid)
    assert body["id"] == cid
    assert body["title"] == "What is virtue"
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]


def test_handle_conversation_get_404_unknown(populated_db, conversations_conn):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    with pytest.raises(_HTTPError) as info:
        _handle_conversation_get(deps, "abcdef1234")
    assert info.value.status == HTTPStatus.NOT_FOUND


def test_handle_conversation_get_400_invalid_id(populated_db, conversations_conn):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    with pytest.raises(_HTTPError) as info:
        _handle_conversation_get(deps, "../oops")
    assert info.value.status == HTTPStatus.BAD_REQUEST


def test_handle_conversation_delete_removes_and_cascades(populated_db, conversations_conn):
    backend = StubBackend(reply="ok")
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    cid = _handle_chat(deps, {"query": "first"})["conversation_id"]
    assert (
        conversations_conn.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id=?", (cid,)
        ).fetchone()[0]
        == 2
    )
    removed = _handle_conversation_delete(deps, cid)
    assert removed is True
    assert (
        conversations_conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE id=?", (cid,)
        ).fetchone()[0]
        == 0
    )
    assert (
        conversations_conn.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id=?", (cid,)
        ).fetchone()[0]
        == 0
    )


def test_handle_conversation_delete_returns_false_for_unknown(populated_db, conversations_conn):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    assert _handle_conversation_delete(deps, "abcdef1234") is False


def test_handle_conversation_delete_400_invalid_id(populated_db, conversations_conn):
    backend = StubBackend()
    deps = _make_deps(populated_db, backend, conversations_conn=conversations_conn)
    with pytest.raises(_HTTPError) as info:
        _handle_conversation_delete(deps, "bad/id")
    assert info.value.status == HTTPStatus.BAD_REQUEST
