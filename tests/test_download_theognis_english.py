"""Tests for the Banks-1856 English extraction reproducibility gap (#448).

Running `_extract_english` fresh against the archive.org djvu text
regressed a 2026-06-06 manual trim: it silently reintroduced two blocks
of non-Theognis pollution the trim had removed, together 99.6% of the
gap between a fresh extraction (520,209 chars) and the curated,
currently-ingested file (238,016 chars, 1,492 chunks) —

1. A misplaced ~43,400-word appendix — Elton's *Remains of Hesiod*
   verse translation — sitting between the Theognis biographical
   section and the actual "FRAGMENTS OF THEOGNIS" elegies. It passes
   every existing filter (real English prose, not a footnote, not
   Greek-heavy, not a page header), so nothing catches it.
2. ~5,400 words of publisher's catalog after "THE END." — none of the
   existing end markers ("INDEX TO", "FINIS.", "PRINTED BY", "BOHN'S
   CLASSICAL") appear before that junk in this volume.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PERSEUS = Path(__file__).resolve().parents[1] / "perseus"


@pytest.fixture(autouse=True)
def _perseus_on_path():
    sys.path.insert(0, str(PERSEUS))
    yield
    sys.path.remove(str(PERSEUS))


def _extract_english(raw: str) -> str:
    import download_theognis

    return download_theognis._extract_english(raw)


# Structurally faithful to the real volume's ordering: biography ->
# misplaced Hesiod-verse appendix -> the actual Fragments, each poem
# numbered and header-page-numbered the way Banks's OCR really is ->
# "THE END." -> publisher's catalog.
_SAMPLE_RAW = """SOME EARLIER HESIOD/CALLIMACHUS MATERIAL NOT THEOGNIS AT ALL.

THEOGNIS THE MEGAREAN.

THE PERSONAL HISTORY OF THE POET.

Theognis was a citizen of Megara who lived in the sixth century
before our era, and whose poems are a rich mine of ethical maxims.

REMAINS OF HESIOD, TRANSLATED FROM THE GREEK INTO ENGLISH VERSE,
CHARLES ABRAHAM ELTON.

Ascraean Hesiod sung of fruitful toil,
And how the seasons turn the patient soil,
across many further stanzas of verse that belong to a wholly
different translator and a wholly different poet, none of which is
about Theognis at all, running on for a long while in this fixture
just as it runs to tens of thousands of words in the real volume.

FRAGMENTS OF THEOGNIS,

TRANSLATED OR PARAPHRASED,

CHRONOLOGICALLY ARRANGED.

I. The gods, Cyrnus, have not revealed all things to men from the
beginning, but by seeking, men in time find out that which is better.

II. Wine is wont to reveal the mind of a man, however close and
secret he may keep it.

THE END.

JUNIUS'S LETTERS, with Notes, Additions, Essay, Index, &c. 2 Vols.
Complete in 5 Vols., with Index.
"""


class TestExtractEnglish:
    def test_biography_and_fragments_are_kept(self):
        text = _extract_english(_SAMPLE_RAW)
        assert "citizen of Megara" in text
        assert "revealed all things to men" in text
        assert "reveal the mind of a man" in text

    def test_pre_megarean_material_is_excluded(self):
        text = _extract_english(_SAMPLE_RAW)
        assert "EARLIER HESIOD" not in text

    def test_misplaced_hesiod_appendix_is_excluded(self):
        text = _extract_english(_SAMPLE_RAW)
        assert "ELTON" not in text
        assert "Ascraean Hesiod" not in text
        assert "wholly\ndifferent translator" not in text

    def test_fragments_header_after_the_appendix_is_kept(self):
        text = _extract_english(_SAMPLE_RAW)
        assert "FRAGMENTS OF THEOGNIS" in text

    def test_publisher_catalog_after_the_end_is_excluded(self):
        text = _extract_english(_SAMPLE_RAW)
        assert "JUNIUS" not in text
        assert "5 Vols" not in text
