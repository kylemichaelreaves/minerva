"""Conversation sidebar endpoints: list / get / delete."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from ... import conversations
from ..server_core import ServerDeps, _HTTPError
from ._locks import with_conv_lock


@with_conv_lock
def _handle_conversations_list(deps: ServerDeps) -> dict[str, Any]:
    rows = conversations.list_conversations(deps.conversations_conn)
    return {"conversations": rows}


@with_conv_lock
def _handle_conversation_get(deps: ServerDeps, cid: str) -> dict[str, Any]:
    if not conversations.is_valid_id(cid):
        raise _HTTPError(HTTPStatus.BAD_REQUEST, "invalid conversation_id")
    result = conversations.get_conversation(deps.conversations_conn, cid)
    if result is None:
        raise _HTTPError(HTTPStatus.NOT_FOUND, "conversation not found")
    return result


@with_conv_lock
def _handle_conversation_delete(deps: ServerDeps, cid: str) -> bool:
    if not conversations.is_valid_id(cid):
        raise _HTTPError(HTTPStatus.BAD_REQUEST, "invalid conversation_id")
    return conversations.delete_conversation(deps.conversations_conn, cid)
