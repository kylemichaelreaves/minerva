"""Tests for the Quran ingest path.

Covers:
* the Tanzil XML parser (``quran.parse_file``) — Al-Fatihah 1:1
  round-trips from a hand-written fixture into the expected
  ``Chunk`` shape
* NFC normalisation
* the works module's lookups + 114-surah coverage
* canonical Mushaf-order ordinals are consecutive (1..114)
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from minerva import quran
from minerva.authors import quran_works

# Tanzil-shape fixture: minimal valid XML with the same structure as
# ``quran-uthmani.xml`` (root <quran>, then <sura index name> with
# <aya index text> children). Verbatim text from Tanzil for Q 1:1–2.
_FATIHA_FIXTURE = """<?xml version="1.0" encoding="utf-8"?>
<quran>
  <sura index="1" name="الفاتحة">
    <aya index="1" text="بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ" />
    <aya index="2" text="ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَٰلَمِينَ" />
  </sura>
</quran>
"""


def test_parse_file_yields_one_chunk_per_ayah(tmp_path: Path) -> None:
    src = tmp_path / "quran-uthmani.xml"
    src.write_text(_FATIHA_FIXTURE, encoding="utf-8")
    chunks = list(quran.parse_file(src))
    assert len(chunks) == 2
    assert [c.section for c in chunks] == ["1:1", "1:2"]
    for c in chunks:
        assert c.lang == "ara"
        assert c.corpus == "quran"
        assert c.author == "Quran"
        assert c.work == "Al-Fatihah"
        assert c.book == "Al-Fatihah"
        assert c.citation_system == "surah_ayah"
    # Tashkeel preserved verbatim.
    assert "بِسْمِ" in chunks[0].text
    assert chunks[0].text.startswith("بِسْمِ")


def test_text_is_nfc_normalised(tmp_path: Path) -> None:
    src = tmp_path / "quran-uthmani.xml"
    src.write_text(_FATIHA_FIXTURE, encoding="utf-8")
    chunks = list(quran.parse_file(src))
    for c in chunks:
        assert unicodedata.is_normalized("NFC", c.text)


def test_find_surah_known_and_unknown() -> None:
    s = quran_works.find_surah(1)
    assert s is not None
    assert s.transliteration == "Al-Fatihah"
    assert s.english == "The Opening"
    assert s.revelation == "meccan"
    assert quran_works.find_surah(0) is None
    assert quran_works.find_surah(115) is None


def test_find_surah_by_transliteration_round_trip() -> None:
    s = quran_works.find_surah_by_transliteration("Al-Baqarah")
    assert s is not None
    assert s.number == 2
    assert s.revelation == "medinan"


def test_all_114_surahs_present() -> None:
    assert len(quran_works.SURAHS) == 114
    # Numbers are 1..114 inclusive with no gaps or duplicates.
    numbers = [s.number for s in quran_works.SURAHS]
    assert numbers == list(range(1, 115))


def test_all_surahs_have_arabic_and_transliteration() -> None:
    for s in quran_works.SURAHS:
        assert s.arabic, f"surah {s.number} missing arabic name"
        assert s.transliteration, f"surah {s.number} missing transliteration"
        assert s.english, f"surah {s.number} missing english gloss"
        assert s.revelation in ("meccan", "medinan"), (
            f"surah {s.number} has invalid revelation tag {s.revelation!r}"
        )


def test_meccan_vs_medinan_counts() -> None:
    """Conventional Sunni count: 86 Meccan + 28 Medinan (or 85+29
    depending on source). Either is acceptable; assert the partition
    sums to 114 and both buckets are non-empty."""
    meccan = sum(1 for s in quran_works.SURAHS if s.revelation == "meccan")
    medinan = sum(1 for s in quran_works.SURAHS if s.revelation == "medinan")
    assert meccan + medinan == 114
    assert 80 <= meccan <= 90
    assert 24 <= medinan <= 34


@pytest.mark.parametrize(
    "number,transliteration,english",
    [
        (1,   "Al-Fatihah",  "The Opening"),
        (2,   "Al-Baqarah",  "The Cow"),
        (36,  "Ya-Sin",      "Ya-Sin"),
        (112, "Al-Ikhlas",   "The Sincerity"),
        (114, "An-Nas",      "Mankind"),
    ],
)
def test_landmark_surahs(number: int, transliteration: str, english: str) -> None:
    s = quran_works.find_surah(number)
    assert s is not None
    assert s.transliteration == transliteration
    assert s.english == english
