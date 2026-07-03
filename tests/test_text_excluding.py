"""Tests for the shared ``minerva.tei.text_excluding`` extractor."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from minerva import tei
from minerva.sources import tei_drama, tei_p5

_TEI_NS = "http://www.tei-c.org/ns/1.0"
_NOTE = f"{{{_TEI_NS}}}note"
_SPEAKER = f"{{{_TEI_NS}}}speaker"
_STAGE = f"{{{_TEI_NS}}}stage"
_L = f"{{{_TEI_NS}}}l"
_P = f"{{{_TEI_NS}}}p"


def _parse(xml: str) -> ET.Element:
    return ET.fromstring(xml)


def test_text_excluding_skips_note_subtree_but_keeps_tail():
    el = _parse(
        '<div>Before <note>apparatus</note> after</div>'
    )
    assert tei._norm_text(tei.text_excluding(el, frozenset({"note"}))) == "Before after"


def test_text_excluding_nested_skip_tags():
    el = _parse(
        "<div>one <note>skip <hi>nested</hi></note> two</div>"
    )
    assert tei._norm_text(tei.text_excluding(el, frozenset({"note"}))) == "one two"


def test_tei_p5_excludes_namespaced_notes():
    el = _parse(
        f'<p xmlns="{_TEI_NS}">Aristotle says <note>variant</note> something</p>'
    )
    assert tei_p5._text_of(el) == "Aristotle says something"


def test_tei_drama_excludes_speaker_and_stage():
    el = _parse(
        f'<sp xmlns="{_TEI_NS}">'
        f"<speaker>Oedipus</speaker>"
        f'<l>τίς ἀνὴρ;</l>'
        f"</sp>"
    )
    line = el.find(_L)
    assert line is not None
    assert tei_drama._text_of(line) == "τίς ἀνὴρ;"


def test_tei_drama_inline_stage_preserves_following_prose():
    """Regression: ``elem.iter()`` skipped ``<stage>`` but still walked
    its descendants and dropped the stage node's ``tail`` — prose after
    an inline direction vanished and stage names leaked into line text."""

    el = _parse(
        f'<l xmlns="{_TEI_NS}">'
        f"Line start "
        f"<stage>[Enter messenger.]</stage>"
        f" continues here"
        f"</l>"
    )
    assert tei_drama._text_of(el) == "Line start continues here"
    assert "Enter" not in tei_drama._text_of(el)
    assert "messenger" not in tei_drama._text_of(el)
