"""Grounded answer agent — package facade."""

from .compose import answer, compose_answer, compose_answer_stream, render_answer
from .detect import detect_corpus, detect_work, strip_author_keywords
from .language import (
    _system_prompt,
    build_retrieval_query,
    infer_reply_language,
    resolve_reply_lang,
    strip_reply_directive,
)
from .prompts import _compose_messages
from .prompts_constants import LANG_DISPLAY_NAMES, SYSTEM_PROMPT
from .retrieval import (
    Answer,
    RetrievalResult,
    _abstain_message,
    concept_expand,
    retrieve_passages,
    rewrite_query,
)

__all__ = [
    "LANG_DISPLAY_NAMES",
    "SYSTEM_PROMPT",
    "Answer",
    "RetrievalResult",
    "_abstain_message",
    "_compose_messages",
    "_system_prompt",
    "answer",
    "build_retrieval_query",
    "compose_answer",
    "compose_answer_stream",
    "concept_expand",
    "detect_corpus",
    "detect_work",
    "infer_reply_language",
    "render_answer",
    "resolve_reply_lang",
    "retrieve_passages",
    "rewrite_query",
    "strip_author_keywords",
    "strip_reply_directive",
]
