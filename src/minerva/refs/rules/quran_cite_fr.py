"""French Roman-numeral Quran citations — the form Renan actually uses.

The Quran is fully ingested (6,236 ``ara`` chunks) and had zero incoming
cross-references. The rule that used to target it, ``QuranCiteRule``,
matched transliterated surah *names* with Arabic numerals
(``Al-Baqarah 255``); it fired on nothing, would have produced 217 false
positives if wired, and was removed in #53 / PR #224.

Renan writes the 19th-c French convention instead — the French book name,
then a Roman-numeral surah, then an Arabic-numeral ayah::

    Coran, sur. xv, 80
    Coran, xviir, 94 et suiv.; xxi, 96

This is a **precision** rule, not a recall gamble: it requires the book
name *and* a locator. Renan names the Quran 17 times without one, and
matching those bare mentions is exactly what #53 was closed for. Hegel's
index line ``Qur'an 162 247`` is page numbers, and is likewise out of
scope.

Shape notes, all derived from the three real sites rather than assumed:

* **Surah range.** 1–114. A numeral above that is a misparse.
* **OCR damage.** ``xviir`` is ``xviii``: ``r`` is not a Roman numeral,
  so a trailing one on an otherwise-valid numeral is unambiguously a
  misread final ``i``. The repair is confirmed by content here — surah
  18 (Al-Kahf) 83–98 is the Dhul-Qarnayn / Gog-and-Magog passage, and
  the citing sentence is about Gog and Magog personifying the Scythian
  invasion. The narrow repair lives here rather than in
  ``scripture_cite._parse_cite_num``, so it cannot affect Bible cites.
* **Citation runs.** ``…xviir, 94 et suiv.; xxi, 96`` is two citations
  under one ``Coran``. The continuation is consumed only when it is
  immediately adjacent (an optional ``et suiv.`` then ``;`` then another
  locator), so an unrelated ``;`` in the same footnote cannot be
  swallowed.
* **``Coran, v, i, 92`` is deliberately unmatched.** Three numbers read
  as volume/surah/verse, but the Quran has no volumes; it could be a
  damaged ``vi`` or a stray footnote marker. One citation corpus-wide,
  and guessing is the failure mode #53 records.

Target binding: ``target_locator`` is ``"<surah>:<ayah>"``, the shape
``sources/quran.py`` writes into ``chunks.section``, so the runner's
exact-section lookup binds ``target_chunk_id`` directly. ``target_work``
is the transliterated surah title, which is what ``works.title`` holds.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from ...authors.quran_works import find_surah
from . import Candidate, ChunkInfo

#: Book name as it appears in French sources. ``Alcoran`` is the older
#: spelling (Du Ryer 1647), included because the corpus reaches back that
#: far in other authors even though Renan does not use it.
_BOOK = r"(?:Coran|Alcoran)"

#: Optional "surah" marker: `sur.`, `sour.`, `surate`, `sourate`, `s.`
_SURAH_MARKER = r"(?:sur(?:ate)?\.?|sour(?:ate)?\.?|s\.)"

#: One `<surah>, <ayah>` pair. The surah may be Roman (either case,
#: possibly with an OCR'd trailing `r`) or Arabic; the ayah is always
#: Arabic in this convention.
_LOCATOR = r"(?P<surah>[ivxlcIVXLC]{1,7}r?|\d{1,3})\s*[,.:]\s*(?P<ayah>\d{1,3})"

#: Same, unnamed, for the continuation alternation.
_LOCATOR_BARE = r"(?:[ivxlcIVXLC]{1,7}r?|\d{1,3})\s*[,.:]\s*\d{1,3}"

#: `et suiv.` / `sq.` — the "and following" tail that sits between a
#: locator and the `;` introducing the next one.
_AND_FOLLOWING = r"(?:\s*et\s+suiv\.?|\s*sqq?\.?)?"

#: The whole citation run: book name, first locator, then any number of
#: `; <locator>` continuations. Matched as one span so the continuations
#: can only attach to a `Coran` that actually precedes them.
_RUN_RE = re.compile(
    rf"{_BOOK}\s*,?\s*(?:{_SURAH_MARKER}\s*,?\s*)?"
    rf"{_LOCATOR_BARE}{_AND_FOLLOWING}"
    rf"(?:\s*;\s*{_LOCATOR_BARE}{_AND_FOLLOWING})*"
)

#: Individual locators within a matched run.
_LOCATOR_RE = re.compile(_LOCATOR)

_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}

#: Surahs in the Mushaf.
_MAX_SURAH = 114
#: Al-Baqarah, the longest surah, has 286 ayat.
_MAX_AYAH = 286

_CONF_QURAN_CITE = 0.90


def _parse_numeral(raw: str) -> int | None:
    """Roman (either case) or Arabic numeral → int, or None.

    Accepts a trailing ``r`` on a Roman numeral as an OCR'd final ``i``
    — see the module docstring for why that is safe and how it was
    confirmed.
    """

    raw = raw.strip()
    if raw.isdigit():
        # `or None` so "0" is rejected here rather than relying on the
        # caller's range check — both branches return None for "no
        # usable number", which is what makes the caller's single
        # `is None` test sufficient.
        return int(raw) or None
    raw = raw.lower()
    if raw.endswith("r"):
        raw = raw[:-1] + "i"
    total = 0
    prev = 0
    for ch in reversed(raw):
        val = _ROMAN_VALUES.get(ch)
        if val is None:
            return None
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    return total or None


@dataclass(frozen=True)
class QuranCiteRuleFrRoman:
    """Fires on `Coran, <roman surah>, <arabic ayah>` in French text."""

    name: str = "quran_cite_fr_roman"
    target_author: str = "Quran"
    langs: tuple[str, ...] = ("fra",)

    def scan(self, chunk: ChunkInfo) -> Iterable[Candidate]:
        if self.langs and chunk.lang not in self.langs:
            return
        # The Quran quoting itself is not a cross-reference.
        if chunk.author == self.target_author:
            return

        for run in _RUN_RE.finditer(chunk.text):
            for index, m in enumerate(_LOCATOR_RE.finditer(run.group(0))):
                surah = _parse_numeral(m.group("surah"))
                ayah = _parse_numeral(m.group("ayah"))
                if surah is None or ayah is None:
                    continue
                if not 1 <= surah <= _MAX_SURAH or not 1 <= ayah <= _MAX_AYAH:
                    continue
                entry = find_surah(surah)
                if entry is None:  # pragma: no cover — guarded by the range check
                    continue

                # The first locator's span starts at the book name, so the
                # snapshot reads as a citation ("Coran, sur. xv, 80"). A
                # continuation has no book name of its own, so its span is
                # just the locator ("xxi, 96").
                start = run.start() if index == 0 else run.start() + m.start()
                end = run.start() + m.end()
                yield Candidate(
                    source_chunk_id=chunk.chunk_id,
                    source_span_start=start,
                    source_span_end=end,
                    source_form_snapshot=chunk.text[start:end],
                    target_author=self.target_author,
                    target_work=entry.transliteration,
                    target_locator=f"{surah}:{ayah}",
                    reference_type="cites",
                    confidence=_CONF_QURAN_CITE,
                    source_method="rule_strong",
                )


RULES = (QuranCiteRuleFrRoman(),)
