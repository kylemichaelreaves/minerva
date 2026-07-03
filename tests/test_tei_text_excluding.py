"""Tests for shared TEI text extraction and drama/P5 parser fixes."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from minerva import tei
from minerva.sources import tei_drama, tei_p5

_TEI = "http://www.tei-c.org/ns/1.0"
_SPEAKER = f"{{{_TEI}}}speaker"
_STAGE = f"{{{_TEI}}}stage"
_NOTE = f"{{{_TEI}}}note"
_L = f"{{{_TEI}}}l"
_P = f"{{{_TEI}}}p"


def test_text_excluding_skips_note_but_keeps_tail():
    el = ET.Element("p")
    el.text = "Before "
    note = ET.SubElement(el, "note")
    note.text = "apparatus"
    note.tail = " after"
    assert tei._norm_text(tei.text_excluding(el, frozenset({"note"}))) == "Before after"


def test_text_excluding_nested_skip_tags():
    el = ET.Element("div")
    el.text = "A "
    outer = ET.SubElement(el, "stage")
    outer.text = "[Exit]"
    inner = ET.SubElement(outer, "note")
    inner.text = "ignored"
    outer.tail = " B"
    assert tei._norm_text(tei.text_excluding(el, frozenset({"stage", "note"}))) == "A B"


def test_tei_drama_text_of_skips_speaker_and_stage_keeps_tail():
    sp = ET.Element(f"{{{_TEI}}}sp")
    speaker = ET.SubElement(sp, _SPEAKER)
    speaker.text = "Oedipus"
    line = ET.SubElement(sp, _L)
    line.text = "Hello world"
    stage = ET.SubElement(sp, _STAGE)
    stage.text = "[Enter messenger.]"
    stage.tail = " after stage"
    assert tei_drama._text_of(sp) == "Hello world after stage"


def test_tei_p5_text_of_excludes_note():
    para = ET.Element(_P)
    para.text = "Aristotle says "
    note = ET.SubElement(para, _NOTE)
    note.text = "variant reading"
    note.tail = " something true."
    assert tei_p5._text_of(para) == "Aristotle says something true."
