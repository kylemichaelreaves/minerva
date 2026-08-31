"""Tests for the Hebrew Masoretic Text ingest path.

Covers:
* the OSIS parser (``hebrew_mt.parse_file``) — Gen 1:1 round-trips
  from a hand-written fixture into the expected ``Chunk`` shape
* morpheme-separator stripping and NFC normalisation
* the works module's filename/osisID lookups
* Tanakh canonical ordering for the sidebar
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from minerva.authors import hebrew_mt_works
from minerva.locations import (
    BCV_BOOK_ORDINAL,
    TANAKH_BOOK_ORDINAL,
)
from minerva.sources import hebrew_mt

# OSIS XML fragment matching the OSHB shape for Gen 1:1 — preserved
# verbatim from the upstream master to lock the parser against the
# real source format.
_GEN_1_1_OSIS = """<?xml version="1.0" encoding="UTF-8"?>
<osis xmlns="http://www.bibletechnologies.net/2003/OSIS/namespace">
  <osisText xml:lang="he" osisIDWork="OSHB" osisRefWork="Bible">
    <div type="book" osisID="Gen">
      <chapter osisID="Gen.1">
        <verse osisID="Gen.1.1">
          <w lemma="b/7225" morph="HR/Ncfsa" id="01xeN">בְּ/רֵאשִׁ֖ית</w>
          <w lemma="1254 a" morph="HVqp3ms" id="01Nvk">בָּרָ֣א</w>
          <w lemma="430" morph="HNcmpa" id="01TyA">אֱלֹהִ֑ים</w>
          <w lemma="853" morph="HTo" id="01vuQ">אֵ֥ת</w>
          <w lemma="d/8064" morph="HTd/Ncmpa" id="01TSc">הַ/שָּׁמַ֖יִם</w>
          <w lemma="c/853" morph="HC/To" id="01k5P">וְ/אֵ֥ת</w>
          <w lemma="d/776" morph="HTd/Ncbsa" id="01nPh">הָ/אָֽרֶץ</w><seg type="x-sof-pasuq">׃</seg>
        </verse>
      </chapter>
    </div>
  </osisText>
</osis>
"""


def test_parse_file_extracts_verse_text(tmp_path: Path) -> None:
    src = tmp_path / "Gen.xml"
    src.write_text(_GEN_1_1_OSIS, encoding="utf-8")
    chunks = list(hebrew_mt.parse_file(src))
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.lang == "heb"
    assert chunk.corpus == "hebrew_mt"
    assert chunk.author == "Hebrew Bible"
    assert chunk.work == "Genesis"
    assert chunk.book == "Genesis"
    assert chunk.section == "Gen 1:1"
    assert chunk.citation_system == "bcv"
    # The text round-trips with cantillation + niqqud, no morpheme
    # slashes, sof pasuq mark preserved.
    assert "/" not in chunk.text
    assert chunk.text.endswith("׃")  # sof pasuq
    assert "בְּרֵאשִׁ֖ית" in chunk.text  # morphemes joined
    assert "אֱלֹהִ֑ים" in chunk.text


# Real WLC/OSHB shape: transcription-apparatus <note> mid-verse, with
# English editorial prose and nested variant machinery (<rdg>,
# <catchWord>). Before the 2026-07 fix, itertext() spliced the English
# sentence into the Hebrew verse text (735 verses affected).
_GEN_WITH_NOTE_OSIS = """<?xml version="1.0" encoding="UTF-8"?>
<osis xmlns="http://www.bibletechnologies.net/2003/OSIS/namespace">
  <osisText xml:lang="he" osisIDWork="OSHB" osisRefWork="Bible">
    <div type="book" osisID="Gen">
      <chapter osisID="Gen.1">
        <verse osisID="Gen.1.12">
          <w lemma="c/3318" morph="HC/Vhw3fs" id="01TXw">וַ/תּוֹצֵ֨א</w>
          <note n="c">We read one or more accents in L differently than BHS.
            <rdg><catchWord>וַתּוֹצֵ֨א</catchWord></rdg>
          </note>
          <w lemma="d/776" morph="HTd/Ncbsa" id="01Y4K">הָ/אָ֜רֶץ</w><seg type="x-sof-pasuq">׃</seg>
        </verse>
      </chapter>
    </div>
  </osisText>
</osis>
"""


def test_note_apparatus_excluded_from_verse_text(tmp_path: Path) -> None:
    src = tmp_path / "Gen.xml"
    src.write_text(_GEN_WITH_NOTE_OSIS, encoding="utf-8")
    chunks = list(hebrew_mt.parse_file(src))
    assert len(chunks) == 1
    text = chunks[0].text
    # The editorial prose (and the variant reading nested in the note)
    # must not leak; the verse is pure Hebrew.
    assert "BHS" not in text
    assert not any("a" <= ch.lower() <= "z" for ch in text)
    assert text == "וַתּוֹצֵ֨א הָאָ֜רֶץ ׃"


def test_text_is_nfc_normalised(tmp_path: Path) -> None:
    src = tmp_path / "Gen.xml"
    src.write_text(_GEN_1_1_OSIS, encoding="utf-8")
    chunk = next(iter(hebrew_mt.parse_file(src)))
    assert unicodedata.is_normalized("NFC", chunk.text)


def test_unknown_filename_yields_nothing(tmp_path: Path) -> None:
    # VerseMap.xml is metadata in the OSHB repo, not a book. Parser
    # silently skips files that don't resolve through ``find_book``.
    src = tmp_path / "VerseMap.xml"
    src.write_text(_GEN_1_1_OSIS, encoding="utf-8")
    chunks = list(hebrew_mt.parse_file(src))
    assert chunks == []


def test_find_book_known_and_unknown() -> None:
    book = hebrew_mt_works.find_book("Gen.xml")
    assert book is not None
    assert book.english == "Genesis"
    assert book.osis_id == "Gen"
    assert book.section == "torah"
    assert hebrew_mt_works.find_book("Nope.xml") is None


def test_all_books_have_bcv_alignment() -> None:
    # Every Hebrew MT book name must resolve in BCV_BOOK_ORDINAL —
    # that's the cross-corpus alignment contract that makes the
    # LXX ↔ MT ↔ Vulgate joins on `chunks.section` work.
    missing = [b.english for b in hebrew_mt_works.BOOKS if b.english not in BCV_BOOK_ORDINAL]
    assert missing == [], (
        f"hebrew_mt_works references books absent from BCV_BOOK_ORDINAL: "
        f"{missing} (add to locations._BCV_BOOKS before ingesting)"
    )


def test_tanakh_ordinal_covers_all_mt_books() -> None:
    # Sidebar order needs an ordinal for every MT book; verify
    # coverage so a future book add doesn't end up in the "9999"
    # fallback bucket and visually re-sort the sidebar mid-author.
    missing = [b.english for b in hebrew_mt_works.BOOKS if b.english not in TANAKH_BOOK_ORDINAL]
    assert missing == [], f"hebrew_mt books absent from TANAKH_BOOK_ORDINAL: {missing}"


def test_tanakh_order_torah_first() -> None:
    # The Tanakh table puts Torah before Nevi'im before Ketuvim.
    # Spot-check the boundaries — Genesis < Joshua < Psalms.
    assert (
        TANAKH_BOOK_ORDINAL["Genesis"]
        < TANAKH_BOOK_ORDINAL["Joshua"]
        < TANAKH_BOOK_ORDINAL["Psalms"]
        < TANAKH_BOOK_ORDINAL["2 Chronicles"]
    )
    # And it differs from BCV order: Psalms sits AFTER Malachi in
    # Tanakh, but BEFORE Isaiah in the Christian BCV sequence.
    assert TANAKH_BOOK_ORDINAL["Psalms"] > TANAKH_BOOK_ORDINAL["Malachi"]
    assert BCV_BOOK_ORDINAL["Psalms"] < BCV_BOOK_ORDINAL["Malachi"]


def test_books_count_is_39() -> None:
    assert len(hebrew_mt_works.BOOKS) == 39


@pytest.mark.parametrize(
    "section_token,book_id",
    [
        ("torah", "Gen"),
        ("torah", "Deut"),
        ("neviim", "Josh"),
        ("neviim", "Mal"),
        ("ketuvim", "Ps"),
        ("ketuvim", "2Chr"),
    ],
)
def test_section_assignment(section_token: str, book_id: str) -> None:
    book = hebrew_mt_works.find_book_by_osis_id(book_id)
    assert book is not None
    assert book.section == section_token
