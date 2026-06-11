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

    def scan(self, chunk: ChunkInfo) -> Iterable[Candidate]:
        if self.langs and chunk.lang not in self.langs:
            return
        # Don't fire on the target Bible's own chunks — Genesis
        # quoting Genesis isn't a useful cross-reference.
        if chunk.author == self.target_author:
            return

        for m in self.cite_re.finditer(chunk.text):
            prefix = m.group("prefix")
            abbr = m.group("abbr")
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

            chap = int(m.group("chap"))
            verse_raw = m.group("verse")

            if verse_raw:
                target_locator = f"{sbl} {chap}:{int(verse_raw)}"
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

            if prefix is None and abbr in self.ambiguous_bare:
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
