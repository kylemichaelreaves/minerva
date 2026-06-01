"""Parser for the Luther Bibel 1912 (modernized German), OSIS XML.

Per-edition adapter over :mod:`minerva.osis_bible`. The OSIS schema
is identical across editions, so the shared parser handles every
Bible we ingest in OSIS format (Luther 1545 / 1912, KJV, Sacy).
This module supplies only the edition-specific knobs:
``corpus="luther_1912"``, ``author="Luther Bibel 1912"``,
``lang="deu"``, ``edition_year="1912"``.

Source: gratis-bible's ``de/luth1912.xml`` (or
``de/luth1912ap.xml`` for the Apocrypha-bearing variant).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from minerva.sources import osis_bible
from minerva.tei import Chunk


def parse_dir(directory: Path) -> Iterator[Chunk]:
    """Yield Chunks for every Luther 1912 verse under ``directory``."""

    yield from osis_bible.parse_dir(
        directory,
        corpus="luther_1912",
        author="Luther Bibel 1912",
        lang="deu",
        edition_year="1912",
        translator="Martin Luther",
    )
