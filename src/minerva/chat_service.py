"""Chat turn orchestration — persistence, retrieval, and shaping a
grounded answer with pinned + retrieved citations.

Phases are explicit so the lock-acquisition order is auditable from the
top of `_handle_chat` down — the LLM round-trip MUST run with all DB
locks released so concurrent translate / conversation requests aren't
blocked by a slow completion. See the comments in `_handle_chat` for
the exact ordering.
"""

from __future__ import annotations

import dataclasses
import logging
import sqlite3
from typing import Any

from . import agent, concept_cache, conversations, llm, retrieve, store
from .chat_context import ChatContext
from .citations import _dominant_from_response, citations_from_hits
from .corpus_registry import original_language_for_corpus
from .errors import BadRequestError, NotFoundError, PayloadTooLargeError

_VALID_REPLY_LANG = frozenset(agent.LANG_DISPLAY_NAMES)

_log = logging.getLogger(__name__)


def answer_to_json(ans: agent.Answer) -> dict[str, Any]:
    # Pinned passages first, then retrieval; numbering runs through both so
    # the frontend can render `[N]` markers consistently across the merged
    # list. Pinned items get `pinned: true` so the UI can mark them.
    citations = citations_from_hits(ans.pinned, ans.hits)
    if ans.backend == "none" and not ans.abstained:
        # _format_passages was inlined into ans.response; the frontend
        # already shows citations separately, so collapse the body.
        paragraphs = ["(retrieval-only mode — see citations below.)"]
    else:
        text = ans.response.strip()
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()] or [text]
    return {
        "response": ans.response,
        "paragraphs": paragraphs,
        "citations": citations,
        "dominant": _dominant_from_response(ans.response, ans.pinned, ans.hits),
        "abstained": ans.abstained,
        "backend": ans.backend,
    }


# ---------- Request parsing helpers ----------

# Mirror translate's 8 KiB source cap — each chat turn can otherwise
# ship ~1 MiB of query + history under the global body limit.
_MAX_QUERY_CHARS = 8 * 1024
_MAX_HISTORY_TURNS = 40
_MAX_HISTORY_CHARS = 32 * 1024
# Hard cap on pinned_chunk_ids so a large payload can't force a heavy
# IN-list lookup under the shared corpus lock. 50 is well past the UI's
# practical limit (the reader pins ~5-10 per conversation) and small
# enough that the resulting `IN (?,?,…)` clause stays cheap.
_MAX_PINNED_IDS = 50


def history_from_payload(raw: Any) -> list[llm.Message]:
    if not isinstance(raw, list):
        return []
    out: list[llm.Message] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content:
            out.append(llm.Message(role=role, content=content))
    return out


def _validate_history(history: list[llm.Message]) -> list[llm.Message]:
    if len(history) > _MAX_HISTORY_TURNS:
        raise PayloadTooLargeError(
            f"history exceeds the per-request cap ({len(history)} > {_MAX_HISTORY_TURNS})",
        )
    total = sum(len(m.content) for m in history)
    if total > _MAX_HISTORY_CHARS:
        raise PayloadTooLargeError(
            f"history exceeds the {_MAX_HISTORY_CHARS}-character cap",
        )
    return history


def pinned_ids_from_payload(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    if len(raw) > _MAX_PINNED_IDS:
        raise PayloadTooLargeError(
            f"pinned_chunk_ids exceeds the per-request cap ({len(raw)} > {_MAX_PINNED_IDS})",
        )
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str) and item and item not in seen:
            out.append(item)
            seen.add(item)
    return out


def resolve_pinned(conn: sqlite3.Connection, chunk_ids: list[str]) -> list[retrieve.Hit]:
    """Resolve pinned chunk_ids into `Hit` objects so they can be passed to
    `agent.answer`. Drops unknown ids silently — they're stale references
    from the client (e.g. after a re-index)."""

    if not chunk_ids:
        return []
    rows = store.fetch_chunks(conn, chunk_ids)
    pinned: list[retrieve.Hit] = []
    for cid in chunk_ids:
        row = rows.get(cid)
        if row is None:
            continue
        pinned.append(
            retrieve.Hit(
                chunk_id=cid,
                score=1.0,  # pin overrides retrieval ranking
                bm25=0.0,
                cosine=0.0,
                meta=store.to_meta_dict(row),
            )
        )
    return pinned


def reply_lang_from_payload(payload: dict[str, Any]) -> str | None:
    """Return an explicit ISO 639-3 override, or ``None`` for auto-detect."""

    raw = payload.get("reply_lang")
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        return None
    code = raw.strip()
    if code == "auto":
        return None
    if code not in _VALID_REPLY_LANG:
        raise BadRequestError(
            f"reply_lang must be one of {('auto', *sorted(_VALID_REPLY_LANG))}",
        )
    return code


def build_retrieval_query(query: str, history: list[llm.Message]) -> str:
    """Thin wrapper around `agent.build_retrieval_query` so the server
    and CLI agree on the retrieval-context policy in one place."""

    prior = [m.content for m in history if m.role == "user"]
    return agent.build_retrieval_query(query, prior)


def citations_from_retrieval(retrieval: agent.RetrievalResult) -> list[dict[str, Any]]:
    return citations_from_hits(retrieval.pinned, retrieval.hits)


@dataclasses.dataclass
class ChatPrepared:
    query: str
    history: list[llm.Message]
    cid: str
    user_msg_id: int
    created_new_conversation: bool
    new_title: str | None
    retrieval: agent.RetrievalResult
    missing_pinned: list[str]
    reply_lang: str | None


@dataclasses.dataclass
class ChatRequest:
    """Validated chat-turn payload — the output of `parse_chat_payload`."""

    query: str
    reply_lang: str | None
    history: list[llm.Message]
    speaker: str | None
    work_id: int | None
    incoming_cid: str | None
    client_requested_rewrite: bool
    pinned_ids: list[str]


def parse_chat_payload(ctx: ChatContext, payload: dict[str, Any]) -> ChatRequest:
    """Validate the raw request payload into a `ChatRequest`. Pure
    parsing — no DB access, no locks; raises BadRequestError /
    PayloadTooLargeError on malformed input."""

    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        raise BadRequestError("missing or empty 'query'")
    query = query.strip()
    if len(query) > _MAX_QUERY_CHARS:
        raise PayloadTooLargeError(
            f"query exceeds the {_MAX_QUERY_CHARS}-character limit",
        )
    # Validated in this order so a multiply-invalid payload reports the
    # same field it did before this parsing was extracted.
    reply_lang = reply_lang_from_payload(payload)
    history = _validate_history(history_from_payload(payload.get("history")))
    raw_speaker = payload.get("speaker")
    speaker = (
        raw_speaker.strip() if isinstance(raw_speaker, str) and raw_speaker.strip() else ctx.speaker
    )
    # Explicit work scope (e.g. "in the Genealogy"): hard-restrict
    # retrieval to one work. `work_id` is the works.id; bool excluded
    # because `True`/`False` are ints in Python. Falls through to
    # auto-detection (in `prepare_chat_turn`) when absent.
    raw_work_id = payload.get("work_id")
    work_id: int | None = (
        raw_work_id
        if isinstance(raw_work_id, int) and not isinstance(raw_work_id, bool) and raw_work_id > 0
        else None
    )
    raw_cid = payload.get("conversation_id")
    incoming_cid: str | None = None
    if isinstance(raw_cid, str) and raw_cid:
        if not conversations.is_valid_id(raw_cid):
            raise BadRequestError("invalid conversation_id")
        incoming_cid = raw_cid
    return ChatRequest(
        query=query,
        reply_lang=reply_lang,
        history=history,
        speaker=speaker,
        work_id=work_id,
        incoming_cid=incoming_cid,
        client_requested_rewrite=bool(payload.get("rewrite")) and ctx.allow_client_rewrite,
        pinned_ids=pinned_ids_from_payload(payload.get("pinned_chunk_ids")),
    )


def _expand_concepts(ctx: ChatContext, retrieval_query: str, corpus: str) -> str:
    """Concept expansion. If the corpus's original language differs
    from the query's (assumed English unless overridden), ask the LLM
    for 2-4 key target-language terms and append them to the retrieval
    query. The multilingual embedding model is too weak to bridge
    English "failures" → German *Mißratenen* on its own; surfacing the
    technical term directly fixes that. No-op when --no-concept-expand
    or backend is `none` or the corpus is English-primary."""

    if not ctx.enable_concept_expand or ctx.backend.name == "none":
        return retrieval_query
    target_lang = original_language_for_corpus(corpus)
    if not target_lang or target_lang == "eng":
        return retrieval_query
    # Cache lookup first — avoids the LLM call entirely for repeat
    # questions about the same concept. The cache key normalizes case +
    # whitespace so trivially-equivalent phrasings share an entry.
    terms: list[str] = []
    if ctx.concept_cache_conn is not None:
        with ctx.concept_cache_lock:
            cached = concept_cache.lookup(
                ctx.concept_cache_conn,
                query=retrieval_query,
                corpus=corpus,
                target_lang=target_lang,
            )
        if cached is not None:
            terms = cached
    # Miss → call the LLM and store the result for next time.
    if not terms:
        terms = agent.concept_expand(
            ctx.backend,
            retrieval_query,
            corpus=corpus,
            target_lang=target_lang,
        )
        if terms and ctx.concept_cache_conn is not None:
            with ctx.concept_cache_lock:
                concept_cache.insert(
                    ctx.concept_cache_conn,
                    query=retrieval_query,
                    corpus=corpus,
                    target_lang=target_lang,
                    terms=terms,
                    model=ctx.backend.name,
                )
    if terms:
        return f"{retrieval_query} {' '.join(terms)}"
    return retrieval_query


def _work_scope(ctx: ChatContext, work_id: int | None) -> tuple[str | None, str | None]:
    """When the client explicitly scopes to a work, derive its author +
    original language so corpus filtering, concept-expansion, and
    orthography folding key off the *scoped work* — even when the
    question never names the author (e.g. "his notes on failures"
    scoped to the Nachlaß). Brief locked read, released before any LLM
    call so the lock-ordering contract in `_handle_chat` is preserved."""

    if work_id is None:
        return None, None
    with ctx.corpus_lock:
        row = ctx.index_conn.execute(
            "SELECT LOWER(author), original_language FROM works WHERE id = ?",
            (work_id,),
        ).fetchone()
    if row is None:
        return None, None
    return row[0], row[1]


def _persist_user_turn(ctx: ChatContext, req: ChatRequest) -> tuple[str, int, bool, str | None]:
    """Phase 1: append the user turn, creating the conversation when no
    id came in. Returns (cid, user_msg_id, created_new, new_title)."""

    new_title: str | None = None
    with ctx.conv_lock:
        if req.incoming_cid is not None:
            if conversations.get_conversation(ctx.conversations_conn, req.incoming_cid) is None:
                raise NotFoundError("conversation not found")
            cid = req.incoming_cid
        else:
            new_title = conversations.derive_title(req.query)
            cid = conversations.create_conversation(
                ctx.conversations_conn,
                title=new_title,
            )
        user_msg_id = conversations.append_message(
            ctx.conversations_conn,
            conversation_id=cid,
            role="user",
            content=req.query,
        )
    return cid, user_msg_id, req.incoming_cid is None, new_title


def prepare_chat_turn(ctx: ChatContext, payload: dict[str, Any]) -> ChatPrepared:
    """Phases 1–3: persist user turn, optional rewrite, retrieve passages."""

    req = parse_chat_payload(ctx, payload)
    work_id = req.work_id
    scope_corpus, scope_lang = _work_scope(ctx, work_id)
    retrieval_query = build_retrieval_query(req.query, req.history)

    cid, user_msg_id, created_new_conversation, new_title = _persist_user_turn(ctx, req)

    try:
        should_rewrite = (
            (ctx.force_rewrite or req.client_requested_rewrite)
            and req.history
            and ctx.backend.name != "none"
        )
        if should_rewrite:
            rewritten = agent.rewrite_query(ctx.backend, req.history, req.query)
            if rewritten:
                retrieval_query = rewritten

        # Precedence: a startup-pinned corpus, then the explicitly-scoped
        # work's author, then auto-detection from the query text.
        resolved_corpus = ctx.corpus or scope_corpus
        if resolved_corpus is None:
            detected = agent.detect_corpus(retrieval_query)
            if detected:
                resolved_corpus = detected
        # Orthographic spelling-variant folding for the BM25 query, keyed on
        # the corpus's original language (e.g. `deu` bridges a historical
        # `Mißrathenen` query to the modernized `Mißratenen` in the index).
        # Computed here so it applies regardless of concept-expansion / backend.
        fold_lang = scope_lang or (
            original_language_for_corpus(resolved_corpus) if resolved_corpus else None
        )
        if resolved_corpus:
            # When a single-author corpus is resolved (either auto-detected
            # or pinned at startup), strip the author-name tokens from the
            # retrieval query — every chunk in the corpus is already from
            # that author, and leaving the name in the embedding query
            # makes vector retrieval surface third-person mentions of the
            # name (letter signatures, colophons) instead of the substantive
            # content the question is actually about. See
            # ``agent.strip_author_keywords`` for the precise scrub.
            retrieval_query = agent.strip_author_keywords(retrieval_query, resolved_corpus)
            retrieval_query = _expand_concepts(ctx, retrieval_query, resolved_corpus)

        missing_pinned: list[str] = []
        with ctx.corpus_lock:
            pinned_hits = resolve_pinned(ctx.index_conn, req.pinned_ids)
            resolved_ids = {h.chunk_id for h in pinned_hits}
            missing_pinned = [cid_ for cid_ in req.pinned_ids if cid_ not in resolved_ids]
            # Auto-detect a work named in the question (e.g. "in the
            # Genealogie der Moral") when the client didn't pin one
            # explicitly. Conservative — only fires when every significant
            # title token is present, so it never silently narrows scope.
            if work_id is None and resolved_corpus:
                work_id = agent.detect_work(ctx.index_conn, retrieval_query, resolved_corpus)
            retrieval = agent.retrieve_passages(
                conn=ctx.index_conn,
                query=req.query,
                top_k=ctx.top_k,
                lang=ctx.lang,
                corpus=resolved_corpus,
                speaker=req.speaker,
                embedder=ctx.embedder,
                retrieval_query=retrieval_query,
                pinned=pinned_hits,
                fold_lang=fold_lang,
                work_id=work_id,
            )

        return ChatPrepared(
            query=req.query,
            history=req.history,
            cid=cid,
            user_msg_id=user_msg_id,
            created_new_conversation=created_new_conversation,
            new_title=new_title,
            retrieval=retrieval,
            missing_pinned=missing_pinned,
            reply_lang=req.reply_lang,
        )
    except Exception:
        rollback_chat_turn(
            ctx,
            created_new_conversation=created_new_conversation,
            cid=cid,
            user_msg_id=user_msg_id,
        )
        raise


def rollback_chat_turn(
    ctx: ChatContext,
    *,
    created_new_conversation: bool,
    cid: str,
    user_msg_id: int,
) -> None:
    """Undo Phase 1 persistence when retrieval/LLM fails."""
    try:
        with ctx.conv_lock:
            if created_new_conversation:
                conversations.delete_conversation(ctx.conversations_conn, cid)
            else:
                conversations.delete_message(ctx.conversations_conn, user_msg_id)
    except Exception:
        # Don't shadow the original failure; an orphan user turn is
        # preferable to losing the root cause.
        _log.exception("chat compensating rollback failed")
