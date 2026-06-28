"""Tests for `minerva.tei` — XML parsing, chunking by section milestones,
speaker tracking, and language detection."""

from __future__ import annotations

from pathlib import Path

from minerva import tei

# ---------- _norm_text ----------


def test_norm_text_collapses_whitespace():
    assert tei._norm_text("  hello   world  ") == "hello world"


def test_norm_text_handles_newlines_and_tabs():
    assert tei._norm_text("hello\n\tworld\n  ") == "hello world"


def test_norm_text_empty_input():
    assert tei._norm_text("") == ""
    assert tei._norm_text("   ") == ""


# ---------- _make_chunk_id ----------


def test_make_chunk_id_is_deterministic():
    a = tei._make_chunk_id("foo.xml", "Republic", "eng", "6", "509d", "", "Conceive then")
    b = tei._make_chunk_id("foo.xml", "Republic", "eng", "6", "509d", "", "Conceive then")
    assert a == b


def test_make_chunk_id_changes_with_any_input():
    a = tei._make_chunk_id("foo.xml", "Republic", "eng", "6", "509d", "", "Conceive then")
    b = tei._make_chunk_id("foo.xml", "Republic", "eng", "6", "510a", "", "Conceive then")
    assert a != b


def test_make_chunk_id_is_short_hex():
    cid = tei._make_chunk_id("a", "b", "c", "d", "e", "f", "g")
    assert len(cid) == 20  # blake2b digest_size=10 → 20 hex chars
    assert all(c in "0123456789abcdef" for c in cid)


# ---------- parse_file: single-work TEI ----------

SAMPLE_REPUBLIC_XML = """<?xml version="1.0"?>
<TEI.2>
  <teiHeader>
    <fileDesc>
      <titleStmt><title>Republic. Machine readable text</title></titleStmt>
      <sourceDesc>
        <biblStruct><monogr>
          <title>Plato in Twelve Volumes</title>
          <imprint><date>1969</date></imprint>
        </monogr></biblStruct>
      </sourceDesc>
    </fileDesc>
  </teiHeader>
  <text>
    <body>
      <div1 type="book" n="6">
        <milestone unit="section" n="509c"/>
        At this point Glaucon laughed and said:
        <milestone unit="section" n="509d"/>
        Conceive then that there are these two entities, represented by a line divided
        into two unequal sections.
        <milestone unit="section" n="510a"/>
        The visible and the intelligible.
      </div1>
    </body>
  </text>
</TEI.2>
"""


def _write_xml(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


def test_parse_file_emits_one_chunk_per_section_milestone(tmp_path: Path):
    path = _write_xml(tmp_path, "republic_en.xml", SAMPLE_REPUBLIC_XML)
    chunks = list(tei.parse_file(path, corpus="plato", author="Plato"))
    assert len(chunks) == 3
    sections = [c.section for c in chunks]
    assert sections == ["509c", "509d", "510a"]


def test_parse_file_carries_book_metadata(tmp_path: Path):
    path = _write_xml(tmp_path, "republic_en.xml", SAMPLE_REPUBLIC_XML)
    chunks = list(tei.parse_file(path, corpus="plato", author="Plato"))
    assert all(c.book == "6" for c in chunks)


def test_parse_file_detects_language_from_stem(tmp_path: Path):
    en_path = _write_xml(tmp_path, "republic_en.xml", SAMPLE_REPUBLIC_XML)
    gr_path = _write_xml(tmp_path, "republic_gr.xml", SAMPLE_REPUBLIC_XML)
    en_chunks = list(tei.parse_file(en_path, corpus="plato", author="Plato"))
    gr_chunks = list(tei.parse_file(gr_path, corpus="plato", author="Plato"))
    assert all(c.lang == "eng" for c in en_chunks)
    assert all(c.lang == "grc" for c in gr_chunks)


def test_note_captured_as_separate_block(tmp_path: Path):
    # A <note> is no longer dropped: its text is captured as a separate
    # block_type='note' chunk, emitted AFTER the section's main chunk, while
    # the main body chunk still excludes the note text (no pollution).
    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt></fileDesc></teiHeader>
<text><body><div1 type="book" n="1">
<milestone unit="section" n="1a"/>
Real text here.
<note>The footnote text.</note>
More real text.
</div1></body></text></TEI.2>
"""
    path = _write_xml(tmp_path, "test_en.xml", xml)
    chunks = list(tei.parse_file(path, corpus="plato", author="Plato"))
    assert len(chunks) == 2
    body, note = chunks  # main first, note after
    assert body.block_type is None
    assert "footnote" not in body.text  # not polluted
    assert "Real text here." in body.text
    assert "More real text." in body.text
    assert note.block_type == "note"
    assert note.section == "1a"  # anchored to the same section
    assert note.text == "The footnote text."


def test_castlist_captured_as_cast_block(tmp_path: Path):
    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt></fileDesc></teiHeader>
<text><body><div1 type="book" n="1">
<castList><castItem>Socrates</castItem><castItem>Glaucon</castItem></castList>
<milestone unit="section" n="1a"/>
Real text here.
</div1></body></text></TEI.2>
"""
    path = _write_xml(tmp_path, "test_en.xml", xml)
    chunks = list(tei.parse_file(path, corpus="plato", author="Plato"))
    cast = [c for c in chunks if c.block_type == "cast"]
    assert len(cast) == 1
    assert "Socrates" in cast[0].text and "Glaucon" in cast[0].text
    # The cast text does not leak into any main body chunk.
    assert all("Socrates" not in c.text for c in chunks if c.block_type is None)


def test_speaker_preserved_across_sp_boundary(tmp_path: Path):
    # Each <sp> wraps one section milestone. The flush for section "1a"
    # is triggered by milestone "1b" — by which point _cur_speaker has
    # popped to None and re-pushed to Cephalus. The fix records each
    # text fragment alongside the speaker active when it was emitted, so
    # the chunk's speaker reflects who actually spoke that text.
    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt></fileDesc></teiHeader>
<text><body><div1 type="book" n="1">
<sp><speaker>Socrates</speaker>
  <milestone unit="section" n="1a"/>
  What is justice, Cephalus?
</sp>
<sp><speaker>Cephalus</speaker>
  <milestone unit="section" n="1b"/>
  Justice is paying back what one owes.
</sp>
</div1></body></text></TEI.2>
"""
    path = _write_xml(tmp_path, "test_en.xml", xml)
    chunks = list(tei.parse_file(path, corpus="plato", author="Plato"))
    by_section = {c.section: c.speaker for c in chunks}
    assert by_section["1a"] == "Socrates"
    assert by_section["1b"] == "Cephalus"


def test_speaker_preserved_across_sections_within_one_sp(tmp_path: Path):
    # One <sp> contains two section milestones — both chunks belong to
    # the same speaker. The second flush still fires inside the active
    # <sp>, so this case worked even pre-fix; assert it doesn't regress.
    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt></fileDesc></teiHeader>
<text><body><div1 type="book" n="1">
<sp><speaker>Socrates</speaker>
  <milestone unit="section" n="x1"/>
  First half of a long speech.
  <milestone unit="section" n="x2"/>
  Second half of the same speech.
</sp>
</div1></body></text></TEI.2>
"""
    path = _write_xml(tmp_path, "test_en.xml", xml)
    chunks = list(tei.parse_file(path, corpus="plato", author="Plato"))
    by_section = {c.section: c.speaker for c in chunks}
    assert by_section["x1"] == "Socrates"
    assert by_section["x2"] == "Socrates"


def test_speaker_preserved_at_end_of_body(tmp_path: Path):
    # The final flush at end-of-walk previously lost the speaker because
    # the <sp> had already popped. With per-fragment speaker capture, the
    # last chunk retains the active speaker.
    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt></fileDesc></teiHeader>
<text><body><div1 type="book" n="1">
<sp><speaker>Glaucon</speaker>
  <milestone unit="section" n="end"/>
  And so the dialogue closes.
</sp>
</div1></body></text></TEI.2>
"""
    path = _write_xml(tmp_path, "test_en.xml", xml)
    chunks = list(tei.parse_file(path, corpus="plato", author="Plato"))
    assert len(chunks) == 1
    assert chunks[0].speaker == "Glaucon"


def test_dominant_speaker_helper():
    # Pure-helper coverage: ignores leading whitespace fragments and
    # falls back to None when nothing speech-bearing is present.
    assert tei._dominant_speaker([]) is None
    assert tei._dominant_speaker([("  ", "Socrates"), ("real text", "Cephalus")]) == "Cephalus"
    assert tei._dominant_speaker([(" ", None), ("\n", None)]) is None
    assert tei._dominant_speaker([("a", "Socrates"), ("b", "Cephalus")]) == "Socrates"


def test_parse_dir_iterates_files_in_sorted_order(tmp_path: Path):
    _write_xml(tmp_path, "b_en.xml", SAMPLE_REPUBLIC_XML)
    _write_xml(tmp_path, "a_en.xml", SAMPLE_REPUBLIC_XML)
    chunks = list(tei.parse_dir(tmp_path, corpus="plato", author="Plato"))
    sources = [c.source_file for c in chunks]
    # All chunks from a_en should come before b_en's chunks.
    a_idx = sources.index("a_en.xml")
    b_idx = sources.index("b_en.xml")
    assert a_idx < b_idx


def test_parse_grouped_works(tmp_path: Path):
    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Bundle</title></titleStmt></fileDesc></teiHeader>
<text><group>
  <text n="Phaedo"><body>
    <head>Phaedo</head>
    <milestone unit="section" n="72e"/>
    Recollection: the soul recovers what it knew before.
  </body></text>
  <text n="Crito"><body>
    <head>Crito</head>
    <milestone unit="section" n="50a"/>
    The laws of Athens approach.
  </body></text>
</group></text></TEI.2>
"""
    path = _write_xml(tmp_path, "bundle_en.xml", xml)
    chunks = list(tei.parse_file(path, corpus="plato", author="Plato"))
    works = {c.work for c in chunks}
    assert works == {"Phaedo", "Crito"}
