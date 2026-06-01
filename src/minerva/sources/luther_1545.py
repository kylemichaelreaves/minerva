"""Parser for the Luther Bibel 1545 Letzte-Hand, OSIS XML.

Per-edition adapter over :mod:`minerva.osis_bible`. The 1545 edition
preserves Frühneuhochdeutsch orthography (Tewfel, langes-ſ, archaic
-nis endings) — preserved verbatim in ``Chunk.text`` for textual-
history fidelity. Storage layer is unaffected: ``section`` is the
canonical SBL abbr form ("Rom 8:15") so cross-corpus joins land the
same verse across all biblical corpora regardless of source-language
orthography.

Source: gratis-bible's ``de/luth1545.xml``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from minerva.sources import osis_bible
from minerva.tei import Chunk


def parse_dir(directory: Path) -> Iterator[Chunk]:
    """Yield Chunks for every Luther 1545 verse under ``directory``."""

    yield from osis_bible.parse_dir(
        directory,
        corpus="luther_1545",
        author="Luther Bibel 1545",
        lang="deu",
        edition_year="1545",
        translator="Martin Luther",
    )
