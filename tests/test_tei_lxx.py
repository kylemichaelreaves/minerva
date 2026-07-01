"""Hermetic tests for the Septuagint TEI P5 parser (``tei_lxx.py``).

Each fixture is a minimal hand-written TEI file locking one behavior
(and one bug we hit) of the 2026-07 apparatus/poetry remediation:

* ``<note>`` apparatus subtrees are excluded from verse text — Swete's
  marginal sigla ("A") and footnote variants used to leak inline
  (Gen 1:2 read "ἡ δὲ γῆ A ἦν ἀόρατος…").
* Poetry in ``<l>``/``<lg>`` lines is collected — Job, Proverbs,
  Wisdom, and Song of Songs are encoded verse-div → ``<l>`` with no
  ``<p>`` at all, so the old ``<p>``-only walker silently dropped
  every verse of all four books (~2,545 verses), plus inset poetry
  like Gen 49 (~2,769 more).
* Single-chapter books (Letter of Jeremiah) have no chapter div;
  their chapter defaults to "1" instead of dropping the whole book.
* A mis-nested wrapper verse div (Psalms has one verse enclosing the
  next five) still yields its own content before recursion.
* Stray manuscript sigla that leaked into the running text as bare
  tokens (standalone Latin capitals, "§") are scrubbed.
"""

from __future__ import annotations

from pathlib import Path

from minerva.locations import BCV_BOOK_ABBR
from minerva.sources import tei_lxx

_TEI_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>Test book</title>
        <editor>Henry Barclay Swete</editor>
      </titleStmt>
      <sourceDesc><bibl><date>1909</date></bibl></sourceDesc>
    </fileDesc>
  </teiHeader>
  <text><body>
    <div type="edition" n="urn:cts:test">
{body}
    </div>
  </body></text>
</TEI>
"""


def _parse(tmp_path: Path, body: str, *, book_title: str = "Genesis") -> list:
    src = tmp_path / "test.xml"
    src.write_text(_TEI_HEADER.format(body=body), encoding="utf-8")
    return list(
        tei_lxx.parse_file(
            src,
            book_title=book_title,
            book_abbr=BCV_BOOK_ABBR[book_title],
            work_code=book_title.lower(),
        )
    )


def test_note_apparatus_excluded_from_verse_text(tmp_path: Path) -> None:
    # Real shape of Swete Gen 1:2: a marginal siglum <note> mid-verse.
    body = """
      <div type="textpart" subtype="chapter" n="1">
        <div type="textpart" subtype="verse" n="2">
          <p>ἡ δὲ γῆ <note type="marginal">A</note> ἦν ἀόρατος
          <note type="footnote">1 αορατος] αοικητος Θ</note>
          καὶ ἀκατασκεύαστος.</p>
        </div>
      </div>
    """
    chunks = _parse(tmp_path, body)
    assert len(chunks) == 1
    assert chunks[0].text == "ἡ δὲ γῆ ἦν ἀόρατος καὶ ἀκατασκεύαστος."
    assert chunks[0].section == "Gen 1:2"


def test_poetry_l_lines_without_p_are_collected(tmp_path: Path) -> None:
    # Job/Proverbs/Wisdom/Song shape: verse div holds only <l> lines.
    body = """
      <div type="textpart" subtype="chapter" n="1">
        <div type="textpart" subtype="verse" n="21">
          <l>γυμνὸς ἐξῆλθον ἐκ κοιλίας μητρός μου,</l>
          <l>γυμνὸς καὶ ἀπελεύσομαι ἐκεῖ.</l>
        </div>
      </div>
    """
    chunks = _parse(tmp_path, body, book_title="Job")
    assert len(chunks) == 1
    assert chunks[0].section == "Job 1:21"
    assert chunks[0].text == ("γυμνὸς ἐξῆλθον ἐκ κοιλίας μητρός μου, γυμνὸς καὶ ἀπελεύσομαι ἐκεῖ.")


def test_acrostic_p_heading_joins_l_lines_in_order(tmp_path: Path) -> None:
    # Lamentations shape: acrostic-letter <p> heading + <l> poetry.
    # The old parser kept ONLY the heading ("Δάλεθ.") — 88 hollow verses.
    body = """
      <div type="textpart" subtype="chapter" n="2">
        <div type="textpart" subtype="verse" n="4">
          <p>Δάλεθ.</p>
          <l>Ἐνέτεινεν τόξον αὐτοῦ ὡς ἐχθρὸς ὑπεναντίος,</l>
        </div>
      </div>
    """
    chunks = _parse(tmp_path, body, book_title="Lamentations")
    assert len(chunks) == 1
    assert chunks[0].text == ("Δάλεθ. Ἐνέτεινεν τόξον αὐτοῦ ὡς ἐχθρὸς ὑπεναντίος,")


def test_lg_groups_are_collected(tmp_path: Path) -> None:
    body = """
      <div type="textpart" subtype="chapter" n="1">
        <div type="textpart" subtype="verse" n="1">
          <lg><l>στίχος πρῶτος</l><l>στίχος δεύτερος</l></lg>
        </div>
      </div>
    """
    chunks = _parse(tmp_path, body)
    assert len(chunks) == 1
    assert chunks[0].text == "στίχος πρῶτος στίχος δεύτερος"


def test_single_chapter_book_defaults_chapter_to_1(tmp_path: Path) -> None:
    # Letter of Jeremiah shape: verse divs directly under the edition,
    # no chapter level. The old walker required a chapter crumb and
    # dropped the entire 72-verse book.
    body = """
      <div type="textpart" subtype="verse" n="1">
        <p>Ἀντίγραφον ἐπιστολῆς ἧς ἀπέστειλεν Ἰερεμίας.</p>
      </div>
      <div type="textpart" subtype="verse" n="2">
        <p>Διὰ τὰς ἁμαρτίας ἃς ἡμαρτήκατε ἐναντίον τοῦ θεοῦ.</p>
      </div>
    """
    chunks = _parse(tmp_path, body, book_title="Letter of Jeremiah")
    assert [c.section for c in chunks] == ["EpJer 1:1", "EpJer 1:2"]


def test_misnested_wrapper_verse_keeps_own_content(tmp_path: Path) -> None:
    # Psalms shape: one verse div encloses the following verse divs.
    # The wrapper's own <p> must not vanish during recursion.
    body = """
      <div type="textpart" subtype="chapter" n="17">
        <div type="textpart" subtype="verse" n="3">
          <p>κείμενον τρίτου στίχου.</p>
          <div type="textpart" subtype="verse" n="4">
            <p>κείμενον τετάρτου στίχου.</p>
          </div>
        </div>
      </div>
    """
    chunks = _parse(tmp_path, body, book_title="Psalms")
    sections = {c.section: c.text for c in chunks}
    assert sections == {
        "Ps 17:3": "κείμενον τρίτου στίχου.",
        "Ps 17:4": "κείμενον τετάρτου στίχου.",
    }


def test_stray_sigla_tokens_scrubbed(tmp_path: Path) -> None:
    # First1KGreek encoding defect: codex letters and the § supplied-
    # text mark leaked into the running text as bare tokens (Gen 19:26
    # read "εἰς D τὰ ὀπίσω"). Standalone Latin capitals are never
    # genuine Greek — scrub whitespace-delimited runs of them.
    body = """
      <div type="textpart" subtype="chapter" n="19">
        <div type="textpart" subtype="verse" n="26">
          <p>καὶ ἐπέβλεψεν ἡ γυνὴ αὐτοῦ εἰς <lb n="26"/> D τὰ ὀπίσω.</p>
        </div>
        <div type="textpart" subtype="verse" n="27">
          <p>πρὸ τοῦ § B* διασπαρῆναι ἐπὶ προσώπου §</p>
        </div>
      </div>
    """
    chunks = _parse(tmp_path, body)
    assert chunks[0].text == "καὶ ἐπέβλεψεν ἡ γυνὴ αὐτοῦ εἰς τὰ ὀπίσω."
    assert chunks[1].text == "πρὸ τοῦ διασπαρῆναι ἐπὶ προσώπου"


def test_greek_capitals_survive_the_siglum_scrub(tmp_path: Path) -> None:
    # Greek capitals are distinct codepoints (Α U+0391 ≠ A U+0041);
    # a standalone Greek majuscule (numeral, nomen sacrum) must stay.
    body = """
      <div type="textpart" subtype="chapter" n="1">
        <div type="textpart" subtype="verse" n="1">
          <p>ἐγώ εἰμι τὸ Α καὶ τὸ Ω.</p>
        </div>
      </div>
    """
    # NB: the Α here is GREEK CAPITAL ALPHA, not Latin A.
    chunks = _parse(tmp_path, body)
    assert chunks[0].text == "ἐγώ εἰμι τὸ Α καὶ τὸ Ω."


def test_verse_without_content_elements_is_skipped(tmp_path: Path) -> None:
    body = """
      <div type="textpart" subtype="chapter" n="1">
        <div type="textpart" subtype="verse" n="1">
          <note type="footnote">apparatus only, no text</note>
        </div>
        <div type="textpart" subtype="verse" n="2">
          <p>κείμενον.</p>
        </div>
      </div>
    """
    chunks = _parse(tmp_path, body)
    assert [c.section for c in chunks] == ["Gen 1:2"]
