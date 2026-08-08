"""Lexical binding of a quoted phrase to the verse it quotes.

``FormulaicQuoteRule`` (``refs/rules/scripture_cite/lat.py``) fires on
``in Psalmo: <verse text>.`` — an introducer plus the quoted words, with
no chapter:verse locator. The Psalm number is implicit in the quote, so
something has to find the verse.

That job used to belong entirely to embed-verify Pass A's cosine search,
and cosine is the wrong instrument for it. These are *exact quotations*
of five or six words of liturgical Latin, and the litany Psalms — 135
above all, with its repeated *quoniam in æternum misericordia eius* —
act as an attractor for any short devotional phrase. It bound the wrong
verse for a large fraction of the population (issue #269): *omnia in
sapientia fecisti* is Ps 103:24 and went to Ps 135:7; *Gustate et videte
quam dulcis est Dominus* is Ps 33:9 and went to Ps 4:4.

A quotation is a *string*, so match it as one. This module normalizes
away the orthographic variation that separates a scholastic author's
quotation from the Vulgate's own spelling, then looks for the phrase
in the candidate verses:

* Unicode diacritics and macrons dropped (``præcinxit`` → ``praecinxit``).
* ``æ``/``œ`` expanded to ``ae``/``oe``.
* ``u``/``v`` folded together and ``i``/``j`` folded together — Latin
  editions disagree freely (*uidetis* / *videtis*, *iustus* / *justus*),
  and Aquinas's text and the Clementine Vulgate here are different
  editions.
* Case dropped; runs of punctuation and whitespace become one space.

Exact containment is the primary signal. When the author quotes loosely
(or an OCR slip breaks a word) the longest run of consecutive matching
tokens carries it, which is deliberately stricter than bag-of-words
overlap: *Deus / meus / in / te* shares four common tokens with half the
Psalter, but the four in sequence pin a verse.

Nothing here is Psalms-specific; it takes any phrase and any candidate
chunks.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

# Expanded before diacritic stripping: NFD on 'æ' does not decompose it
# into 'a' + 'e', so it would otherwise survive as a bare 'æ'.
_LIGATURES = {
    "æ": "ae",
    "Æ": "ae",
    "œ": "oe",
    "Œ": "oe",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ß": "ss",
}

# u/v and i/j are the same letter in classical orthography; editions
# split them differently. Fold each pair onto one representative so
# `uidete` and `videte` compare equal.
_LETTER_FOLD = str.maketrans({"u": "v", "j": "i"})

_NON_LETTER_RE = re.compile(r"[^a-z0-9]+")

# A contiguous run this long identifies a verse on its own. Below it,
# short devotional formulae ("Deus meus", "in aeternum") recur across
# the Psalter and would bind arbitrarily.
_MIN_TOKEN_RUN = 4

# How much of the phrase an anchored match must account for, measured as
# order-preserving subsequence coverage (NOT the contiguous run — see
# ``_ANCHORED`` vs ``_NEAR_TOTAL`` below).
_MIN_COVERAGE = 0.6

# The variant-spelling path. One differing token splits the contiguous
# run in half, so a nine-word quotation with a single edition variant
# cannot clear ``_MIN_TOKEN_RUN`` on run length alone even though it is
# plainly the same verse:
#
#   Aquinas   "cor meum et caro mea exultaverunt in Deum vivum"
#   Ps 83:3   "cor meum et caro mea exsultaverunt in Deum vivum"
#                                    ^ Clementine keeps the s
#
# Coverage there is 8/9; the longest run is 5. Admitting it needs a
# high-coverage clause with a smaller anchor. The bar has to stay above
# the case where the wording genuinely differs, which must NOT bind:
#
#   Aquinas   "Gustate et uidete quam dulcis  est Dominus"   coverage 5/7
#   Ps 33:9   "Gustate et videte quoniam suavis est Dominus"  run 3
#
# 0.8 / 3 separates them. The second is a different Psalter recension,
# not a spelling variant, and no amount of string matching should claim
# it — llm-verify triages that band.
_NEAR_TOTAL_COVERAGE = 0.8
_NEAR_TOTAL_MIN_RUN = 3


def normalize_latin(text: str) -> str:
    """Fold a Latin string to its comparison form.

    Idempotent, and safe on Greek or English input (they simply lose
    their diacritics and case) — but tuned for Latin.
    """

    for lig, expansion in _LIGATURES.items():
        text = text.replace(lig, expansion)
    # NFD splits 'é' into 'e' + combining acute; drop the marks.
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(
        ch for ch in decomposed if not unicodedata.combining(ch)
    )
    folded = stripped.lower().translate(_LETTER_FOLD)
    return _NON_LETTER_RE.sub(" ", folded).strip()


def _tokens(normalized: str) -> list[str]:
    return normalized.split()


def _longest_common_run(phrase_tokens: list[str], text_tokens: list[str]) -> int:
    """Length of the longest run of consecutive tokens shared by both.

    Standard DP over the two token lists; the phrase is a handful of
    words and a verse is a couple of dozen, so the quadratic table is
    trivially small.
    """

    if not phrase_tokens or not text_tokens:
        return 0
    prev = [0] * (len(text_tokens) + 1)
    best = 0
    for p_tok in phrase_tokens:
        cur = [0] * (len(text_tokens) + 1)
        for j, t_tok in enumerate(text_tokens, start=1):
            if p_tok == t_tok:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def _subsequence_coverage(phrase_tokens: list[str], text_tokens: list[str]) -> int:
    """Longest common *subsequence* length — how many of the phrase's
    tokens appear in the candidate in the right order, gaps allowed.

    Order-preserving on purpose. Bag-of-words overlap would let a verse
    score highly just for containing *deus*, *in* and *est* somewhere;
    requiring the original sequence means a high score is evidence about
    this verse rather than about Latin.
    """

    if not phrase_tokens or not text_tokens:
        return 0
    prev = [0] * (len(text_tokens) + 1)
    for p_tok in phrase_tokens:
        cur = [0] * (len(text_tokens) + 1)
        for j, t_tok in enumerate(text_tokens, start=1):
            cur[j] = prev[j - 1] + 1 if p_tok == t_tok else max(prev[j], cur[j - 1])
        prev = cur
    return prev[-1]


@dataclass(frozen=True)
class LexicalMatch:
    """A quoted phrase located in a candidate chunk."""

    chunk_id: str
    #: True when the whole normalized phrase appears verbatim.
    exact: bool
    #: Longest run of consecutive shared tokens.
    run: int
    #: Order-preserving subsequence coverage of the phrase, in [0, 1].
    coverage: float


def all_lexical_matches(
    phrase: str,
    candidates: Iterable[tuple[str, str]],
    *,
    min_token_run: int = _MIN_TOKEN_RUN,
    min_coverage: float = _MIN_COVERAGE,
) -> list[LexicalMatch]:
    """Every chunk among ``candidates`` tied at the best strength.

    ``candidates`` is an iterable of ``(chunk_id, text)``. Returns an
    empty list when nothing clears the bar — which is the point: an
    unbound target is visibly unresolved, whereas a wrong one reads as
    verified.

    Three acceptance paths, in descending strength: whole-phrase
    containment; a long contiguous anchor with decent coverage; and
    near-total coverage with a shorter anchor, which is what admits a
    one-word edition variant. See the constants above for why the last
    two need different bars.

    Weaker matches are dropped, so a list longer than one element means a
    genuine ambiguity: the quotation occurs identically in more than one
    verse and the string says nothing about which was meant (issue #276).
    The result is ordered by ``chunk_id`` so a caller that just takes the
    first gets the same answer on every run.
    """

    norm_phrase = normalize_latin(phrase)
    phrase_tokens = _tokens(norm_phrase)
    if not phrase_tokens:
        return []
    n = len(phrase_tokens)

    best: LexicalMatch | None = None
    tied: list[LexicalMatch] = []
    for chunk_id, text in candidates:
        norm_text = normalize_latin(text)
        if not norm_text:
            continue
        # Containment counts only once the phrase is long enough to
        # identify a verse. "in aeternum" is contained verbatim in every
        # litany verse of Ps 135 and distinguishes none of them, so
        # taking the first would reproduce the arbitrary binding this
        # module exists to remove. FormulaicQuoteRule's own 15-char floor
        # makes such phrases rare rather than impossible, and a wrong
        # binding is the expensive failure here.
        if n >= min_token_run and norm_phrase in norm_text:
            found = LexicalMatch(
                chunk_id=chunk_id, exact=True, run=n, coverage=1.0
            )
        else:
            text_tokens = _tokens(norm_text)
            run = _longest_common_run(phrase_tokens, text_tokens)
            coverage = _subsequence_coverage(phrase_tokens, text_tokens) / n
            anchored = run >= min_token_run and coverage >= min_coverage
            near_total = (
                coverage >= _NEAR_TOTAL_COVERAGE and run >= _NEAR_TOTAL_MIN_RUN
            )
            if not (anchored or near_total):
                continue
            found = LexicalMatch(
                chunk_id=chunk_id, exact=False, run=run, coverage=coverage
            )
        # Strongest wins. Equal strength is kept rather than discarded:
        # the string alone cannot choose between two verses that contain
        # the quotation identically, and pretending otherwise is what
        # #276 is about. Weaker candidates are dropped outright — merely
        # clearing the bar does not make a verse an alternative.
        if best is None or _strength_key(found) < _strength_key(best):
            best = found
            tied = [found]
        elif _strength_key(found) == _strength_key(best):
            tied.append(found)
    return sorted(tied, key=lambda m: m.chunk_id)


def best_lexical_match(
    phrase: str,
    candidates: Iterable[tuple[str, str]],
    *,
    min_token_run: int = _MIN_TOKEN_RUN,
    min_coverage: float = _MIN_COVERAGE,
) -> LexicalMatch | None:
    """Single strongest match, or None when nothing clears the bar.

    Ties break on the lowest ``chunk_id`` so repeated runs bind the same
    chunk and don't grow parallel rows through ``insert_candidate``'s
    dedup key. That pick is stable but arbitrary when a quotation really
    does occur in two verses, so a caller that can adjudicate — as
    ``embed_verify`` does, by cosine among the tied pair — should call
    :func:`all_lexical_matches` instead.
    """

    matches = all_lexical_matches(
        phrase,
        candidates,
        min_token_run=min_token_run,
        min_coverage=min_coverage,
    )
    return matches[0] if matches else None


def _strength_key(m: LexicalMatch) -> tuple[int, int, float]:
    """Ascending strength — smaller is better, so the numeric components
    are negated. Excludes ``chunk_id``: two candidates equal on this key
    are genuinely indistinguishable, which is what makes them a tie."""

    return (0 if m.exact else 1, -m.run, -m.coverage)


__all__ = [
    "LexicalMatch",
    "all_lexical_matches",
    "best_lexical_match",
    "normalize_latin",
]
