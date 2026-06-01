"""Parser for the Lemaistre de Sacy (1696) French Catholic Bible.

Per-edition adapter over :mod:`minerva.osis_bible`. The gratis-bible
``fr/sacc.xml`` distribution is technically the 1759 "Bible de Saci"
— an 18th-c. revised edition of Sacy's original 1696 Port-Royal
translation. The chapter/verse numbering follows the Vulgate canon
(73 books incl. deuterocanon), so cross-corpus joins with Vulgate
land on the same verse.

Source: gratis-bible's ``fr/sacc.xml``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from . import osis_bible
from .tei import Chunk


def parse_dir(directory: Path) -> Iterator[Chunk]:
    """Yield Chunks for every Sacy verse under ``directory``."""

    yield from osis_bible.parse_dir(
        directory,
        corpus="sacy",
        author="Sacy",
        lang="fra",
        edition_year="1696",
        translator="Louis-Isaac Lemaistre de Sacy",
    )
