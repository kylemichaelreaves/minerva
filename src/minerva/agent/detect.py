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


# Every name a work answers to: its canonical (for Greek authors,
# Latinized-Greek) title plus the per-language `title_local` names that
# migration 0023 put on editions and translations. Display used those
# from the start; detection did not, so the English name of a
# canonicalised work was unreachable (#164).
_TITLES_SQL = """
    SELECT w.id, w.title FROM works w WHERE LOWER(w.author) = ?
    UNION
    SELECT w.id, t.title_local FROM works w JOIN translations t ON t.work_id = w.id
     WHERE LOWER(w.author) = ? AND t.title_local IS NOT NULL
    UNION
    SELECT w.id, e.title_local FROM works w JOIN editions e ON e.work_id = w.id
     WHERE LOWER(w.author) = ? AND e.title_local IS NOT NULL
"""


def detect_work(conn: sqlite3.Connection, query: str, corpus: str) -> int | None:
    """Resolve a single ``works.id`` named in ``query`` for ``corpus``.

    A work answers to any of its names: the canonical ``works.title``
    and the per-language ``title_local`` values on its editions and
    translations. So both "Plato's Politeia" and "Plato's Republic"
    resolve to the same work.

    Conservative by design: a title matches only when EVERY significant
    (non-stopword) token of it appears in the lowercased query. When
    several titles qualify (a query naming a long title that contains a
    shorter one), the most specific — most significant tokens — wins.
    Two *different* works tying at that specificity is ambiguity and
    yields ``None``; several titles of one work tying is not. Returns
    ``None`` when nothing matches cleanly, so a passing mention never
    silently narrows scope.
    """

    query_tokens = set(_WORD_RE.findall(query.lower()))
    best_ids: set[int] = set()
    best_n = 0
    for work_id, title in conn.execute(_TITLES_SQL, (corpus.lower(),) * 3):
        sig = [t for t in _WORD_RE.findall(title.lower()) if t not in _TITLE_STOPWORDS]
        if not sig or not all(t in query_tokens for t in sig):
            continue
        if len(sig) > best_n:
            best_ids, best_n = {work_id}, len(sig)
        elif len(sig) == best_n:
            best_ids.add(work_id)
    # A tie between two *different* works is genuine ambiguity; several
    # titles of the same work tying is not.
    return next(iter(best_ids)) if len(best_ids) == 1 else None


def _title_tokens(conn: sqlite3.Connection, corpus: str) -> set[str]:
    """Every token of every name every work of *corpus* answers to."""

    toks: set[str] = set()
    for _work_id, title in conn.execute(_TITLES_SQL, (corpus.lower(),) * 3):
        toks.update(_WORD_RE.findall((title or "").lower()))
    return toks


def detect_corpus(query: str, conn: sqlite3.Connection | None = None) -> str | None:
    """Resolve the single corpus named in *query*, or ``None``.

    A query naming two authors must not be scoped to one of them — half
    the question would be silently dropped. But a *work* title that
    happens to equal another author's name is not a second author, and
    keywords alone cannot tell the two apart: "Plato's Phaedrus" hits
    ``plato`` and (via Phaedrus the Latin fabulist) ``aesop``, and used
    to scope to neither (#170).

    So when more than one corpus matches and *conn* is given, each
    candidate is asked whether it can account for the other candidates'
    keywords as titles of its own works. "Plato's Phaedrus" -> Plato has
    a work called Phaedrus, Aesop has none called Plato, so Plato is the
    author and Phaedrus the work. Exactly one candidate must survive;
    a genuine two-author query leaves none, and stays unscoped. Without
    *conn* the pre-#170 behaviour stands.
    """

    matched: dict[str, set[str]] = {}
    for word in _WORD_RE.findall(query.lower()):
        c = AUTHOR_KEYWORDS.get(word)
        if c:
            matched.setdefault(c, set()).add(word)

    if len(matched) == 1:
        return next(iter(matched))
    if len(matched) < 2 or conn is None:
        return None

    survivors = [
        cand
        for cand in matched
        if {w for c, words in matched.items() if c != cand for w in words}
        <= _title_tokens(conn, cand)
    ]
    return survivors[0] if len(survivors) == 1 else None


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
