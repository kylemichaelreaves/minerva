"""Shared scripture-citation rule machinery.

The four language variants (Latin Vulgate, German Luther, English
KJV, French Sacy) all run the identical pipeline — regex over the
chunk text, ``(prefix, abbr)`` lexicon lookup, SBL-locator
construction, ambiguity discount — and differ only in their
parametrization: the lexicon dict, the cite regex, the
ambiguous-bare set, and the target/langs defaults. Each language
module subclasses :class:`BaseScriptureCiteRule` and supplies those
four as plain class attributes (``ClassVar`` — configuration, not
per-instance state).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import ClassVar

from .. import Candidate, ChunkInfo
from .lexicon import (
    _CONF_AMBIGUOUS,
    _CONF_CHAPTER_ONLY,
    _CONF_FULL,
    _sbl_abbr_for,
)

_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}


def _parse_cite_num(raw: str) -> int | None:
    """Chapter/verse token → int. Accepts Arabic digits and Roman
    numerals in either case — 19th-c French editions cite chapters in
    lowercase Roman ("Luc, xxiii, 34" = Luke 23:34). Returns None for
    malformed or implausible values (0, or beyond Ps 150) so the
    caller can skip the match instead of emitting garbage."""

    raw = raw.strip()
    if raw.isdigit():
        n = int(raw)
        return n if 1 <= n <= 176 else None  # Ps 119 has 176 verses
    total = 0
    prev = 0
    for ch in reversed(raw.lower()):
        val = _ROMAN_VALUES.get(ch)
        if val is None:
            return None
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    return total if 1 <= total <= 176 else None


def _abbr_carried_period(m: re.Match[str]) -> bool:
    """Did the matched abbreviation keep its trailing period?

    None of the four language regexes captures the period as a group —
    it is written ``\\.?`` so that spelled-out genitive forms
    ("Isaiae 54-13") still match — so read it off the subject string
    at the abbreviation's end rather than adding a group to a pattern
    three other rules inherit.
    """

    end = m.end("abbr")
    return m.string[end : end + 1] == "."


@dataclass(frozen=True)
class BaseScriptureCiteRule:
    """Fires on scripture cite-string syntax in chunk text.

    Each match becomes one :class:`Candidate` with ``target_locator``
    set to ``"<SBL-abbr> <chap>:<verse>"``. The runner's
    ``insert_candidate`` then performs an exact-section lookup
    against the target Bible's chunks and binds ``target_chunk_id``
    directly when a verse is matched.

    Subclasses configure the language via class attributes:

    * ``lexicon`` — ``(prefix, abbr) → canonical book`` mapping.
    * ``cite_re`` — compiled cite regex with named groups ``prefix``,
      ``abbr``, ``chap``, ``verse``. The ``verse`` group may be
      optional (Latin chapter-only cites) or required (vernaculars).
    * ``ambiguous_bare`` — bare abbrevs whose default resolution is
      ambiguous (Cor without I/II); emitted at low confidence.
    * ``word_collision`` — abbrevs that are also ordinary words in
      the language; emitted at low confidence only when the cite's
      optional trailing period is absent.

    and instance-field defaults for ``name`` / ``target_author`` /
    ``langs``.
    """

    name: str = ""
    target_author: str = ""
    langs: tuple[str, ...] = ()

    # Per-language configuration — set as plain class attributes on
    # subclasses, never per-instance.
    lexicon: ClassVar[dict[tuple[str | None, str], str]]
    cite_re: ClassVar[re.Pattern[str]]
    ambiguous_bare: ClassVar[frozenset[str]]
    # Prefixes that appear on a cite but do NOT disambiguate an
    # ambiguous abbrev (e.g. the Latin preposition "ad": "ad Cor" is
    # still 1-vs-2 Corinthians). Ordinal prefixes (I/II/III/…) are
    # absent from this set because they DO pin the number. Empty by
    # default — only the Latin subclass overrides it (issue #52).
    non_disambiguating_prefixes: ClassVar[frozenset[str]] = frozenset()
    # Abbrevs that double as ordinary words in this language, for
    # which the cite's *optional* trailing period is the only evidence
    # of citation intent ("Ex 3 modis" is prose; "Ex. 3-14" is a
    # cite). Empty by default — only the Latin subclass overrides it
    # (issue #508).
    word_collision: ClassVar[frozenset[str]] = frozenset()

    @classmethod
    def canonical_abbr(cls, abbr: str) -> str:
        """The matched abbrev as this language's tables spell it.

        Identity by default. `scan` looks the result up in all three
        of ``lexicon``, ``ambiguous_bare`` and ``word_collision``, so a
        subclass whose regex can match more than one spelling of the
        same abbrev folds them here and leaves those tables with one
        entry per book. Only the Latin subclass overrides it (#511) —
        the vernacular regexes still require a capital initial, so for
        them there is nothing to fold.

        ``source_form_snapshot`` keeps the literal matched text; this
        affects lookup only."""

        return abbr

    def scan(self, chunk: ChunkInfo) -> Iterable[Candidate]:
        if self.langs and chunk.lang not in self.langs:
            return
        # Don't fire on the target Bible's own chunks — Genesis
        # quoting Genesis isn't a useful cross-reference.
        if chunk.author == self.target_author:
            return

        for m in self.cite_re.finditer(chunk.text):
            prefix = m.group("prefix")
            abbr = self.canonical_abbr(m.group("abbr"))
            book = self.lexicon.get((prefix, abbr))
            if book is None:
                continue
            sbl = _sbl_abbr_for(book)
            if sbl is None:
                # Lexicon out of sync with the BCV table. Logged
                # silently rather than raised — the rules pass
                # processes thousands of chunks and one missing
                # entry shouldn't kill the batch.
                continue

            chap = _parse_cite_num(m.group("chap"))
            if chap is None:
                continue
            verse_raw = m.group("verse")

            if verse_raw:
                verse = _parse_cite_num(verse_raw)
                if verse is None:
                    continue
                target_locator = f"{sbl} {chap}:{verse}"
                conf = _CONF_FULL
            else:
                # Chapter-level locator (Latin only — the vernacular
                # regexes require a verse): no chunks.section will
                # match exactly (Bible sections are per-verse), so
                # the chunk binder leaves target_chunk_id NULL. The
                # row is still useful for "Aquinas cites Matthew 5
                # (no specific verse)" curation.
                target_locator = f"{sbl} {chap}"
                conf = _CONF_CHAPTER_ONLY

            if abbr in self.ambiguous_bare and (
                prefix is None or prefix in self.non_disambiguating_prefixes
            ):
                conf = _CONF_AMBIGUOUS

            # A word-collision abbrev without its period is prose as
            # far as the rule can tell, whether or not a verse follows.
            if abbr in self.word_collision and not _abbr_carried_period(m):
                conf = _CONF_AMBIGUOUS

            yield Candidate(
                source_chunk_id=chunk.chunk_id,
                source_span_start=m.start(),
                source_span_end=m.end(),
                source_form_snapshot=m.group(0),
                target_author=self.target_author,
                target_work=book,
                target_locator=target_locator,
                reference_type="cites",
                confidence=conf,
                source_method="rule_strong" if conf >= 0.85 else "rule_weak",
            )
