"""Orthographic normalization for full-text search.

The FTS index stores whatever spelling each ingested edition used, and
that often diverges from how users (or the source's own canonical
edition) spell a word. Our zeno.org German texts are modernized — they
store Nietzsche's *Mißrathenen* as *Mißratenen*, *Muth* as *Mut*,
*thun* as *tun* — while readers naturally search the historical 19th-c
spelling. SQLite's ``unicode61 remove_diacritics 2`` tokenizer already
folds case + umlauts symmetrically on both index and MATCH term, so
those bridge automatically; what it *cannot* bridge are letter-sequence
differences (``th``↔``t``, ``ß``↔``ss``, ``ey``↔``ei``, ``-iren``↔``-ieren``).

``canonicalize(text, lang)`` collapses those differences to a single
canonical form. Applied at BOTH ingest (the ``chunks.text_norm`` column
feeding the ``chunks_fts_norm`` index) and query time, it makes matching
symmetric and direction-independent: a historical index + a modern query,
or a modern index + a historical query, both fold to the same form and
meet in the middle. The original ``chunks.text`` is kept verbatim for
display and exact (precision) search; the normalized index is fused in
as a recall booster (see ``retrieve._bm25_search``).

Over-folding a loanword (``Theater`` → ``teater``) is acceptable here:
it only ever runs on the recall leg, the exact index still scores the
true spelling higher, and because the query is folded the same way the
behavior stays self-consistent. Folding is language-scoped — only a
``lang`` with a registered folder is touched, so ``th`` → ``t`` never
mangles English or Latin text.
"""

from __future__ import annotations

import re

# Historical → modern German foldings. The whole string is lowercased
# first (the FTS tokenizer lowercases too, so this loses nothing and
# makes ``ß`` handling uniform).
_DE_TH = re.compile(r"th")  # Muth→Mut, thun→tun, Rath→Rat, Mißrathenen→Mißratenen
_DE_EY = re.compile(r"ey")  # Seyn→Sein, Leyer→Leier
_DE_IREN = re.compile(r"(?<=[a-zß])iren\b")  # studiren→studieren (not bare "Iren")


def _german_canon(text: str) -> str:
    t = text.lower()
    t = t.replace("ß", "ss")
    t = _DE_TH.sub("t", t)
    t = _DE_EY.sub("ei", t)
    t = _DE_IREN.sub("ieren", t)
    return t


# lang code -> whole-text canonicalizer.
_CANONICALIZERS = {"deu": _german_canon}


def has_canonicalizer(lang: str | None) -> bool:
    """Whether ``lang`` has a registered orthographic canonicalizer.

    Lets callers skip the redundant second FTS match when normalization
    would be a no-op (``text_norm`` equals the verbatim text)."""

    return lang in _CANONICALIZERS


def canonicalize(text: str, lang: str | None) -> str:
    """Fold ``text`` to its canonical orthographic form for ``lang``.

    Returns the text unchanged for languages without a registered
    folder (so ``text_norm`` is a faithful copy and the normalized FTS
    behaves like the exact one for those corpora)."""

    folder = _CANONICALIZERS.get(lang or "")
    if folder is None or not text:
        return text
    return folder(text)
