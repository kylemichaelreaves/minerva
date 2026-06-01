"""Answer composition and CLI convenience entry points."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from .. import llm, retrieve
from .language import resolve_reply_lang
from .prompts import _compose_messages
from .retrieval import (
    Answer,
    RetrievalResult,
    _abstain_message,
    _format_passages,
    retrieve_passages,
)


def compose_answer(
    *,
    query: str,
    retrieval: RetrievalResult,
    backend: llm.LLMBackend,
    history: list[llm.Message] | None = None,
    temperature: float = 0.2,
    cite_style: str = "locator",
    reply_lang: str | None = None,
) -> Answer:
    """Given hits from `retrieve_passages`, build the LLM prompt and call
    the backend. No DB access; safe to run with all DB locks released
    (which means a long-running `backend.complete()` doesn't block
    sibling requests)."""

    pinned = retrieval.pinned
    hits = retrieval.hits
    resolved_lang = resolve_reply_lang(query, reply_lang)
    if retrieval.abstain:
        return Answer(
            query=query,
            response=_abstain_message(query, reply_lang=resolved_lang),
            hits=hits,
            abstained=True,
            backend=backend.name,
            pinned=pinned,
        )

    if backend.name == "none":
        return Answer(
            query=query,
            response=_render_passages_for_display(pinned, hits),
            hits=hits,
            abstained=False,
            backend=backend.name,
            pinned=pinned,
        )

    messages = _compose_messages(
        query=query,
        retrieval=retrieval,
        history=history,
        cite_style=cite_style,
        reply_lang=reply_lang,
    )
    text = backend.complete(messages, temperature=temperature)
    return Answer(
        query=query,
        response=text,
        hits=hits,
        abstained=False,
        backend=backend.name,
        pinned=pinned,
    )


def compose_answer_stream(
    *,
    query: str,
    retrieval: RetrievalResult,
    backend: llm.LLMBackend,
    history: list[llm.Message] | None = None,
    temperature: float = 0.2,
    cite_style: str = "locator",
    reply_lang: str | None = None,
) -> Iterator[str]:
    """Yield answer text fragments. Abstain and retrieval-only paths emit
    the full body in one chunk; LLM backends stream token deltas."""

    pinned = retrieval.pinned
    hits = retrieval.hits
    resolved_lang = resolve_reply_lang(query, reply_lang)
    if retrieval.abstain:
        yield _abstain_message(query, reply_lang=resolved_lang)
        return
    if backend.name == "none":
        yield _render_passages_for_display(pinned, hits)
        return
    messages = _compose_messages(
        query=query,
        retrieval=retrieval,
        history=history,
        cite_style=cite_style,
        reply_lang=reply_lang,
    )
    yield from backend.stream_complete(messages, temperature=temperature)


def answer(
    *,
    conn: sqlite3.Connection,
    query: str,
    backend: llm.LLMBackend,
    top_k: int = 6,
    lang: str | None = "eng",
    corpus: str | None = None,
    embedder=None,
    bm25_floor: float = 0.5,
    cosine_floor: float = 0.25,
    temperature: float = 0.2,
    history: list[llm.Message] | None = None,
    retrieval_query: str | None = None,
    pinned: list[retrieve.Hit] | None = None,
    cite_style: str = "locator",
    speaker: str | None = None,
    reply_lang: str | None = None,
) -> Answer:
    """End-to-end: retrieve + compose. Convenience for callers (CLI,
    older tests) that don't need to manage locks between the two steps.
    The server splits the call (see `_handle_chat`)."""

    result = retrieve_passages(
        conn=conn,
        query=query,
        top_k=top_k,
        lang=lang,
        corpus=corpus,
        embedder=embedder,
        bm25_floor=bm25_floor,
        cosine_floor=cosine_floor,
        retrieval_query=retrieval_query,
        pinned=pinned,
        speaker=speaker,
    )
    return compose_answer(
        query=query,
        retrieval=result,
        backend=backend,
        history=history,
        temperature=temperature,
        cite_style=cite_style,
        reply_lang=reply_lang,
    )


def _render_passages_for_display(pinned: list[retrieve.Hit], hits: list[retrieve.Hit]) -> str:
    # No pins: keep the original `ask --llm none` shape — bare passage list,
    # the trailing preview block in render_answer adds the section header.
    if not pinned:
        return _format_passages(hits) if hits else "(nothing in scope)"
    parts: list[str] = ["--- Pinned passages ---", _format_passages(pinned, label_prefix="P")]
    if hits:
        parts.extend(["", "--- Retrieved passages ---", _format_passages(hits)])
    return "\n".join(parts)


def render_answer(ans: Answer) -> str:
    parts = [ans.response.strip(), ""]
    # When pinned passages are inlined into the no-LLM display response,
    # skip the trailing preview blocks to avoid duplication. The original
    # `ask --llm none` shape (bare passage list + trailing previews) is
    # preserved when there are no pins.
    inline = ans.backend == "none" and not ans.abstained and bool(ans.pinned)
    if ans.pinned and not inline:
        parts.append("--- Pinned passages ---")
        for i, h in enumerate(ans.pinned, 1):
            loc = retrieve.format_locator(h.meta)
            preview = h.meta["text"][:180].replace("\n", " ")
            if len(h.meta["text"]) > 180:
                preview += " […]"
            parts.append(f"[P{i}] {loc}\n    {preview}")
    if ans.hits and not inline:
        parts.append("--- Retrieved passages ---")
        for i, h in enumerate(ans.hits, 1):
            loc = retrieve.format_locator(h.meta)
            preview = h.meta["text"][:180].replace("\n", " ")
            if len(h.meta["text"]) > 180:
                preview += " […]"
            parts.append(f"[{i}] {loc}  (score={h.score:.3f})\n    {preview}")
    return "\n".join(parts)
