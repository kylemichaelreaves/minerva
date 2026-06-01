"""Tests for `minerva.conversations` — schema, CRUD, derive_title, id validation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from minerva import conversations

# ---------- derive_title ----------


def test_derive_title_uses_input_when_short():
    # Trailing punctuation is stripped; the question mark goes.
    assert conversations.derive_title("What is virtue?") == "What is virtue"


def test_derive_title_keeps_internal_punctuation():
    assert conversations.derive_title("Plato vs. Aristotle") == "Plato vs. Aristotle"


def test_derive_title_truncates_long_input_at_word_boundary():
    s = "what does Hegel mean by Sittlichkeit and how does it differ from Moralitat in his system"
    title = conversations.derive_title(s, limit=60)
    assert len(title) <= 60
    assert not title.endswith(" ")
    assert " " in title  # didn't fall to hard truncation


def test_derive_title_strips_trailing_punctuation():
    assert (
        conversations.derive_title("Is justice the same in soul and city?")
        == "Is justice the same in soul and city"
    )


def test_derive_title_collapses_internal_whitespace():
    # \t and \n and runs of spaces all collapse to a single space.
    title = conversations.derive_title("line\nbreak with  spaces")
    assert title == "line break with spaces"


def test_derive_title_empty_falls_back():
    assert conversations.derive_title("") == "Untitled"
    assert conversations.derive_title("   \n  ") == "Untitled"


def test_derive_title_hard_truncates_when_no_word_boundary():
    # No spaces in the head; falls through to a hard truncation.
    s = "x" * 200
    title = conversations.derive_title(s, limit=60)
    assert len(title) == 60


# ---------- is_valid_id ----------


def test_is_valid_id_accepts_token_urlsafe_outputs():
    import secrets

    for _ in range(20):
        assert conversations.is_valid_id(secrets.token_urlsafe(8))


def test_is_valid_id_rejects_obvious_attacks():
    assert not conversations.is_valid_id("../etc/passwd")
    assert not conversations.is_valid_id("'; DROP TABLE--")
    assert not conversations.is_valid_id("a/b")
    assert not conversations.is_valid_id("a b")
    assert not conversations.is_valid_id("")


def test_is_valid_id_rejects_too_short_and_too_long():
    assert not conversations.is_valid_id("abc")  # 3 chars
    assert not conversations.is_valid_id("a" * 33)


# ---------- open_db schema ----------


def test_open_db_creates_schema(tmp_path: Path):
    conn = conversations.open_db(tmp_path / "c.sqlite")
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "conversations" in tables
    assert "messages" in tables


def test_open_db_enables_foreign_keys(tmp_path: Path):
    conn = conversations.open_db(tmp_path / "c.sqlite")
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1


# ---------- create + append + get ----------


def test_create_and_get_round_trip(tmp_path: Path):
    conn = conversations.open_db(tmp_path / "c.sqlite")
    cid = conversations.create_conversation(conn, title="On virtue", now=100.0)
    conversations.append_message(
        conn, conversation_id=cid, role="user", content="Is virtue teachable?", now=101.0
    )
    conversations.append_message(
        conn,
        conversation_id=cid,
        role="assistant",
        content="It depends on what we mean by virtue.",
        dominant="A",
        abstained=False,
        citations=[{"n": 1, "src": "Meno 70a", "text": "..."}],
        now=102.0,
    )
    out = conversations.get_conversation(conn, cid)
    assert out is not None
    assert out["id"] == cid
    assert out["title"] == "On virtue"
    assert out["dominant"] == "A"  # bumped by the assistant turn
    assert len(out["messages"]) == 2
    assert out["messages"][0]["role"] == "user"
    assert out["messages"][1]["role"] == "assistant"
    assert out["messages"][1]["dominant"] == "A"
    assert out["messages"][1]["abstained"] is False
    assert out["messages"][1]["citations"][0]["src"] == "Meno 70a"


def test_get_unknown_conversation_returns_none(tmp_path: Path):
    conn = conversations.open_db(tmp_path / "c.sqlite")
    assert conversations.get_conversation(conn, "nope-1234") is None


def test_append_message_updates_updated_at(tmp_path: Path):
    conn = conversations.open_db(tmp_path / "c.sqlite")
    cid = conversations.create_conversation(conn, title="t", now=100.0)
    conversations.append_message(conn, conversation_id=cid, role="user", content="q", now=200.0)
    row = conn.execute(
        "SELECT created_at, updated_at FROM conversations WHERE id=?", (cid,)
    ).fetchone()
    assert row[0] == 100.0
    assert row[1] == 200.0


def test_append_message_user_does_not_overwrite_dominant(tmp_path: Path):
    """Only assistant turns reflect philosopher dominance; a follow-up user
    turn shouldn't blank the prior dominant."""

    conn = conversations.open_db(tmp_path / "c.sqlite")
    cid = conversations.create_conversation(conn, title="t")
    conversations.append_message(
        conn,
        conversation_id=cid,
        role="assistant",
        content="reply",
        dominant="P",
    )
    conversations.append_message(
        conn,
        conversation_id=cid,
        role="user",
        content="follow up",
    )
    out = conversations.get_conversation(conn, cid)
    assert out is not None
    assert out["dominant"] == "P"


def test_append_message_invalid_role_raises(tmp_path: Path):
    conn = conversations.open_db(tmp_path / "c.sqlite")
    cid = conversations.create_conversation(conn, title="t")
    with pytest.raises(ValueError):
        conversations.append_message(conn, conversation_id=cid, role="system", content="x")


def test_append_message_unknown_conversation_id_fk_error(tmp_path: Path):
    conn = conversations.open_db(tmp_path / "c.sqlite")
    with pytest.raises(sqlite3.IntegrityError):
        conversations.append_message(conn, conversation_id="nonsense-id", role="user", content="x")


# ---------- list ----------


def test_list_orders_by_updated_at_desc(tmp_path: Path):
    conn = conversations.open_db(tmp_path / "c.sqlite")
    a = conversations.create_conversation(conn, title="A", now=100.0)
    b = conversations.create_conversation(conn, title="B", now=200.0)
    c = conversations.create_conversation(conn, title="C", now=150.0)
    rows = conversations.list_conversations(conn)
    assert [r["id"] for r in rows] == [b, c, a]


def test_list_empty_returns_empty(tmp_path: Path):
    conn = conversations.open_db(tmp_path / "c.sqlite")
    assert conversations.list_conversations(conn) == []


# ---------- delete + cascade ----------


def test_delete_removes_conversation(tmp_path: Path):
    conn = conversations.open_db(tmp_path / "c.sqlite")
    cid = conversations.create_conversation(conn, title="t")
    assert conversations.delete_conversation(conn, cid) is True
    assert conversations.get_conversation(conn, cid) is None


def test_delete_unknown_returns_false(tmp_path: Path):
    conn = conversations.open_db(tmp_path / "c.sqlite")
    assert conversations.delete_conversation(conn, "missing-id") is False


def test_delete_cascades_messages(tmp_path: Path):
    conn = conversations.open_db(tmp_path / "c.sqlite")
    cid = conversations.create_conversation(conn, title="t")
    conversations.append_message(conn, conversation_id=cid, role="user", content="x")
    conversations.append_message(conn, conversation_id=cid, role="assistant", content="y")
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 2
    conversations.delete_conversation(conn, cid)
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
