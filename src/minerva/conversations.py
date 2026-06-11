"""Conversation + message persistence, kept in its own SQLite file.

Lives separately from `data/index.sqlite` because the corpus index is
considered derived and gets blown away on `minerva index --reset`;
conversations need to survive re-ingests.

Schema is created on `open_db`. All public functions take an open
connection so callers (CLI, server) can manage lifecycle. The HTTP
server serializes access through its existing `ServerDeps.lock`, so we
don't need a per-module lock.
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    dominant    TEXT,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS conversations_updated ON conversations(updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    created_at      REAL NOT NULL,
    dominant        TEXT,
    abstained       INTEGER,
    citations_json  TEXT
);

CREATE INDEX IF NOT EXISTS messages_by_conv ON messages(conversation_id, id);
"""

# IDs are minted with `secrets.token_urlsafe(8)` (~11 chars). The path-param
# regex is intentionally permissive on length to tolerate future bumps but
# strict on character class — keeps traversal/injection out of SQL paths.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,32}$")


def is_valid_id(s: str) -> bool:
    return bool(_ID_RE.match(s))


def open_db(path: Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open the conversations DB, creating tables if missing.

    The HTTP server uses ThreadingHTTPServer + a single shared lock, so it
    opts into `check_same_thread=False`. CLI / test callers keep the safer
    default.
    """

    from .sqlite_util import open_sqlite

    return open_sqlite(path, SCHEMA, check_same_thread=check_same_thread)


def derive_title(text: str, *, limit: int = 60) -> str:
    """Derive a sidebar title from the first user message.

    Strip whitespace, take the first `limit` chars, snap back to the
    nearest word boundary, then strip trailing punctuation. Empty input
    falls back to "Untitled" so the title column is never empty.
    """

    s = (text or "").strip()
    if not s:
        return "Untitled"
    # Collapse internal newlines/tabs so titles stay one line.
    s = re.sub(r"\s+", " ", s)
    if len(s) <= limit:
        candidate = s
    else:
        head = s[:limit]
        cut = head.rfind(" ")
        # Only snap to a word boundary when one exists in the head; otherwise
        # accept the hard truncation (very long single tokens, code samples).
        candidate = head[:cut] if cut >= limit // 2 else head
    candidate = candidate.rstrip(" .,;:!?-—")
    return candidate or "Untitled"


def _row_to_conversation(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "dominant": row["dominant"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_message(row: sqlite3.Row) -> dict[str, Any]:
    citations: list[Any] = []
    raw = row["citations_json"]
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                citations = parsed
        except json.JSONDecodeError:
            citations = []
    return {
        "role": row["role"],
        "content": row["content"],
        "created_at": row["created_at"],
        "dominant": row["dominant"],
        "abstained": bool(row["abstained"]) if row["abstained"] is not None else None,
        "citations": citations,
    }


def create_conversation(
    conn: sqlite3.Connection,
    *,
    title: str,
    dominant: str | None = None,
    now: float | None = None,
) -> str:
    """Insert a new conversation and return its id."""

    cid = secrets.token_urlsafe(8)
    ts = time.time() if now is None else now
    conn.execute(
        "INSERT INTO conversations(id, title, dominant, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (cid, title, dominant, ts, ts),
    )
    conn.commit()
    return cid


def append_message(
    conn: sqlite3.Connection,
    *,
    conversation_id: str,
    role: str,
    content: str,
    dominant: str | None = None,
    abstained: bool | None = None,
    citations: list[dict[str, Any]] | None = None,
    now: float | None = None,
) -> int:
    """Append a message and bump the conversation's `updated_at` + `dominant`.

    Returns the new message rowid. Raises ValueError on unknown id so
    callers don't silently leak orphan rows (FK would catch it but the
    error path is uglier).
    """

    if role not in {"user", "assistant"}:
        raise ValueError(f"invalid role: {role!r}")
    ts = time.time() if now is None else now
    citations_json = json.dumps(citations, ensure_ascii=False) if citations else None
    abstained_int = None if abstained is None else (1 if abstained else 0)
    cur = conn.execute(
        "INSERT INTO messages"
        "(conversation_id, role, content, created_at, dominant, abstained, citations_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (conversation_id, role, content, ts, dominant, abstained_int, citations_json),
    )
    # Keep the conversation's dominant tracking the most recent assistant
    # turn so the sidebar glyph reflects "what kind of conversation this
    # has become." User turns leave dominant alone.
    if role == "assistant" and dominant:
        conn.execute(
            "UPDATE conversations SET updated_at=?, dominant=? WHERE id=?",
            (ts, dominant, conversation_id),
        )
    else:
        conn.execute(
            "UPDATE conversations SET updated_at=? WHERE id=?",
            (ts, conversation_id),
        )
    conn.commit()
    if cur.lastrowid is None:
        # SQLite always sets lastrowid on INSERT; defensive only.
        raise RuntimeError("INSERT did not produce a rowid")
    return cur.lastrowid


def list_conversations(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, title, dominant, created_at, updated_at "
        "FROM conversations ORDER BY updated_at DESC"
    ).fetchall()
    return [_row_to_conversation(r) for r in rows]


def get_conversation(conn: sqlite3.Connection, cid: str) -> dict[str, Any] | None:
    """Fetch one conversation + all its messages, or None if unknown."""

    row = conn.execute(
        "SELECT id, title, dominant, created_at, updated_at FROM conversations WHERE id=?",
        (cid,),
    ).fetchone()
    if row is None:
        return None
    out = _row_to_conversation(row)
    msgs = conn.execute(
        "SELECT role, content, created_at, dominant, abstained, citations_json "
        "FROM messages WHERE conversation_id=? ORDER BY id",
        (cid,),
    ).fetchall()
    out["messages"] = [_row_to_message(m) for m in msgs]
    return out


def delete_conversation(conn: sqlite3.Connection, cid: str) -> bool:
    """Hard-delete a conversation and its messages. Returns True if a row
    was actually removed (so callers can return 404 on misses)."""

    cur = conn.execute("DELETE FROM conversations WHERE id=?", (cid,))
    conn.commit()
    return cur.rowcount > 0


def delete_message(conn: sqlite3.Connection, message_id: int) -> bool:
    """Hard-delete a single message by rowid. Used by /api/chat when
    the user-turn has been persisted but the assistant turn could not
    be generated (retrieval or LLM failure) — leaving the orphan user
    turn would visibly clutter the conversation history.

    Returns True if a row was actually removed. Also recomputes the
    conversation's `updated_at` so the sidebar's "last activity" time
    moves backward to the previous message.
    """

    # Look up the parent conversation before deleting so we can fix
    # the updated_at; if the row's already gone (concurrent delete),
    # short-circuit cleanly.
    row = conn.execute(
        "SELECT conversation_id FROM messages WHERE id=?", (message_id,)
    ).fetchone()
    if row is None:
        return False
    cid = row[0]
    conn.execute("DELETE FROM messages WHERE id=?", (message_id,))
    # Recompute updated_at from the latest surviving message's timestamp,
    # falling back to the conversation's created_at if none remain (which
    # can happen if the failing chat call created the conversation too —
    # in that case the handler will follow up with delete_conversation
    # anyway).
    conn.execute(
        "UPDATE conversations "
        "SET updated_at = COALESCE("
        "  (SELECT MAX(created_at) FROM messages WHERE conversation_id=?), "
        "  created_at"
        ") "
        "WHERE id=?",
        (cid, cid),
    )
    conn.commit()
    return True
