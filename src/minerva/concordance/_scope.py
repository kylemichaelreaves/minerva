"""Shared scope SQL and concordance constants."""

from __future__ import annotations

from typing import Any

from ..errors import BadRequestError

_DEFAULT_INDEX_LIMIT = 200
_MAX_INDEX_LIMIT = 1000
_DEFAULT_KWIC_LIMIT = 50
_MAX_KWIC_LIMIT = 200
_KWIC_CONTEXT_RADIUS = 60   # characters on each side of the match

# Default POS set for the leaderboard. Strips function words
# (DET/ADP/CCONJ/SCONJ/PRON/AUX/PART/PUNCT/SYM/SPACE) so the top
# entries are content words a philology reader actually wants —
# Geist, Wesen, Begriff (DEU); essence, substance (ENG); etc.
# User can override with ?pos_in=NOUN,VERB,ADJ,DET,...
_DEFAULT_CONTENT_POS = ("NOUN", "VERB", "ADJ", "PROPN")

# Closing punctuation that should hug the preceding word (no leading space).
_ATTACHED_TRAIL = ",.;:!?)]}»"
# Opening punctuation that should hug the following word.
_ATTACHED_LEAD = "([{«"


# ──────────────────────────────────────────────────────────────────
#  Shared scope-clause builder
# ──────────────────────────────────────────────────────────────────


def _scope_clause(
    scope: str, author: str | None, work: str | None
) -> tuple[str, list[Any]]:
    """Translate (scope, author, work) into a SQL fragment + params
    that filters the JOIN to ``chunks_full``.

    Always emits language as ``cf.lang = ?`` — that param is appended
    by the caller. The scope check follows.
    """

    if scope not in ("corpus", "author", "work"):
        raise BadRequestError(
            "'scope' must be one of: corpus, author, work",
        )
    if scope == "author" and not author:
        raise BadRequestError("'scope=author' requires an 'author' query param")
    if scope == "work" and not work:
        raise BadRequestError("'scope=work' requires a 'work' query param")

    if scope == "corpus":
        return "", []
    if scope == "author":
        return " AND cf.author = ?", [author]
    return " AND cf.work = ?", [work]

