"""Quran-citation detection.

Fires on Quran cite-string syntax in chunk text. The result is a
:class:`Candidate` whose ``target_locator`` is the compact
``"<surah>:<ayah>"`` form (same shape Quran chunks carry in
``chunks.section``), so the chunk-binder in ``insert_candidate``
resolves ``target_chunk_id`` directly.

This rule is scaffolding for Phase E (Arabic-philosophy ingest). With
the Quran corpus indexed but no Arabic-philosophy source text yet,
the rule has no chunks to fire against today; the patterns + tests
are in place so adding Avicenna / Averroes / al-Ghazali lights up
cross-references automatically the moment their chunks land.

Recognized forms (Western academic + scholarly conventions):

* ``Q 2:255``                    — compact letter-prefix
* ``Q. 2:255``                   — with period
* ``Quran 2:255`` / ``Qur'an``   — full word, optional apostrophe
* ``Qurʾan 2:255``               — with ʾalif (ʿayn/hamza scholarly form)
* ``Surah 2:255`` / ``Sura``     — surah-prefix
* ``Al-Baqarah 2:255``           — transliterated surah name + ref
* ``Al-Baqarah 255``             — transliterated surah name + ayah only

Surah-name matching uses the transliterated titles in
``quran_works`` as the lexicon. The Arabic-script equivalents
(``البقرة 2:255``) are handled by a separate pass in the Arabic-prose
extension (Phase E ingest), kept out of this rule so the regex stays
auditable.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from ...authors.quran_works import SURAHS
from ..rules import Candidate, ChunkInfo

# Confidence tiers. Compact ``Q 2:255`` and ``Quran 2:255`` are
# unambiguous in any prose; bare-name forms like ``Al-Baqarah 255``
# rely on the transliteration lexicon and are slightly lower
# confidence because variant romanizations exist.
_CONF_STRONG = 0.92
_CONF_NAME_BASED = 0.80

# Quran title prefixes that unambiguously introduce a citation.
# Matched case-insensitively. The apostrophe character class is
# explicit because Qur'an / Qurʾan / Qur'an / Qur'an all appear in
# scholarly texts depending on the editor's transliteration scheme.
_TITLE_PREFIX_RE = re.compile(
    r"""
    \b (?:                              # word boundary
        Q                                # bare 'Q' (most compact)
        | Quran                          # plain English spelling
        | Qur [ ' ʾ ʿ ʼ ` ] an           # Qur'an / Qurʾan / Qur'an / etc.
        | Sura                           # academic 'Sura'
        | Surah                          # variant 'Surah'
    )
    \.?                                 # optional period after the word
    \s+
    (?P<surah> \d{1,3} )                # surah number 1..114
    \s* [:.] \s*                        # separator (colon or dot)
    (?P<ayah> \d{1,3} )                 # ayah number 0..286ish
    """,
    re.IGNORECASE | re.VERBOSE,
)


# Lexicon for surah-name + ayah forms. Built from the canonical
# transliteration table in quran_works. Case-insensitive matching is
# applied at scan time. The longest match wins so ``Al-Baqarah`` is
# preferred over ``Al-Baqara`` when both could fit a prefix.
def _build_surah_lexicon() -> dict[str, int]:
    """Map every recognized surah-name form (lowercased) to its
    canonical surah number. Includes the canonical transliteration
    plus a handful of common alternate spellings."""

    lex: dict[str, int] = {}
    for s in SURAHS:
        canonical = s.transliteration.lower()
        lex[canonical] = s.number
        # Also accept the hyphen-stripped form ("Al-Baqarah" → "Al Baqarah" /
        # "AlBaqarah") and the no-prefix form ("Al-Baqarah" → "Baqarah")
        # because scholarly prose varies.
        if "-" in canonical:
            lex[canonical.replace("-", " ")] = s.number
            lex[canonical.replace("-", "")] = s.number
            no_prefix = canonical.split("-", 1)[1]
            lex[no_prefix] = s.number
    return lex


_SURAH_LEXICON: dict[str, int] = _build_surah_lexicon()

# Pre-compile a regex that matches any known surah name followed by
# (optional ``surah:`` indicator) ayah number. Surah-names sorted
# longest-first so ``Al-Baqarah`` (10 chars) doesn't get truncated to
# ``Al-Baqara`` (9 chars) by a shorter alternate.
_SURAH_NAMES_PATTERN = "|".join(
    re.escape(name) for name in sorted(_SURAH_LEXICON.keys(), key=len, reverse=True)
)
_SURAH_NAME_REF_RE = re.compile(
    rf"""
    \b (?P<name> {_SURAH_NAMES_PATTERN} ) \b
    \s*
    (?:                                  # one of two locator shapes:
       (?P<surah> \d{{1,3}}) \s* [:.] \s* (?P<ayah_full> \d{{1,3}})
                                          # explicit surah:ayah after name
     | (?P<ayah_only> \d{{1,3}})          # bare ayah number after name
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _resolve_surah_work(surah_n: int) -> str | None:
    """Map a surah number 1..114 to its canonical work title (the
    transliteration we store as ``works.title`` for Quran rows).
    Returns ``None`` for out-of-range inputs."""

    for s in SURAHS:
        if s.number == surah_n:
            return s.transliteration
    return None


@dataclass(frozen=True)
class QuranCiteRule:
    """Fires on Quran cite-string syntax in chunk text.

    Each match becomes one :class:`Candidate` with ``target_locator``
    set to ``"<surah>:<ayah>"``. The runner's ``insert_candidate``
    then performs an exact-section lookup against Quran chunks and
    binds ``target_chunk_id`` when the verse exists.

    Default langs covers the languages Quran-citing prose typically
    appears in: English / French / German for Western philosophy,
    Arabic for Arabic-philosophy text. Latin scholastics rarely cite
    the Quran directly (they engage it indirectly via Averroes etc.),
    but the rule is permissive — narrow via ``langs`` per author if
    false-positive volume becomes an issue.
    """

    name: str = "quran_cite"
    target_corpus: str = "Quran"
    langs: tuple[str, ...] = ("eng", "fra", "deu", "ara", "lat")
    _key: str = field(init=False, default="")

    def __post_init__(self) -> None:
        object.__setattr__(self, "_key", f"quran_cite/{self.name}")

    def scan(self, chunk: ChunkInfo) -> Iterable[Candidate]:
        if self.langs and chunk.lang not in self.langs:
            return
        # Don't fire on Quran chunks themselves — Surah X quoting
        # Surah X isn't a useful cross-reference.
        if chunk.author == self.target_corpus:
            return

        seen_spans: set[tuple[int, int]] = set()

        # Pass 1: title-prefixed forms (``Q 2:255`` / ``Quran 2:255`` / …)
        for m in _TITLE_PREFIX_RE.finditer(chunk.text):
            try:
                surah_n = int(m.group("surah"))
                ayah_n = int(m.group("ayah"))
            except ValueError:
                continue
            if not (1 <= surah_n <= 114):
                continue
            work = _resolve_surah_work(surah_n)
            if work is None:
                continue
            seen_spans.add((m.start(), m.end()))
            yield Candidate(
                source_chunk_id=chunk.chunk_id,
                source_span_start=m.start(),
                source_span_end=m.end(),
                source_form_snapshot=m.group(0),
                target_author=self.target_corpus,
                target_work=work,
                target_locator=f"{surah_n}:{ayah_n}",
                reference_type="cites",
                confidence=_CONF_STRONG,
                source_method="rule_strong",
            )

        # Pass 2: name-based forms (``Al-Baqarah 255`` / ``Al-Baqarah 2:255``)
        for m in _SURAH_NAME_REF_RE.finditer(chunk.text):
            span = (m.start(), m.end())
            # Skip overlapping matches with Pass 1 (a ``Q 2:255``
            # adjacent to ``Quran`` could double-match; trust Pass 1).
            if any(
                seen[0] <= span[0] < seen[1] or span[0] <= seen[0] < span[1] for seen in seen_spans
            ):
                continue

            name_key = m.group("name").lower()
            surah_n = _SURAH_LEXICON.get(name_key)
            if surah_n is None:
                continue
            ayah_full = m.group("ayah_full")
            ayah_only = m.group("ayah_only")
            ayah_n_str = ayah_full or ayah_only
            if ayah_n_str is None:
                continue
            try:
                ayah_n = int(ayah_n_str)
            except ValueError:
                continue
            # If the prose also specified an explicit surah number,
            # require it to match the named surah. ``Al-Baqarah 3:5``
            # is contradictory (surah 2 named, surah 3 numbered) and
            # we'd rather drop the candidate than emit a wrong one.
            if ayah_full is not None:
                explicit_surah = m.group("surah")
                if explicit_surah and int(explicit_surah) != surah_n:
                    continue
            work = _resolve_surah_work(surah_n)
            if work is None:
                continue
            yield Candidate(
                source_chunk_id=chunk.chunk_id,
                source_span_start=m.start(),
                source_span_end=m.end(),
                source_form_snapshot=m.group(0),
                target_author=self.target_corpus,
                target_work=work,
                target_locator=f"{surah_n}:{ayah_n}",
                reference_type="cites",
                confidence=_CONF_NAME_BASED,
                source_method="rule_strong",
            )


# Public single-instance the runner imports. Per-author overrides
# (e.g., scoped to Avicenna only) can be created by callers via the
# dataclass keyword args; the bare singleton applies everywhere.
QURAN_CITE = QuranCiteRule()
