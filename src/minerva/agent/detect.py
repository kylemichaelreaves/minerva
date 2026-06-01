"""Corpus detection from query keywords."""

from __future__ import annotations

import re

from ..corpus_registry import AUTHOR_KEYWORDS

_WORD_RE = re.compile(r"\b[\w]+\b", re.UNICODE)


def detect_corpus(query: str) -> str | None:
    found: set[str] = set()
    for word in _WORD_RE.findall(query.lower()):
        c = AUTHOR_KEYWORDS.get(word)
        if c:
            found.add(c)
            if len(found) > 1:
                return None
    return next(iter(found)) if found else None


def strip_author_keywords(query: str, corpus: str) -> str:
    if not query or not corpus:
        return query
    out = _WORD_RE.sub(
        lambda m: "" if AUTHOR_KEYWORDS.get(m.group(0).lower()) == corpus else m.group(0),
        query,
    )
    out = re.sub(r"\s+", " ", out).strip()
    out = re.sub(r"\s+([,.?!;:])", r"\1", out)
    return out if out else query
