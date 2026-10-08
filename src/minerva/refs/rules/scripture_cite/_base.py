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
from .verse_canon import exists as _verse_exists
from .verse_canon import load_canon

# Loaded once, at import, into a module global rather than looked up per
# call: `refs.rules.fingerprint` hashes the globals a rule's methods read,
# so a regenerated canon invalidates `refs_scan_state` and the next
# `refs build` re-scans. A lookup through the module object would be
# skipped by that walk (it does not descend into modules), and a canon
# change would sit unseen under every already-scanned chunk — #287's
# failure again. The import of `exists` as a function is for the same
# reason: the walk hashes the logic of the helpers it can reach.
_VERSE_CANON = load_canon()

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

    def _resolve_book(self, m: re.Match[str]) -> tuple[str | None, str, str, int] | None:
        """``(prefix, abbr, book, span_start)`` for a match, or None.

        A prefix that pins no lexicon entry is not part of the cite. The
        Latin and French regexes admit a bare digit as an ordinal ("2
        Cor."), and a digit before a book that has no numbered sense is
        something else — an article number ("art. 3 Matth. 5-3") or a
        footnote ("3 Exodus 14: 21", Renan's "1. Matth., VIII, 3"). Dropping
        the whole cite on that miss is what lost them; it now falls back to
        the bare book, with the span starting at the book rather than at
        the stray number."""

        prefix = m.group("prefix")
        abbr = self.canonical_abbr(m.group("abbr"))
        book = self.lexicon.get((prefix, abbr))
        if book is not None:
            return prefix, abbr, book, m.start()
        # Only for a book with no numbered sense. Before "Pet." or "Joh."
        # the digit IS the ordinal, and a miss is a gap in the table;
        # falling back would bind the bare default — 1 Peter, the Gospel
        # of John — which is #719's defect by another route.
        if prefix is None or abbr in self.ambiguous_bare:
            return None
        book = self.lexicon.get((None, abbr))
        if book is None:
            return None
        return None, abbr, book, m.start("abbr")

    def _is_ambiguous(self, prefix: str | None, abbr: str) -> bool:
        return abbr in self.ambiguous_bare and (
            prefix is None or prefix in self.non_disambiguating_prefixes
        )

    def _in_canon(self, book: str, chap: int, verse: int | None) -> str | None:
        """The SBL abbreviation if ``book chap[:verse]`` may exist in the
        target Bible, else None. A target the canon does not cover passes
        unchecked (#519)."""

        sbl = _sbl_abbr_for(book)
        if sbl is None:
            # Lexicon out of sync with the BCV table. Skipped silently
            # rather than raised — the rules pass processes thousands of
            # chunks and one missing entry shouldn't kill the batch.
            return None
        found = _verse_exists(_VERSE_CANON, self.target_author, sbl, chap, verse)
        return sbl if found is not False else None

    def _locate(
        self, prefix: str | None, abbr: str, book: str, chap: int, verse: int | None
    ) -> tuple[str, str] | None:
        """``(book, sbl)`` for a cite whose verse exists, or None.

        When the default book of an ambiguous abbreviation has no such
        verse, the abbreviation's other numbered books are tried, and the
        cite moves to the one that has it — "ad Cor. 5-14" is 2 Cor 5:14,
        because 1 Cor 5 has 13 verses. Two or more fits, or none, and the
        cite is refused rather than guessed (#519)."""

        sbl = self._in_canon(book, chap, verse)
        if sbl is not None:
            return book, sbl
        if not self._is_ambiguous(prefix, abbr):
            return None
        alternates = {
            other
            for (p, a), other in self.lexicon.items()
            if a == abbr and p is not None and other != book
        }
        fits = [(b, s) for b in sorted(alternates) if (s := self._in_canon(b, chap, verse))]
        return fits[0] if len(fits) == 1 else None

    def scan(self, chunk: ChunkInfo) -> Iterable[Candidate]:
        if self.langs and chunk.lang not in self.langs:
            return
        # Don't fire on the target Bible's own chunks — Genesis
        # quoting Genesis isn't a useful cross-reference.
        if chunk.author == self.target_author:
            return

        # Not `finditer`: a match that yields nothing must not consume the
        # text after its abbreviation. In "dicitur 2 Cor. 3-18" the Latin
        # regex first matches `dicitur 2` (a lowercase word and a number),
        # misses the lexicon, and `finditer` would resume past the `2` —
        # leaving "Cor. 3-18" to bind its bare default, 1 Cor (#719). The
        # next search starts right after the failed abbreviation instead,
        # so the digit is still there to be read as an ordinal.
        pos = 0
        while (m := self.cite_re.search(chunk.text, pos)) is not None:
            cand = self._candidate(chunk, m)
            if cand is None:
                pos = m.end("abbr")
                continue
            pos = m.end()
            yield cand

    def _candidate(self, chunk: ChunkInfo, m: re.Match[str]) -> Candidate | None:
        resolved = self._resolve_book(m)
        if resolved is None:
            return None
        prefix, abbr, book, start = resolved

        chap = _parse_cite_num(m.group("chap"))
        if chap is None:
            return None
        verse_raw = m.group("verse")
        verse = _parse_cite_num(verse_raw) if verse_raw else None
        if verse_raw and verse is None:
            return None

        located = self._locate(prefix, abbr, book, chap, verse)
        if located is None:
            return None
        book, sbl = located

        if verse is not None:
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

        if self._is_ambiguous(prefix, abbr):
            conf = _CONF_AMBIGUOUS

        # A word-collision abbrev without its period is prose as
        # far as the rule can tell, whether or not a verse follows.
        if abbr in self.word_collision and not _abbr_carried_period(m):
            conf = _CONF_AMBIGUOUS

        return Candidate(
            source_chunk_id=chunk.chunk_id,
            source_span_start=start,
            source_span_end=m.end(),
            source_form_snapshot=chunk.text[start : m.end()],
            target_author=self.target_author,
            target_work=book,
            target_locator=target_locator,
            reference_type="cites",
            confidence=conf,
            source_method="rule_strong" if conf >= 0.85 else "rule_weak",
        )
