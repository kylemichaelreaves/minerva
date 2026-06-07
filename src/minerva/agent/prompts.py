"""LLM message assembly for grounded answers."""

from __future__ import annotations

from .. import llm
from .language import _system_prompt, resolve_reply_lang
from .retrieval import _LLM_PASSAGE_CHARS, RetrievalResult, _format_passages


def _compose_messages(
    *,
    query: str,
    retrieval: RetrievalResult,
    history: list[llm.Message] | None,
    cite_style: str,
    reply_lang: str | None = None,
) -> list[llm.Message]:
    pinned = retrieval.pinned
    hits = retrieval.hits
    sections: list[str] = [f"<QUESTION>\n{query}\n</QUESTION>"]
    numeric = cite_style == "numeric"
    if pinned:
        sections.append(
            "<PINNED>\n"
            f"{_format_passages(pinned, max_chars_per_passage=_LLM_PASSAGE_CHARS, label_prefix='' if numeric else 'P')}\n"
            "</PINNED>"
        )
    hit_start = (len(pinned) + 1) if numeric else 1
    sections.append(
        "<PASSAGES>\n"
        f"{_format_passages(hits, max_chars_per_passage=_LLM_PASSAGE_CHARS, start=hit_start) if hits else '(no fresh retrieval matches)'}\n"
        "</PASSAGES>"
    )
    if numeric:
        sections.append(
            "Answer the question following all rules. Use the bracketed "
            "index `[N]` shown before each passage as the citation marker. "
            "Pinned passages and retrieval hits share one continuous numbering "
            "sequence across <PINNED> and <PASSAGES>."
        )
    else:
        sections.append(
            "Answer the question following all rules. Use locators exactly "
            "as shown in parentheses for each passage."
        )
    user_block = "\n\n".join(sections)
    resolved = resolve_reply_lang(query, reply_lang)
    explicit = reply_lang is not None and reply_lang not in ("auto",)
    return [
        llm.Message(
            role="system",
            content=_system_prompt(
                cite_style,
                reply_lang=resolved if explicit else None,
            ),
        ),
        *(history or []),
        llm.Message(role="user", content=user_block),
    ]

