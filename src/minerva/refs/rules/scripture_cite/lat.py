"""Latin Vulgate scripture cite and formulaic-quote rules."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache

from .. import Candidate, ChunkInfo
from ._base import BaseScriptureCiteRule
from .lexicon import _AMBIGUOUS_BARE, _CITE_RE, _LEXICON, _WORD_COLLISION


@dataclass(frozen=True)
class ScriptureCiteRule(BaseScriptureCiteRule):
    """Fires on Latin Vulgate cite-string syntax in chunk text.

    Each match becomes one :class:`Candidate` with
    ``target_locator`` set to ``"<SBL-abbr> <chap>:<verse>"``. The
    runner's ``insert_candidate`` then performs an exact-section
    lookup against Vulgate chunks and binds ``target_chunk_id``
    directly when a verse is matched.
    """

    name: str = "scripture_cite_vulgate"
    target_author: str = "Vulgate"
    langs: tuple[str, ...] = ("lat",)

    lexicon = _LEXICON
    cite_re = _CITE_RE
    ambiguous_bare = _AMBIGUOUS_BARE
    word_collision = _WORD_COLLISION
    # "ad Cor." / "ad Thess." / "ad Tim." mark an epistle but not the
    # number, so they stay ambiguous like the bare form (issue #52).
    non_disambiguating_prefixes = frozenset({"ad"})

    @classmethod
    def canonical_abbr(cls, abbr: str) -> str:
        """Fold the lowercase spelled-out forms onto their capitalised
        entry. `_CITE_RE` admits `sapientiae` alongside `Sapientiae`
        (#511); every lookup table is keyed on the latter, and
        `_AMBIGUOUS_BARE` in particular must still see `Corinthiorum`
        in `corinthiorum 13-4` or the lowercase branch would launder an
        ambiguous cite into a confident one."""

        return abbr[:1].upper() + abbr[1:]


# ──────────────────────────────────────────────────────────────────
# Roman-numeral-chapter cites (19th-c editions)
# ──────────────────────────────────────────────────────────────────
#
# `_CITE_RE` takes an Arabic chapter, which is what the 16th–17th-c
# Latin printings use. 19th-century editors set the chapter in
# lowercase Roman and the verse in Arabic — "1 Cor. ix. 9", "Rom. viii.
# 5", "Matth. xxv. 41" — and prefix the numbered books with an Arabic
# ordinal where the older convention used "I Cor."
#
# This matters because of what the corpus reads. Re-sourcing the Latin
# Hobbes to Molesworth's 1839 *Opera Latina* (#535) fixed a text that
# was unusable OCR of a long-s printing, and moved every one of its
# scripture citations into this convention at the same time. The Latin
# Hobbes went from 276 Vulgate cross-references to 4.
#
# A SIBLING RULE, not a widening of `_CITE_RE`, for the same reason
# `ScriptureCiteRuleFrRoman` is one in `fr.py`. Measured across the
# corpus before writing it — chapter-in-Roman citation shapes:
#
#     Hobbes (Molesworth)   555      Aquinas      0
#     Spinoza                 7      Augustine    0
#                                    Descartes    0
#
# Widening the shared pattern would have put every Latin author at risk
# of new false positives for a benefit confined to one of them.
#
# The chapter group `[ivxlc]{1,7}` is also how plenty of short Latin
# words are spelled, so it is gated three ways: the book abbreviation
# must be in the lexicon, the numeral must carry a trailing period
# (Molesworth always prints one), and `_parse_cite_num` in the base
# rule rejects anything outside 1–176. The verse stays Arabic-only —
# the same call `fr.py` makes, and for the same reason: a Roman verse
# group swallows ordinary words that follow a chapter number.
_CITE_RE_LAT_ROMAN = re.compile(
    # Ordinal prefix, Arabic ("1 Cor.") or Roman ("I Cor.").
    r"(?:\b(?P<prefix>I{1,3}V?|[1-4])\s+)?"
    # Book abbreviation, always capitalised in this convention, always
    # followed by its period. Spacing after it is optional — the scan
    # contains "Psal.lxxxiv. 11".
    r"\b(?P<abbr>[A-Z][a-zëæoœ]{1,15})\.\s*"
    # Chapter in lowercase Roman, with its own period.
    r"(?P<chap>[ivxlc]{1,7})\.\s*"
    # Verse in Arabic. Optional trailing range ("xv. 22-24" → 15:22).
    r"(?P<verse>\d{1,3})"
    r"(?:\s*[-–]\s*\d{1,3})?"
)


@dataclass(frozen=True)
class ScriptureCiteRuleLatRoman(BaseScriptureCiteRule):
    """Latin rule accepting a Roman-numeral chapter with an Arabic
    verse — the 19th-century convention Molesworth uses throughout the
    *Opera Latina*, and so the form every scripture citation in the
    Latin Hobbes now takes."""

    name: str = "scripture_cite_vulgate_roman"
    target_author: str = "Vulgate"
    langs: tuple[str, ...] = ("lat",)

    lexicon = _LEXICON
    cite_re = _CITE_RE_LAT_ROMAN
    ambiguous_bare = _AMBIGUOUS_BARE
    word_collision = _WORD_COLLISION
    non_disambiguating_prefixes = frozenset({"ad"})

    @classmethod
    def canonical_abbr(cls, abbr: str) -> str:
        return abbr[:1].upper() + abbr[1:]


# ──────────────────────────────────────────────────────────────────
# Formulaic-quote rule (verse text instead of locator)
# ──────────────────────────────────────────────────────────────────
#
# Aquinas cites scripture two ways:
#   1. By locator: "Matth. 5-48" — handled by ScriptureCiteRule above.
#   2. By formulaic introducer + quoted verse text:
#        "in Psalmo: tu autem domine in aeternum permanes"
#        "Psalmista: verbo domini caeli firmati sunt"
#        "sicut illud Psalmi: non est similis tibi in diis"
#      The Psalm number is omitted — the verse text IS the locator.
#
# These can't be resolved at rule time (we don't know which Psalm
# without reading the verse). The rule captures `quoted_phrase` and
# leaves chunk-binding to embed-verify Pass A.
#
# ⚠ This used to say Pass A "compares the quoted text's embedding
# against every Vulgate Psalm chunk and pins the best cosine match",
# stated as though that resolves. It resolved to the wrong verse about a
# third of the time (issue #269) — the litany Psalms, Ps 135 above all,
# act as a cosine attractor for any short liturgical phrase, so "omnia
# in sapientia fecisti" (Ps 103:24) was pinned to Ps 135:7. Pass A now
# LOCATES the quotation as a string first (`refs/quote_match.py`) and
# only falls back to cosine for the promote/reject decision — and in
# that case deliberately binds no verse at all.

_FORMULAIC_QUOTE_END_RE = r"[.;?!]"  # Latin sentences end at . ; ? or !
_FORMULAIC_MIN_QUOTE_CHARS = 15  # below this is noise (false intros)
_FORMULAIC_MAX_QUOTE_CHARS = 250  # above this likely overran the verse


@cache
def _formulaic_pattern(introducer_patterns: tuple[str, ...]) -> re.Pattern[str]:
    alt = "|".join(f"(?:{p})" for p in introducer_patterns)
    body = (
        rf"\b(?:{alt})"
        # Optional Latin verbs that bridge intro and quote
        # ("dicit", "dicitur", "ait", "inquit", "legitur",
        # "namque", "enim", "de X").
        rf"(?:\s+(?:dicit(?:ur)?|ait|inquit|legitur|namque|enim|de\s+\w+))?"
        rf"\s*:\s+"
        rf"(?P<quote>[A-Za-zæëœÆËŒ][^.:;!?]{{{_FORMULAIC_MIN_QUOTE_CHARS - 1},{_FORMULAIC_MAX_QUOTE_CHARS}}}?)"
        rf"\s*{_FORMULAIC_QUOTE_END_RE}"
    )
    return re.compile(body, re.IGNORECASE)


@dataclass(frozen=True)
class FormulaicQuoteRule:
    """Fires on ``<introducer>: <verse text>.`` patterns.

    The rule emits a :class:`Candidate` whose ``target_work`` is
    known (Psalms, Romans, etc.) but ``target_locator`` is left
    NULL — embed-verify Pass A handles chunk binding, by locating the
    quotation in the target work's text (see the ⚠ note above; it used
    to bind by cosine and got the verse wrong about a third of the
    time).

    Confidence starts low (0.55) because the introducer alone isn't
    proof; Pass A promotes high-cosine matches to 0.85+ and rejects
    low-cosine ones. The middle band falls to llm-verify for triage.

    ``introducer_patterns`` are regex fragments (un-anchored, no
    capture groups). The rule combines them into one big alternation
    and matches case-insensitively (Latin proper-noun casing is
    inconsistent across editions; the introducer stems — "Psalm",
    "Apostol", "Augustin" — don't collide with common Latin words).
    """

    name: str
    target_author: str
    target_work: str
    introducer_patterns: tuple[str, ...]
    confidence: float = 0.55
    reference_type: str = "quotes"
    source_method: str = "rule_weak"
    langs: tuple[str, ...] = ("lat",)

    def _pattern(self) -> re.Pattern[str]:
        # Cached on the introducer tuple itself (`@cache` above) —
        # two rules sharing a name can never collide on a pattern.
        return _formulaic_pattern(self.introducer_patterns)

    def scan(self, chunk: ChunkInfo) -> Iterable[Candidate]:
        if self.langs and chunk.lang not in self.langs:
            return
        if chunk.author == self.target_author:
            return
        for m in self._pattern().finditer(chunk.text):
            quote = m.group("quote").strip()
            if len(quote) < _FORMULAIC_MIN_QUOTE_CHARS:
                continue
            yield Candidate(
                source_chunk_id=chunk.chunk_id,
                source_span_start=m.start("quote"),
                source_span_end=m.end("quote"),
                # The formula plus the quote, capped at 120 — the only
                # place `source_form_snapshot` is truncated anywhere in
                # refs. 120 is borrowed from `_make_chunk_id`'s hash
                # window and means something different here, so do not
                # read the two as linked. The consequence is not local:
                # a quote longer than the cap leaves a snapshot that
                # stops mid-word, so the snapshot is neither equal to
                # nor a superstring of the span it describes, and any
                # consumer testing for containment misreads those rows
                # as damaged (#545 — 9 of 212 live rows).
                source_form_snapshot=m.group(0)[:120],
                target_author=self.target_author,
                target_work=self.target_work,
                target_locator=None,  # embed-verify Pass A binds chunk
                reference_type=self.reference_type,
                confidence=self.confidence,
                source_method=self.source_method,
                quoted_phrase=quote,
            )
