"""POST /api/chat — grounded answer with pinned + retrieved citations."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ... import agent, chat_service
from ...chat_context import ChatContext
from ..server_core import ServerDeps
from ._locks import map_domain_errors


@map_domain_errors
def _handle_chat(deps: ServerDeps, payload: dict[str, Any]) -> dict[str, Any]:
    ctx = deps.to_chat_context()
    prep = chat_service.prepare_chat_turn(ctx, payload)
    try:
        ans = agent.compose_answer(
            query=prep.query,
            retrieval=prep.retrieval,
            backend=deps.backend,
            history=prep.history,
            cite_style="numeric",
            reply_lang=prep.reply_lang,
        )
        body = chat_service.answer_to_json(ans)
        _persist_assistant_turn(deps, prep, body)
    except KeyboardInterrupt:
        raise
    except Exception:
        chat_service.rollback_chat_turn(
            ctx,
            created_new_conversation=prep.created_new_conversation,
            cid=prep.cid,
            user_msg_id=prep.user_msg_id,
        )
        raise

    body["conversation_id"] = prep.cid
    if prep.new_title is not None:
        body["title"] = prep.new_title
    if prep.missing_pinned:
        body["missing_pinned_ids"] = prep.missing_pinned
    return body


def _persist_assistant_turn(
    deps: ServerDeps,
    prep: chat_service.ChatPrepared,
    body: dict[str, Any],
) -> None:
    from ... import conversations

    with deps.conv_lock:
        conversations.append_message(
            deps.conversations_conn,
            conversation_id=prep.cid,
            role="assistant",
            content="\n\n".join(body["paragraphs"]),
            dominant=body["dominant"],
            abstained=bool(body["abstained"]),
            citations=body["citations"],
        )


@map_domain_errors
def _handle_chat_stream(
    deps: ServerDeps, payload: dict[str, Any]
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Prepare the turn eagerly, then return the SSE event generator.

    Preparation (validation, conversation persistence, retrieval) must
    run BEFORE the caller writes the SSE response headers: it raises
    domain errors (missing query, bad conversation_id, too many pinned
    ids), and if those surfaced lazily on the generator's first
    ``next()`` the server would have already committed to a 200 SSE
    response — the error JSON would then be written as a second status
    line into the open stream.
    """

    ctx = deps.to_chat_context()
    prep = chat_service.prepare_chat_turn(ctx, payload)
    return _stream_prepared_turn(deps, ctx, prep)


def _stream_prepared_turn(
    deps: ServerDeps, ctx: ChatContext, prep: chat_service.ChatPrepared
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield SSE ``(event_name, data)`` pairs for a prepared chat turn."""

    from ... import llm

    skip_deltas = prep.retrieval.abstain or deps.backend.name == "none"
    completed = False
    persisted = False

    meta: dict[str, Any] = {
        "citations": chat_service.citations_from_retrieval(prep.retrieval),
        "abstained": prep.retrieval.abstain,
        "backend": deps.backend.name,
        "conversation_id": prep.cid,
    }
    if prep.new_title is not None:
        meta["title"] = prep.new_title
    if prep.missing_pinned:
        meta["missing_pinned_ids"] = prep.missing_pinned
    yield ("meta", meta)

    try:
        parts: list[str] = []
        for chunk in agent.compose_answer_stream(
            query=prep.query,
            retrieval=prep.retrieval,
            backend=deps.backend,
            history=prep.history,
            cite_style="numeric",
            reply_lang=prep.reply_lang,
        ):
            parts.append(chunk)
            if chunk and not skip_deltas:
                yield ("delta", {"text": chunk})

        text = "".join(parts)
        ans = agent.Answer(
            query=prep.query,
            response=text,
            hits=prep.retrieval.hits,
            abstained=prep.retrieval.abstain,
            backend=deps.backend.name,
            pinned=prep.retrieval.pinned,
        )
        body = chat_service.answer_to_json(ans)
        _persist_assistant_turn(deps, prep, body)
        persisted = True
        yield (
            "done",
            {
                "response": body["response"],
                "paragraphs": body["paragraphs"],
                "dominant": body["dominant"],
            },
        )
        completed = True
    except KeyboardInterrupt:
        raise
    except llm.LLMError:
        import logging

        logging.getLogger(__name__).exception("LLM error during chat stream")
        yield ("error", {"error": "LLM backend error"})
    except Exception:
        import logging

        logging.getLogger(__name__).exception("chat stream failed")
        yield ("error", {"error": "server error"})
    finally:
        if not completed and not persisted:
            chat_service.rollback_chat_turn(
                ctx,
                created_new_conversation=prep.created_new_conversation,
                cid=prep.cid,
                user_msg_id=prep.user_msg_id,
            )
