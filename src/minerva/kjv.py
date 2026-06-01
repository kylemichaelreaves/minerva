"""Parser for the King James Bible (1611), OSIS XML.

Per-edition adapter over :mod:`minerva.osis_bible`. KJV English with
archaic verb forms (thou / ye / thy) preserved verbatim in
``Chunk.text``; the storage layer aligns on canonical English SBL
book abbreviations so cross-corpus citation queries work across
Vulgate / Luther / KJV / Sacy.

Source: gratis-bible's ``en/kjv.xml``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from . import osis_bible
from .tei import Chunk


def parse_dir(directory: Path) -> Iterator[Chunk]:
    """Yield Chunks for every KJV verse under ``directory``."""

    yield from osis_bible.parse_dir(
        directory,
        corpus="kjv",
        author="King James Bible",
        lang="eng",
        edition_year="1611",
        translator="Various (KJV translators)",
    )
