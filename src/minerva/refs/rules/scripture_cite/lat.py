"""Latin Vulgate scripture cite and formulaic-quote rules."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache

from .. import Candidate, ChunkInfo
from ._base import BaseScriptureCiteRule
from .lexicon import _AMBIGUOUS_BARE, _CITE_RE, _LEXICON


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
    # "ad Cor." / "ad Thess." / "ad Tim." mark an epistle but not the
    # number, so they stay ambiguous like the bare form (issue #52).
    non_disambiguating_prefixes = frozenset({"ad"})


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
                source_form_snapshot=m.group(0)[:120],
                target_author=self.target_author,
                target_work=self.target_work,
                target_locator=None,  # embed-verify Pass A binds chunk
                reference_type=self.reference_type,
                confidence=self.confidence,
                source_method=self.source_method,
                quoted_phrase=quote,
            )
