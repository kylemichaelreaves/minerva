"""Hardened XML parsing for corpus sources (#127)."""

from __future__ import annotations

import pytest

from minerva.xml_safe import UnsafeXMLError, parse

# The classic internal-entity expansion. `xml.etree` is safe against
# *external* entities but still expands these, so the parse never gets
# to run — the DOCTYPE is refused first.
BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
]>
<TEI><text>&lol2;</text></TEI>
"""

PLAIN_TEI = """<?xml version="1.0" encoding="UTF-8"?>
<!-- a comment in the prolog must not confuse the scan -->
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text><body><p>Ἐν ἀρχῇ ἦν ὁ λόγος</p></body></text>
</TEI>
"""


def test_rejects_entity_expansion_document(tmp_path):
    p = tmp_path / "lol.xml"
    p.write_text(BILLION_LAUGHS, encoding="utf-8")
    with pytest.raises(UnsafeXMLError) as exc:
        parse(p)
    assert "declares a DTD" in str(exc.value)


def test_rejects_any_doctype_even_without_entities(tmp_path):
    # The refusal is on the declaration, not on what it contains — a
    # DOCTYPE is the delivery mechanism, and no corpus format needs one.
    p = tmp_path / "dtd.xml"
    p.write_text('<?xml version="1.0"?>\n<!DOCTYPE TEI SYSTEM "tei.dtd">\n<TEI/>\n', "utf-8")
    with pytest.raises(UnsafeXMLError):
        parse(p)


def test_parses_an_ordinary_document(tmp_path):
    p = tmp_path / "ok.xml"
    p.write_text(PLAIN_TEI, encoding="utf-8")
    tree = parse(p)
    body = tree.getroot().find(".//{http://www.tei-c.org/ns/1.0}p")
    assert body is not None
    assert body.text == "Ἐν ἀρχῇ ἦν ὁ λόγος"


def test_accepts_a_path_string(tmp_path):
    p = tmp_path / "ok.xml"
    p.write_text(PLAIN_TEI, encoding="utf-8")
    assert parse(str(p)).getroot() is not None


def test_doctype_in_body_text_does_not_trip_a_large_file(tmp_path):
    # The scan reads only the prolog window. A document that merely
    # *mentions* the string far past it still parses — this is why the
    # window exists, and it is the behaviour to know about if a source
    # ever legitimately contains the literal.
    filler = "<p>x</p>\n" * 9000
    p = tmp_path / "big.xml"
    p.write_text(f'<?xml version="1.0"?>\n<TEI>\n{filler}<p>&lt;!DOCTYPE lolz&gt;</p>\n</TEI>\n', "utf-8")
    assert p.stat().st_size > 64 * 1024
    assert parse(p).getroot().tag == "TEI"
