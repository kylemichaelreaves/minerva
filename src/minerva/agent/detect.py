"""Corpus + work detection from query keywords."""

from __future__ import annotations

import re
import sqlite3

from ..corpus_registry import AUTHOR_KEYWORDS

_WORD_RE = re.compile(r"\b[\w]+\b", re.UNICODE)

# Title words too generic to carry scoping signal — articles,
# prepositions, conjunctions across the corpus languages. A work is
# auto-detected only when ALL of its *significant* (non-stopword) title
# tokens appear in the query, so these must be excluded or e.g. "Der
# Antichrist" would match any query containing "der".
_TITLE_STOPWORDS = frozenset(
    {
        # German
        "der", "die", "das", "den", "dem", "des", "ein", "eine", "zur", "zum",
        "von", "vom", "und", "im", "in", "an", "am", "aus", "über", "uber",
        # English
        "the", "a", "of", "on", "to", "and", "or",
        # Latin / French light title words
        "de", "la", "le", "les", "du",
    }
)


def detect_work(conn: sqlite3.Connection, query: str, corpus: str) -> int | None:
    """Resolve a single ``works.id`` named in ``query`` for ``corpus``.

    Conservative by design: a work matches only when EVERY significant
    (non-stopword) token of its title appears in the lowercased query.
    When several works qualify (a query naming a long title that
    contains a shorter one), the most specific — most significant
    tokens — wins. Returns ``None`` when nothing matches cleanly, so a
    passing mention never silently narrows scope.
    """

    query_tokens = set(_WORD_RE.findall(query.lower()))
    best_id: int | None = None
    best_n = 0
    for work_id, title in conn.execute(
        "SELECT id, title FROM works WHERE LOWER(author) = ?", (corpus.lower(),)
    ):
        sig = [t for t in _WORD_RE.findall(title.lower()) if t not in _TITLE_STOPWORDS]
        if sig and all(t in query_tokens for t in sig) and len(sig) > best_n:
            best_id, best_n = work_id, len(sig)
    return best_id


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
