"""Tests for the Theognis Greek re-source (#431).

Welcker 1826's OCR is corrupted: Latin letters substituted into Greek
words, and its critical apparatus interleaved with the poems as body
text (26.9% of the work's letters). el.wikisource.org's Ελεγείαι
Θεόγνιδος is the replacement — human-transcribed, no apparatus, the
complete canonical sequence (lines 1-1389, both books).

`_extract_greek` turns its raw wikitext into plain text shaped for the
generic `locator="chapter"` paragraph splitter: one blank-line-separated
block per elegy, `{{r|N}}` line-number templates rendered as inline
`[N]` annotations, MediaWiki chrome (the header template, the
translation cross-link, category links) stripped.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PERSEUS = Path(__file__).resolve().parents[1] / "perseus"


@pytest.fixture(autouse=True)
def _perseus_on_path():
    sys.path.insert(0, str(PERSEUS))
    yield
    sys.path.remove(str(PERSEUS))


def _extract_greek_wikisource(wikitext: str) -> str:
    import download_theognis

    return download_theognis._extract_greek_wikisource(wikitext)

# A trimmed but structurally faithful excerpt of the real page's
# wikitext (fetched and inspected directly against the live page).
_SAMPLE_WIKITEXT = """{{κεφαλίδα
|τίτλος=Ἐλεγεῖαι
|συγγραφέας=Θέογνις ο Μεγαρεύς
|σημειώσεις=
}}

*μετάφραση στίχων στο: [[Στέφανος (Σίμος Μενάρδος)/Μούσες και Χάριτες]]

ΕΛΕΓΕΙΩΝ Α

Ὦ ἄνα, Λητοῦς υἱέ, Διὸς τέκος, οὔποτε σεῖο <br>
λήσομαι ἀρχόμενος οὐδ' ἀποπαυόμενος, <br>

Κύρνε, σοφιζομένῳ μὲν ἐμοὶ σφρηγὶς ἐπικείσθω <br>
τοῖσδ' ἔπεσιν, λήσει δ' οὔποτε κλεπτόμενα, {{r|20}}<br>
οὐδέ τις ἀλλάξει κάκιον τοὐσθλοῦ παρεόντος· <br>

ΕΛΕΓΕΙΩΝ Β

Σχέτλι' Ἔρως, μανίαι σε τιθηνήσαντο λαβοῦσαι· {{r|1231}}<br>
ἐκ σέθεν ὤλετο μὲν Ἰλίου ἀκρόπολις, <br>

Κυπρογενὲς Κυθέρεια δολοπλόκε, σοὶ τί περισσόν <br>
Ζεὺς τόδε τιμήσας δῶρον ἔδωκεν ἔχειν;   {{r|1387}}<br>
δαμνᾶις δ' ἀνθρώπων πυκινὰς φρένας, οὐδέ τίς ἐστιν <br>
οὕτως ἴφθιμος καὶ σοφὸς ὥστε φυγεῖν.   {{r|1389}}<br>

[[Κατηγορία:Ποίηση]]

[[Κατηγορία:Αρχαία και Κλασική γραμματεία]]
"""


class TestExtractGreekWikisource:
    def test_strips_the_header_template_and_translation_link(self):
        out = _extract_greek_wikisource(_SAMPLE_WIKITEXT)
        assert "κεφαλίδα" not in out
        assert "μετάφραση" not in out
        assert "Στέφανος" not in out

    def test_strips_category_links(self):
        out = _extract_greek_wikisource(_SAMPLE_WIKITEXT)
        assert "Κατηγορία" not in out

    def test_no_html_break_tags_survive(self):
        out = _extract_greek_wikisource(_SAMPLE_WIKITEXT)
        assert "<br>" not in out
        assert "<br/>" not in out
        assert "<br />" not in out

    def test_line_number_templates_become_bracketed_numbers(self):
        out = _extract_greek_wikisource(_SAMPLE_WIKITEXT)
        assert "{{r|" not in out
        assert "[20]" in out
        assert "[1231]" in out
        assert "[1389]" in out

    def test_both_books_are_present(self):
        out = _extract_greek_wikisource(_SAMPLE_WIKITEXT)
        assert "ΕΛΕΓΕΙΩΝ Α" in out
        assert "ΕΛΕΓΕΙΩΝ Β" in out
        # Book B starts at the canonical line the source itself marks.
        assert out.index("ΕΛΕΓΕΙΩΝ Β") > out.index("[20]")
        assert out.index("[1231]") > out.index("ΕΛΕΓΕΙΩΝ Β")

    def test_the_greek_verses_themselves_survive_intact(self):
        out = _extract_greek_wikisource(_SAMPLE_WIKITEXT)
        assert "Ὦ ἄνα, Λητοῦς υἱέ, Διὸς τέκος, οὔποτε σεῖο" in out
        assert "Σχέτλι' Ἔρως, μανίαι σε τιθηνήσαντο λαβοῦσαι·" in out

    def test_no_stray_latin_apparatus_survives(self):
        """The whole point: nothing resembling Welcker's Latin
        critical notes should be possible to introduce, since none
        exists in the Wikisource source to begin with."""

        out = _extract_greek_wikisource(_SAMPLE_WIKITEXT)

        # Every non-blank line must contain a Greek letter — no
        # apparatus-only line survives.
        for line in out.splitlines():
            if line.strip():
                assert re.search(r"[Ͱ-Ͽἀ-῿]", line), f"non-Greek line: {line!r}"

    def test_paragraphs_are_blank_line_separated(self):
        """Matches split_paragraphic.py's `_split_chapter_block`
        convention — one blank-line-delimited block per elegy."""

        out = _extract_greek_wikisource(_SAMPLE_WIKITEXT)
        blocks = [b for b in out.split("\n\n") if b.strip()]
        assert len(blocks) >= 3  # at least a few distinct elegies survived
