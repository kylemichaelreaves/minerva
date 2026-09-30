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


_MARKER_NOTES_XML = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt></fileDesc></teiHeader>
<text><body><div1 type="book" n="1">
<milestone unit="section" n="1a"/>
Sing, goddess, the wrath.<note resp="Loeb" anchored="yes">{marker}</note>
Real text.<note resp="Rackham" anchored="yes">2.7.2.</note>
<milestone unit="section" n="1b"/>
More text.<note>A real footnote.</note>
</div1></body></text></TEI.2>
"""


def _notes(tmp_path: Path, marker: str) -> list[tei.Chunk]:
    path = _write_xml(tmp_path, "test_en.xml", _MARKER_NOTES_XML.format(marker=marker))
    return [c for c in tei.parse_file(path, corpus="homer", author="Homer") if c.block_type]


def test_marker_only_note_is_not_emitted(tmp_path: Path):
    # Perseus's Loeb Homer keeps the footnote markers and none of the note
    # bodies, so a <note> reading "1" or "153.1" is not a note (#676).
    for marker in ("1", "153.1"):
        assert "2.7.2." in [c.text for c in _notes(tmp_path, marker)]
        assert marker not in [c.text for c in _notes(tmp_path, marker)]


def test_cross_reference_note_is_kept(tmp_path: Path):
    # Rackham's "We have already seen[2.7.2.]" is a citation, not a marker:
    # sentence-final period and all. Digits-and-dots alone would drop it.
    assert [c.text for c in _notes(tmp_path, "1")] == ["2.7.2.", "A real footnote."]


def test_skipped_marker_keeps_later_note_ids(tmp_path: Path):
    # The skipped marker still consumes its sequence number, so every note
    # after it keeps the chunk_id it had when the marker was emitted.
    with_marker = _notes(tmp_path, "1")
    with_prose = _notes(tmp_path, "a gloss")
    assert [c.chunk_id for c in with_marker] == [c.chunk_id for c in with_prose[1:]]


def test_work_title_excludes_note_gloss(tmp_path: Path):
    # A glossing <note> inside the <head> must not be swallowed into the work
    # title (regression: Plato's Epinomis / Epictetus' Fragments titles had a
    # paragraph-long gloss appended via head.itertext()).
    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Bundle</title></titleStmt></fileDesc></teiHeader>
<text><group>
  <text n="d1"><body><head>Epinomis<note>i.e. the Nocturnal Council, a long editorial gloss</note></head>
  <milestone unit="section" n="973a"/>Real dialogue text here that is long enough to chunk.</body></text>
</group></text></TEI.2>
"""
    path = _write_xml(tmp_path, "plato_en.xml", xml)
    chunks = list(tei.parse_file(path, corpus="plato", author="Plato"))
    assert chunks
    assert all(c.work == "Epinomis" for c in chunks)
    assert all("editorial gloss" not in c.work for c in chunks)


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
    # Plato titles are canonicalized to their Latinized-Greek names; the
    # anglicized English title rides along as the subordinate title_local.
    works = {c.work for c in chunks}
    assert works == {"Phaidon", "Kriton"}
    local = {c.work: c.title_local for c in chunks}
    assert local == {"Phaidon": "Phaedo", "Kriton": "Crito"}


# ── back matter is not a work (#177) ───────────────────────────────────


def test_back_matter_text_is_not_ingested_as_a_work(tmp_path: Path, capsys):
    """Perseus's English Epictetus ships its alphabetical index as a
    sibling ``<text n="index">`` after the real works. It became
    works.id=832 'Index.', one chunk of 8,495 characters of page-number
    apparatus — retrievable as though Epictetus wrote it, and a magnet
    for BM25 because it contains every topic term in the volume."""

    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Bundle</title></titleStmt></fileDesc></teiHeader>
<text><group>
  <text lang="en" n="enc"><body>
    <head>The Enchiridion</head>
    <milestone unit="section" n="1"/>
    Of things some are in our power and others are not.
  </body></text>
  <text lang="en" n="index"><body>
    <head>Index.</head>
    <milestone unit="section" n="1"/>
    Academics, deny the evidence of the senses, i. 193. Adultery reproved, i. 118.
  </body></text>
</group></text></TEI.2>
"""
    path = _write_xml(tmp_path, "discourses_en.xml", xml)
    chunks = list(tei.parse_file(path, corpus="epictetus", author="Epictetus"))
    assert {c.work for c in chunks} == {"The Enchiridion"}
    assert not any("Academics" in c.text for c in chunks)
    # Loud, not silent — the alternative is what happened here: apparatus
    # sitting in the corpus for months, found only by auditing titles.
    assert "skipping back matter" in capsys.readouterr().err


def test_back_matter_detected_by_head_when_n_is_absent(tmp_path: Path):
    """The ``n`` attribute is not always there; the head alone must do."""

    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Bundle</title></titleStmt></fileDesc></teiHeader>
<text><group>
  <text><body>
    <head>Meditations</head>
    <milestone unit="section" n="1"/>
    From my grandfather Verus I learned good morals.
  </body></text>
  <text><body>
    <head>General Index</head>
    <milestone unit="section" n="1"/>
    Antoninus, his character, i. 16. Apathy, not the Stoic doctrine, v. 20.
  </body></text>
</group></text></TEI.2>
"""
    path = _write_xml(tmp_path, "meditations_en.xml", xml)
    chunks = list(tei.parse_file(path, corpus="marcus_aurelius", author="Marcus Aurelius"))
    assert {c.work for c in chunks} == {"Meditations"}


def test_a_work_whose_title_merely_contains_index_is_kept(tmp_path: Path):
    """The match is on the whole normalized title, not a substring — a
    real work must not be dropped for having 'index' in its name."""

    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Bundle</title></titleStmt></fileDesc></teiHeader>
<text><group>
  <text n="w1"><body>
    <head>The Index Librorum Prohibitorum</head>
    <milestone unit="section" n="1"/>
    A real work that happens to be named for an index.
  </body></text>
</group></text></TEI.2>
"""
    path = _write_xml(tmp_path, "x_en.xml", xml)
    chunks = list(tei.parse_file(path, corpus="epictetus", author="Epictetus"))
    assert {c.work for c in chunks} == {"The Index Librorum Prohibitorum"}


# ── chapter fallback for milestone-less bodies (#176) ──────────────────

# Perseus's English Epictetus carries no `<milestone>` at all, so
# `_detect_chunk_boundary_units` returns an empty set and the body used to
# become one chunk per `<div1 type="book">` — 151,427 characters at the
# worst. The chapter divisions the source does carry are the fallback.

SAMPLE_DISCOURSES_XML = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Discourses</title></titleStmt></fileDesc></teiHeader>
<text><body>
  <head>The Discourses of Epictetus</head>
  <div1 type="book" n="1">
    <div2 type="chapter" n="1">
      <head>Of the things which are, and the things which are not, in our own power</head>
      <p>Of all the faculties, you will find none capable of contemplating itself.</p>
    </div2>
    <div2 type="chapter" n="2">
      <head>In what manner, upon every occasion, to preserve our character</head>
      <p>To a reasonable creature, that alone is insupportable which is unreasonable.</p>
    </div2>
  </div1>
  <div1 type="book" n="2">
    <div2 type="chapter" n="1">
      <head>That courage is not inconsistent with caution</head>
      <p>The opinion of the philosophers perhaps seems a paradox to some.</p>
    </div2>
  </div1>
</body></text></TEI.2>
"""


def test_a_body_with_no_milestones_chunks_at_chapter_divisions(tmp_path: Path):
    path = _write_xml(tmp_path, "discourses_en.xml", SAMPLE_DISCOURSES_XML)
    chunks = list(tei.parse_file(path, corpus="epictetus", author="Epictetus"))
    assert [(c.book, c.section) for c in chunks] == [("1", "1"), ("1", "2"), ("2", "1")]


def test_chapter_fallback_finds_chapters_at_div1(tmp_path: Path):
    """The Enchiridion's chapters are `<div1 type="chapter">` — there is no
    book level above them, so a fallback that only looked at `<div2>`
    would leave the whole work in one chunk."""

    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Enchiridion</title></titleStmt></fileDesc></teiHeader>
<text><body>
  <head>The Enchiridion</head>
  <div1 type="chapter" n="1"><p>Some things are in our power, and others are not.</p></div1>
  <div1 type="chapter" n="2"><p>Remember that desire demands the attainment of that of which you are desirous.</p></div1>
</body></text></TEI.2>
"""
    path = _write_xml(tmp_path, "enchiridion_en.xml", xml)
    chunks = list(tei.parse_file(path, corpus="epictetus", author="Epictetus"))
    assert [c.section for c in chunks] == ["1", "2"]


def test_every_chapter_survives_the_fallback(tmp_path: Path):
    """No text is lost or duplicated by the split."""

    path = _write_xml(tmp_path, "discourses_en.xml", SAMPLE_DISCOURSES_XML)
    joined = " ".join(c.text for c in tei.parse_file(path, corpus="epictetus", author="Epictetus"))
    for sentence in (
        "none capable of contemplating itself",
        "that alone is insupportable which is unreasonable",
        "seems a paradox to some",
    ):
        assert joined.count(sentence) == 1


def test_a_body_with_milestones_ignores_chapter_divisions(tmp_path: Path):
    """The churn guard. A body whose milestones fire keeps chunking on
    them, so no existing `chunk_id` in the five milestone-driven corpora
    moves — chapter divisions are a fallback, not a second boundary."""

    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Athenian Constitution</title></titleStmt></fileDesc></teiHeader>
<text><body>
  <div1 type="book" n="1">
    <div2 type="chapter" n="1">
      <milestone unit="section" n="1"/>
      They were tried by a court empanelled from among the noble families.
      <milestone unit="section" n="2"/>
      Epimenides purified the city.
    </div2>
  </div1>
</body></text></TEI.2>
"""
    path = _write_xml(tmp_path, "athenian_en.xml", xml)
    chunks = list(tei.parse_file(path, corpus="aristotle", author="Aristotle"))
    assert [c.section for c in chunks] == ["1", "2"]


def test_oversized_chapter_splits_at_paragraph_boundaries_with_letter_suffix(
    tmp_path: Path, monkeypatch
):
    """A chapter-fallback chunk over budget splits at `<p>` boundaries and
    gets a letter-suffixed locator (#394); a chapter that fits keeps its
    bare chapter number so its `chunk_id` doesn't move."""

    monkeypatch.setattr(tei, "_MAX_CHAPTER_CHUNK_CHARS", 15)
    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Discourses</title></titleStmt></fileDesc></teiHeader>
<text><body>
  <div1 type="book" n="4">
    <div2 type="chapter" n="1">
      <p>aaaaaaaaaa</p>
      <p>bbbbbbbbbb</p>
    </div2>
    <div2 type="chapter" n="2">
      <p>cccccccccc</p>
    </div2>
  </div1>
</body></text></TEI.2>
"""
    path = _write_xml(tmp_path, "discourses_en.xml", xml)
    chunks = list(tei.parse_file(path, corpus="epictetus", author="Epictetus"))
    assert [(c.book, c.section, c.text) for c in chunks] == [
        ("4", "1a", "aaaaaaaaaa"),
        ("4", "1b", "bbbbbbbbbb"),
        ("4", "2", "cccccccccc"),
    ]


def test_oversized_chapter_split_preserves_text_before_first_paragraph(tmp_path: Path, monkeypatch):
    """Text sitting directly in the division before its first `<p>` must not
    be silently dropped by the paragraph-boundary split."""

    monkeypatch.setattr(tei, "_MAX_CHAPTER_CHUNK_CHARS", 15)
    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Discourses</title></titleStmt></fileDesc></teiHeader>
<text><body>
  <div1 type="book" n="4">
    <div2 type="chapter" n="1">
      Loose lead-in text.
      <p>bbbbbbbbbb</p>
      <p>cccccccccc</p>
    </div2>
  </div1>
</body></text></TEI.2>
"""
    path = _write_xml(tmp_path, "discourses_en.xml", xml)
    joined = " ".join(c.text for c in tei.parse_file(path, corpus="epictetus", author="Epictetus"))
    assert "Loose lead-in text." in joined


def test_a_milestone_less_body_without_chapters_is_left_alone(tmp_path: Path):
    """A body with nothing to chunk on stays one chunk: the chapter
    fallback is not a licence to invent boundaries.

    This was written against the Greek *Fragmenta*, described here as
    having "neither milestones nor chapter divisions". The second half was
    right and the first was not — that body carries 111 milestones, and it
    now chunks on them (#395). What the case below pins is the general
    rule, with a body that genuinely has no markers."""

    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Fragmenta</title></titleStmt></fileDesc></teiHeader>
<text><body>
  <div1 type="book" n="0">
    <p>What is it to me whether all existing things are composed of atoms?</p>
    <p>He who is dissatisfied with what he has is unlearned.</p>
  </div1>
</body></text></TEI.2>
"""
    path = _write_xml(tmp_path, "fragmenta_gr.xml", xml)
    chunks = list(tei.parse_file(path, corpus="epictetus", author="Epictetus"))
    assert len(chunks) == 1
    assert chunks[0].section is None


# ---------- named-series milestones (#395) ----------

# Two `<div1 type="book">` with no `n`, each restarting `Sententia` at 1 —
# the shape of the Greek *Fragmenta*'s two Stobaeus gnomologia. Reused by
# the two tests below so the run-separation case and the label case read
# against the same body.
SAMPLE_FRAGMENTA_XML = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Fragmenta</title></titleStmt></fileDesc></teiHeader>
<text><body>
  <div1 type="book" n="0">
    <milestone unit="Fragment" n="1"/>
    What is it to me whether all existing things are composed of atoms?
    <milestone unit="Fragment" n="2"/>
    He who is dissatisfied with what he has is unlearned.
  </div1>
  <div1 type="book">
    <head>Gnomologium Epicteteum (e Stobaei libris 1-2)</head>
    <milestone unit="Sententia" n="1"/>
    All things obey and serve the cosmos.
  </div1>
  <div1 type="book">
    <head>Gnomologium Epicteteum (e Stobaei libris 3-4)</head>
    <milestone unit="Sententia" n="1"/>
    Freedom is the name of virtue, slavery of vice.
  </div1>
</body></text></TEI.2>
"""


def test_named_series_milestones_chunk_a_body_the_section_family_ignores(tmp_path: Path):
    """The *Fragmenta*'s 111 milestones all carry a `unit` — 36 `Fragment`
    and 75 `Sententia` — but neither is in the section/bekker/card
    allowlist, so the body read as milestone-less and stayed one
    25,244-char chunk. The series name and number are the citable locator
    (*Fr.* 1), so both come from the source rather than being invented."""

    path = _write_xml(tmp_path, "fragmenta_gr.xml", SAMPLE_FRAGMENTA_XML)
    chunks = list(tei.parse_file(path, corpus="epictetus", author="Epictetus"))
    assert [c.section for c in chunks] == [
        "Fragment 1",
        "Fragment 2",
        "Sententia 1",
        "Sententia 1",
    ]


def test_repeated_named_series_runs_are_separated_by_their_division_heads(tmp_path: Path):
    """Both gnomologia restart `Sententia` at 1 and neither `<div1>` carries
    an `n`, so `book` never moves off the first division's "0" and the two
    runs would cite identically. The divisions' own `<head>` is what tells
    them apart, so it becomes the book label when there is no number."""

    path = _write_xml(tmp_path, "fragmenta_gr.xml", SAMPLE_FRAGMENTA_XML)
    chunks = list(tei.parse_file(path, corpus="epictetus", author="Epictetus"))
    assert [c.book for c in chunks] == [
        "0",
        "0",
        "Gnomologium Epicteteum (e Stobaei libris 1-2)",
        "Gnomologium Epicteteum (e Stobaei libris 3-4)",
    ]
    assert len({(c.book, c.section) for c in chunks}) == len(chunks)


def test_a_section_chunked_body_ignores_stray_named_series_milestones(tmp_path: Path):
    """The churn guard, same as the one that keeps Aristotle Economics's 5
    stray cards from re-splitting a section-chunked work. A body that fires
    on `unit="section"` must not also fire on a named series, or every
    `chunk_id` in the milestone-driven corpora moves."""

    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Dissertationes</title></titleStmt></fileDesc></teiHeader>
<text><body>
  <div1 type="book" n="1">
    <milestone unit="section" n="1"/>
    Of things some are in our power, and others are not.
    <milestone unit="Fragment" n="9"/>
    <milestone unit="section" n="2"/>
    What then is to be done?
  </div1>
</body></text></TEI.2>
"""
    path = _write_xml(tmp_path, "dissertationes_gr.xml", xml)
    chunks = list(tei.parse_file(path, corpus="epictetus", author="Epictetus"))
    assert [c.section for c in chunks] == ["1", "2"]


def test_a_headless_division_does_not_blank_the_book_label(tmp_path: Path):
    """`<head>` stands in for a missing `n`, but only when there is one.
    A division with neither keeps whatever book label is in force rather
    than overwriting it with the empty string — an unlabelled chunk is
    worse than one inheriting its predecessor's division."""

    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Fragmenta</title></titleStmt></fileDesc></teiHeader>
<text><body>
  <div1 type="book" n="0">
    <milestone unit="Fragment" n="1"/>
    What is it to me whether all existing things are composed of atoms?
  </div1>
  <div1 type="book">
    <milestone unit="Fragment" n="2"/>
    He who is dissatisfied with what he has is unlearned.
  </div1>
</body></text></TEI.2>
"""
    path = _write_xml(tmp_path, "fragmenta_gr.xml", xml)
    chunks = list(tei.parse_file(path, corpus="epictetus", author="Epictetus"))
    assert [c.book for c in chunks] == ["0", "0"]


# ---------- unrecognized boundary units (#405) ----------


def test_a_body_whose_only_units_are_unrecognized_says_so(tmp_path: Path, capsys):
    """`_detect_chunk_boundary_units` returns an empty set both for a body
    with no milestones and for one whose milestones all carry a unit it
    does not know. Nothing distinguished the two, and #395 was filed on
    that ambiguity — its author read the empty return as "these
    milestones have no unit" when the *Fragmenta* had 111 with units."""

    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Unknown</title></titleStmt></fileDesc></teiHeader>
<text><body>
  <div1 type="book" n="1">
    <milestone unit="strophe" n="1"/>
    A body chunked on a unit this parser has never been taught.
    <milestone unit="strophe" n="2"/>
    Which is a different thing from a body with no milestones at all.
  </div1>
</body></text></TEI.2>
"""
    path = _write_xml(tmp_path, "unknown_gr.xml", xml)
    list(tei.parse_file(path, corpus="epictetus", author="Epictetus"))
    err = capsys.readouterr().out
    assert "strophe" in err
    assert "unknown_gr.xml" in err


def test_a_body_with_no_milestones_at_all_stays_quiet(tmp_path: Path, capsys):
    """The guard's whole value is that it fires only on the ambiguous
    case. Warning on every milestone-less body would bury it — three of
    Epictetus's English works are legitimately milestone-less."""

    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Quiet</title></titleStmt></fileDesc></teiHeader>
<text><body>
  <div1 type="chapter" n="1"><p>Some things are in our power, and others are not.</p></div1>
</body></text></TEI.2>
"""
    path = _write_xml(tmp_path, "quiet_en.xml", xml)
    list(tei.parse_file(path, corpus="epictetus", author="Epictetus"))
    assert "unrecognized" not in capsys.readouterr().out


def test_a_stray_unrecognized_unit_in_a_chunked_body_stays_quiet(tmp_path: Path, capsys):
    """The allowlist dropping a stray unit inside a body that chunks fine
    is the guard working, not a problem. Only a body left with NOTHING to
    chunk on is worth a line."""

    xml = """<?xml version="1.0"?>
<TEI.2><teiHeader><fileDesc><titleStmt><title>Mixed</title></titleStmt></fileDesc></teiHeader>
<text><body>
  <div1 type="book" n="1">
    <milestone unit="section" n="1"/>
    Of things some are in our power, and others are not.
    <milestone unit="strophe" n="9"/>
    <milestone unit="section" n="2"/>
    What then is to be done?
  </div1>
</body></text></TEI.2>
"""
    path = _write_xml(tmp_path, "mixed_gr.xml", xml)
    list(tei.parse_file(path, corpus="epictetus", author="Epictetus"))
    assert "unrecognized" not in capsys.readouterr().out
