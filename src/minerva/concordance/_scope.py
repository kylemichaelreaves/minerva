"""Shared scope SQL and concordance constants."""

from __future__ import annotations

from typing import Any

from ..errors import BadRequestError

_DEFAULT_INDEX_LIMIT = 200
_MAX_INDEX_LIMIT = 1000
_DEFAULT_KWIC_LIMIT = 50
_MAX_KWIC_LIMIT = 200
_KWIC_CONTEXT_RADIUS = 60  # characters on each side of the match

# Default POS set for the leaderboard. Strips function words
# (DET/ADP/CCONJ/SCONJ/PRON/AUX/PART/PUNCT/SYM/SPACE) so the top
# entries are content words a philology reader actually wants —
# Geist, Wesen, Begriff (DEU); essence, substance (ENG); etc.
# User can override with ?pos_in=NOUN,VERB,ADJ,DET,...
#
# NOTE: index_queries.lemma_index's docstring claims the default also
# includes ADV — it does not, and adding ADV here would reshuffle the
# UI leaderboard. The docstring over there is the drifted side; this
# tuple is the source of truth.
_DEFAULT_CONTENT_POS = ("NOUN", "VERB", "ADJ", "PROPN")

# Re-export snippet punctuation constants for legacy imports.


# ──────────────────────────────────────────────────────────────────
#  Shared scope-clause builder
# ──────────────────────────────────────────────────────────────────


# The ``author`` and ``work`` query params are tab-joined when multiple
# values are selected: a work title can contain a comma (Kant's "On the
# Common Saying: …, but…"), so comma-splitting would corrupt it, whereas
# no title/author name contains a tab and the tab round-trips cleanly
# through URLSearchParams / parse_qs.
_MULTI_SEP = "\t"


def _parse_multi(query: dict[str, str], key: str) -> list[str]:
    raw = query.get(key) or ""
    return [v for v in (s.strip() for s in raw.split(_MULTI_SEP)) if v]


def parse_works(query: dict[str, str]) -> list[str]:
    """Parse the (possibly multi-valued) ``work`` query param. A bare
    single title (no separator) returns a one-element list, so existing
    single-work callers/URLs keep working unchanged."""

    return _parse_multi(query, "work")


def parse_authors(query: dict[str, str]) -> list[str]:
    """Parse the (possibly multi-valued) ``author`` query param. A bare
    single name returns a one-element list (back-compatible)."""

    return _parse_multi(query, "author")


def _scope_clause(
    scope: str, authors: list[str], works: list[str]
) -> tuple[str, list[Any]]:
    """Translate (scope, authors, works) into a SQL fragment + params
    that filters the JOIN to ``chunks_full``.

    Always emits language as ``cf.lang = ?`` — that param is appended
    by the caller. The scope check follows. ``authors``/``works`` may
    each name one or more values (``scope=author`` → ``cf.author IN
    (...)``; ``scope=work`` → ``cf.work IN (...)``).
    """

    if scope not in ("corpus", "author", "work"):
        raise BadRequestError(
            "'scope' must be one of: corpus, author, work",
        )
    if scope == "author" and not authors:
        raise BadRequestError("'scope=author' requires at least one 'author' query param")
    if scope == "work" and not works:
        raise BadRequestError("'scope=work' requires at least one 'work' query param")

    if scope == "corpus":
        return "", []
    values = authors if scope == "author" else works
    col = "cf.author" if scope == "author" else "cf.work"
    placeholders = ",".join("?" * len(values))
    return f" AND {col} IN ({placeholders})", list(values)
