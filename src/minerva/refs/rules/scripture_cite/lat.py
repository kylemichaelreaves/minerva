"""Latin Vulgate scripture cite and formulaic-quote rules."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from .. import _PATTERN_CACHE, Candidate, ChunkInfo
from .lexicon import (
    _AMBIGUOUS_BARE,
    _CITE_RE,
    _CONF_AMBIGUOUS,
    _CONF_CHAPTER_ONLY,
    _CONF_FULL,
    _LEXICON,
    _sbl_abbr_for,
)


class ScriptureCiteRule:
    """Fires on Latin Vulgate cite-string syntax in chunk text.

    Each match becomes one :class:`Candidate` with
    ``target_locator`` set to ``"<SBL-abbr> <chap>:<verse>"``. The
    runner's ``insert_candidate`` then performs an exact-section
    lookup against Vulgate chunks and binds ``target_chunk_id``
    directly when a verse is matched.
    """

    name: str = "scripture_cite_vulgate"
    target_corpus: str = "Vulgate"
    langs: tuple[str, ...] = ("lat",)
    # No suffix mods today; field is reserved for future
    # source-author overrides without breaking subclasses.
    _key: str = field(init=False, default="")

    def __post_init__(self) -> None:
        object.__setattr__(self, "_key", f"scripture_cite/{self.name}")

    def scan(self, chunk: ChunkInfo) -> Iterable[Candidate]:
        if self.langs and chunk.lang not in self.langs:
            return
        # Don't fire on Vulgate chunks themselves — Genesis quoting
        # Genesis isn't a useful cross-reference.
        if chunk.author == self.target_corpus:
            return

        for m in _CITE_RE.finditer(chunk.text):
            prefix = m.group("prefix")
            abbr = m.group("abbr")
            book = _LEXICON.get((prefix, abbr))
            if book is None:
                continue
            sbl = _sbl_abbr_for(book)
            if sbl is None:
                # Lexicon out of sync with the BCV table. Logged
                # silently rather than raised — the rules pass
                # processes thousands of chunks and one missing
                # entry shouldn't kill the batch.
                continue

            chap = int(m.group("chap"))
            verse_raw = m.group("verse")
            verse: int | None = int(verse_raw) if verse_raw else None

            if verse is not None:
                target_locator = f"{sbl} {chap}:{verse}"
                conf = _CONF_FULL
            else:
                # Chapter-level locator: no chunks.section will match
                # exactly (Vulgate sections are per-verse), so the
                # chunk binder will leave target_chunk_id NULL. The
                # row still useful for "Aquinas cites Matthew 5 (no
                # specific verse)" curation.
                target_locator = f"{sbl} {chap}"
                conf = _CONF_CHAPTER_ONLY

            if prefix is None and abbr in _AMBIGUOUS_BARE:
                conf = _CONF_AMBIGUOUS

            yield Candidate(
                source_chunk_id=chunk.chunk_id,
                source_span_start=m.start(),
                source_span_end=m.end(),
                source_form_snapshot=m.group(0),
                target_author=self.target_corpus,
                target_work=book,
                target_locator=target_locator,
                reference_type="cites",
                confidence=conf,
                source_method="rule_strong" if conf >= 0.85 else "rule_weak",
            )


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
# leaves chunk-binding to embed-verify Pass A, which compares the
# quoted text's embedding against every Vulgate Psalm chunk and pins
# the best cosine match.

_FORMULAIC_QUOTE_END_RE = r"[.;?!]"  # Latin sentences end at . ; ? or !
_FORMULAIC_MIN_QUOTE_CHARS = 15  # below this is noise (false intros)
_FORMULAIC_MAX_QUOTE_CHARS = 250  # above this likely overran the verse


@dataclass(frozen=True)
class FormulaicQuoteRule:
    """Fires on ``<introducer>: <verse text>.`` patterns.

    The rule emits a :class:`Candidate` whose ``target_work`` is
    known (Psalms, Romans, etc.) but ``target_locator`` is left
    NULL — embed-verify Pass A handles chunk binding by cosine
    similarity against the target work's verse embeddings.

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
    _key: str = field(init=False, default="")

    def __post_init__(self) -> None:
        object.__setattr__(self, "_key", f"formulaic_quote/{self.name}")

    def _pattern(self) -> re.Pattern[str]:
        cached = _PATTERN_CACHE.get(self._key)
        if cached is not None:
            return cached
        alt = "|".join(f"(?:{p})" for p in self.introducer_patterns)
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
        compiled = re.compile(body, re.IGNORECASE)
        _PATTERN_CACHE[self._key] = compiled
        return compiled

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
                source_form_snapshot=m.group(0)[:120],
                target_author=self.target_author,
                target_work=self.target_work,
                target_locator=None,  # embed-verify Pass A binds chunk
                reference_type=self.reference_type,
                confidence=self.confidence,
                source_method=self.source_method,
                quoted_phrase=quote,
            )
