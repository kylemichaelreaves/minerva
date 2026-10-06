"""Helpers shared between the 0003 backfill migration and the
runtime ``store._resolve_work_refs`` path.

If you change either, change the other — the on-disk
edition-vs-translation split must be reproducible from the legacy
JSONL fields whether you're loading an existing index or reingesting
from scratch.
"""

from __future__ import annotations

import re


from .. import corpus_registry

# Re-exported for code that still reads the legacy dict names.
_ORIGINAL_LANG_BY_CORPUS = {e.id: e.original_lang for e in corpus_registry.CORPORA}
_CITATION_SYSTEM_BY_CORPUS = {e.id: e.citation_system for e in corpus_registry.CORPORA}

_YEAR_RE = re.compile(r"\d{4}")


def citation_system_for_corpus(corpus: str, *, strict: bool = False) -> str:
    return corpus_registry.citation_system_for_corpus(corpus, strict=strict)


def original_language_for_corpus(
    corpus: str,
    *,
    translator: str | None,
    this_lang: str,
    strict: bool = False,
) -> str:
    """Decide the original_language for a new Work record being created
    for the FIRST time at runtime (we only have one chunk's worth of
    information).

    Two markers count as "this chunk is the original":

    * The literal string ``'(Original)'`` in the ``translator`` field,
      set by the Hegel/Kant zeno scrapers when they download a German
      original.
    * Nothing else. A bare ``None`` translator is ambiguous — the
      Perseus Aristotle TEI bundles leave it ``None`` for BOTH the
      Greek source and the English translation, so trusting it would
      let whichever-arrives-first win. The Plato Perseus bundles set
      it to a citation string ("Platonis Opera, ed. ...") for both
      sides, sidestepping the issue, but Aristotle doesn't.

    For any other case (``None``, or a real translator string), we
    defer to the corpus's canonical original language. That gets the
    Aristotle Perseus case right and remains correct for English-only
    Plato (the corpus primary is still 'grc' even when only English
    chunks ever land).
    """

    if translator == "(Original)":
        if strict:
            corpus_registry.original_language_for_corpus(corpus, strict=True)
        return this_lang
    return corpus_registry.original_language_for_corpus(corpus, strict=strict)


def parse_year(raw: str | None) -> int | None:
    """Extract a four-digit year from ``chunks.edition_year``, which is
    sometimes a range ('1812-16/1832', '1781/1787') or just empty."""

    if raw is None:
        return None
    m = _YEAR_RE.search(raw)
    return int(m.group(0)) if m else None
