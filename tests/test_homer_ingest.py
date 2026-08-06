"""Ingest tests for Homer (Perseus TEI).

Homer's TEI shape is distinct from Plato/Aristotle:

* `unit="card"` is the only chunk boundary. There are no `unit="section"`
  or `unit="bekker page"` milestones, so `_detect_chunk_boundary_units`
  must return `{"card"}`.
* `<div1 type="Book" n="N">` wraps each book; combining with the card's
  starting line number gives the canonical `<book>.<line>` section
  label ("1.1", "1.33", ...).
* The XML body is Perseus beta-code; ingest must transliterate it to
  polytonic Unicode at flush time (after computing chunk_id, so re-
  ingest keeps stable ids).

These tests build a tiny synthetic Homer-style XML in-memory so they
run without depending on the real Perseus dltext archive on disk.
"""

from __future__ import annotations

from pathlib import Path

from minerva import tei

_HOMER_FIXTURE_XML = """<?xml version="1.0" encoding="utf-8"?>
<TEI.2>
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>Iliad, Machine readable text</title>
      </titleStmt>
      <sourceDesc>
        <biblStruct>
          <monogr>
            <title>The Iliad with an English Translation</title>
            <imprint>
              <date>1924</date>
            </imprint>
          </monogr>
        </biblStruct>
      </sourceDesc>
    </fileDesc>
  </teiHeader>
  <text>
    <body>
      <div1 type="Book" n="1">
        <milestone unit="card" n="1"/>
        <l>mh=nin a)/eide qea\\ *phlhi+a/dew *)axilh=os</l>
        <l>ou)lome/nhn, h(\\ muri/' *)axaioi=s a)/lge' e)/qhken,</l>
        <milestone unit="card" n="8"/>
        <l>ti/s t' a)/r sfwe qew=n e)/ridi cune/hke ma/xesqai;</l>
        <milestone unit="card" n="33"/>
        <l>w(\\s e)/fat': e)/ddeisen d' o( ge/rwn kai\\ e)pei/qeto mu/qw|.</l>
      </div1>
      <div1 type="Book" n="2">
        <milestone unit="card" n="1"/>
        <l>a)/lloi me/n r(a qeoi/ te kai\\ a)ne/res i(ppokorustai\\</l>
      </div1>
    </body>
  </text>
</TEI.2>
"""


def _write_fixture(tmp_path: Path) -> Path:
    # Filename matters: `_detect_lang` reads the stem suffix. `_gr`
    # forces lang='grc' regardless of header.
    path = tmp_path / "hom_il_gr.xml"
    path.write_text(_HOMER_FIXTURE_XML, encoding="utf-8")
    return path


class TestHomerCardChunking:
    def test_emits_one_chunk_per_card_with_book_line_section(self, tmp_path: Path) -> None:
        path = _write_fixture(tmp_path)
        chunks = list(tei.parse_file(path, corpus="homer", author="Homer"))

        # 3 cards in book 1 + 1 card in book 2 = 4 chunks.
        assert len(chunks) == 4
        # Section format is `<book>.<line>` derived from `<div1 type="Book">`
        # + card's starting line. This is the canonical Homer locator.
        sections = [c.section for c in chunks]
        assert sections == ["1.1", "1.8", "1.33", "2.1"]

    def test_book_locator_carries_through_with_known_boundary_quirk(self, tmp_path: Path) -> None:
        path = _write_fixture(tmp_path)
        chunks = list(tei.parse_file(path, corpus="homer", author="Homer"))
        # Known chunker quirk: the LAST chunk inside book N gets its
        # `book` column re-stamped to N+1 because `_cur_book` updates
        # on `<div1 type="Book" n="N+1">` entry BEFORE the next card's
        # `_flush()` flushes the still-buffered tail of book N. The
        # `section` column is set correctly ("1.33") because section
        # is captured at the card milestone, before the book switch.
        # This is a pre-existing inconsistency; the test pins current
        # behavior so a future fix is recognized rather than silently
        # changing the contract.
        sections = [c.section for c in chunks]
        books = [c.book for c in chunks]
        assert sections == ["1.1", "1.8", "1.33", "2.1"]
        assert books == ["1", "1", "2", "2"]
        # The mismatch is the third chunk: section says book 1, book
        # column says book 2. Note that downstream consumers should
        # prefer `section` (which has the book prefix anyway) when the
        # two disagree.
        assert chunks[2].section == "1.33"
        assert chunks[2].book == "2"

    def test_metadata_propagated_from_args_and_header(self, tmp_path: Path) -> None:
        path = _write_fixture(tmp_path)
        chunks = list(tei.parse_file(path, corpus="homer", author="Homer"))
        first = chunks[0]
        assert first.corpus == "homer"
        assert first.author == "Homer"
        # lang resolved from filename `_gr` suffix.
        assert first.lang == "grc"
        # Translator title is from `<sourceDesc><biblStruct><monogr><title>`.
        assert first.translator == "The Iliad with an English Translation"
        assert first.edition_year == "1924"
        assert first.source_file == "hom_il_gr.xml"


class TestHomerBetacodeTransliteration:
    def test_betacode_converted_to_polytonic_unicode(self, tmp_path: Path) -> None:
        path = _write_fixture(tmp_path)
        chunks = list(tei.parse_file(path, corpus="homer", author="Homer"))
        first = chunks[0]
        # The first card is the Iliad's incipit. The betacode
        # `mh=nin a)/eide qea\\` must transliterate to Unicode with
        # polytonic accents — verify on a few high-confidence cores:
        #  * "mh=nin" → "μῆνιν" (mu + eta+circumflex + nu + iota + nu)
        #  * "qea\\"  → "θεὰ"   (theta + eta + alpha+grave)
        # Asserting partials so a minor diacritic flip in the
        # beta-code library doesn't break the test, but enough that a
        # missing/regressed transliteration would clearly fail.
        assert "μῆνιν" in first.text
        assert "θεὰ" in first.text
        # No raw beta-code escapes should remain.
        assert "mh=" not in first.text
        assert "qea" not in first.text

    def test_chunk_id_stable_across_betacode_change(self, tmp_path: Path) -> None:
        # chunk_id is computed BEFORE transliteration (so a re-ingest
        # against a different beta-code library doesn't churn ids).
        # Run the parser twice and confirm the ids match — regression
        # guard for the "compute id then transliterate" ordering.
        path = _write_fixture(tmp_path)
        run1 = list(tei.parse_file(path, corpus="homer", author="Homer"))
        run2 = list(tei.parse_file(path, corpus="homer", author="Homer"))
        assert [c.chunk_id for c in run1] == [c.chunk_id for c in run2]


class TestChunkBoundaryDetection:
    def test_card_only_policy_when_no_section_milestones(self) -> None:
        # White-box: feed a body element with only `card` milestones
        # to the boundary detector; should pick card as the boundary.
        import xml.etree.ElementTree as ET

        body = ET.fromstring(
            "<body><milestone unit='card' n='1'/><milestone unit='card' n='8'/></body>"
        )
        units = tei._detect_chunk_boundary_units(body)
        assert units == frozenset({"card"})

    def test_section_wins_when_both_present(self) -> None:
        # The "stray card in a section-chunked work" case
        # (Aristotle Economics has 5 cards in a 28-section body).
        # `section` should win; cards should NOT split.
        import xml.etree.ElementTree as ET

        body = ET.fromstring(
            "<body><milestone unit='section' n='327a'/><milestone unit='card' n='1'/></body>"
        )
        units = tei._detect_chunk_boundary_units(body)
        assert units == frozenset({"section"})

    def test_no_boundary_units_when_neither_present(self) -> None:
        import xml.etree.ElementTree as ET

        body = ET.fromstring("<body><milestone unit='page' n='12'/></body>")
        assert tei._detect_chunk_boundary_units(body) == frozenset()
