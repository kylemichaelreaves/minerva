"""Ingest tests for the Diels pre-Socratic OCR text.

Two surfaces:

* **Synthetic fixture tests** — hand-built mini-source covering the
  parser's discrimination edge cases (chapter heading vs. A-fragment,
  Greek-vs-German fragment, apparatus rejection, print-line-number
  prefix stripping, OCR'd integer in chapter heading).

* **Real-file integration test** — skipped when the OCR file isn't
  available locally. Confirms counts + locator format for Heraclitus
  using the actual archive.org download in the user's Downloads
  folder.

Mirrors the pattern from `tests/test_homer_ingest.py` +
`tests/test_biblical_parsers.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minerva import presocratic
from minerva.authors.presocratic_works import _PHASE_1, find_by_chapter_heading

# ════════════════════════════════════════════════════════════════════
# Synthetic-fixture tests
# ════════════════════════════════════════════════════════════════════


_SYNTHETIC = """\
A. LEHRE.
1. SourceCite about Anaximenes here, just A-fragment noise.
12. HERAKLEITOS.
A. LEHRE.
1. DioGENES ix 1—2. (1) Ἡράκλειτος about Heraclitus — A-fragment.
B. FRAGMENTE.
1. [2 Bywater] Sext. adv. math. vii 132 τοῦ δὲ λόγου τοῦδ᾽ ἐόντος ἀεὶ ἀξύνετοι.
2. [92] Sext. vii 133 διὸ δεῖ ἕπεσθαι τῶι κοινῶι.
5 μυοῦνται Clem.: μυεῦνται Euseb. — apparatus, ignore.
1. Für dies Wort aber gewinnen die Menschen kein Verständnis.
2. Drum ist's Pflicht dem Gemeinsamen zu folgen.
21. EMPEDOKLES,.
B. FRAGMENTE.
25 1. [1—32 Karst.] Sext. vii 100 ὦ φίλοι, οἳ μέγα ἄστυ.
1. O Freunde, die ihr in der großen Stadt wohnt.
"""


@pytest.fixture
def synthetic_path(tmp_path: Path) -> Path:
    p = tmp_path / "synthetic_dk.txt"
    p.write_text(_SYNTHETIC, encoding="utf-8")
    return p


class TestSyntheticFixture:
    def test_only_b_fragments_emitted(self, synthetic_path: Path) -> None:
        chunks = list(presocratic.parse_file(synthetic_path))
        # No A-fragment chunks (we have two A-fragments in the source
        # but only B-FRAGMENTE blocks should produce chunks).
        for c in chunks:
            assert c.section is not None
            assert " B " in c.section, f"unexpected non-B section {c.section!r}"

    def test_heraclitus_b1_greek_and_german_paired(
        self, synthetic_path: Path
    ) -> None:
        chunks = list(presocratic.parse_file(synthetic_path))
        by_section_lang = {(c.section, c.lang): c for c in chunks}

        grc = by_section_lang.get(("22 B 1", "grc"))
        deu = by_section_lang.get(("22 B 1", "deu"))
        assert grc is not None, "missing Greek B 1 for Heraclitus"
        assert deu is not None, "missing German B 1 for Heraclitus"

        # Greek text contains the Greek script.
        assert "τοῦ δὲ λόγου" in grc.text
        # Source citation lands in `book` (Latin-script prefix up to
        # the first Greek char).
        assert grc.book is not None and "Sext" in grc.book
        # German text contains the German prose; no source citation
        # since no Greek-script discriminator fired.
        assert deu.text.startswith("Für dies Wort")
        assert deu.book is None

    def test_apparatus_lines_dropped(self, synthetic_path: Path) -> None:
        chunks = list(presocratic.parse_file(synthetic_path))
        # The apparatus line `5 μυοῦνται Clem.: μυεῦνται` must NOT
        # produce a fragment-5 chunk (there is no Heraclitus B 5 in
        # the fixture).
        for c in chunks:
            assert c.section != "22 B 5", "apparatus line spawned chunk"

    def test_chapter_heading_with_trailing_comma_recognised(
        self, synthetic_path: Path
    ) -> None:
        # `21. EMPEDOKLES,.` is an OCR quirk in the real source; the
        # parser must still recognise Empedocles and emit its B 1.
        chunks = list(presocratic.parse_file(synthetic_path))
        emp_sections = {c.section for c in chunks if c.author == "Empedocles"}
        assert "31 B 1" in emp_sections

    def test_print_line_number_prefix_stripped(self, synthetic_path: Path) -> None:
        # `25 1. [1—32 Karst.] ...` opens Empedocles B 1 with a leading
        # print-line-number `25`. The parser must strip it and still
        # detect fragment 1.
        chunks = list(presocratic.parse_file(synthetic_path))
        emp_b1 = next(
            (c for c in chunks if c.author == "Empedocles" and c.section == "31 B 1"),
            None,
        )
        assert emp_b1 is not None
        assert emp_b1.lang == "grc"
        assert "φίλοι" in emp_b1.text

    def test_chunk_fields_carry_corpus_metadata(self, synthetic_path: Path) -> None:
        chunks = list(presocratic.parse_file(synthetic_path))
        c = next(c for c in chunks if c.section == "22 B 1" and c.lang == "grc")
        assert c.corpus == "presocratic"
        assert c.citation_system == "diels_kranz"
        assert c.work == "Fragments (DK 22)"
        assert c.translator == "(Original)"
        assert c.edition_year == "1912"

    def test_german_chunk_carries_translator(self, synthetic_path: Path) -> None:
        chunks = list(presocratic.parse_file(synthetic_path))
        c = next(c for c in chunks if c.section == "22 B 1" and c.lang == "deu")
        assert c.translator == "Hermann Diels"
        assert c.lang == "deu"


# ════════════════════════════════════════════════════════════════════
# find_by_chapter_heading — direct unit tests
# ════════════════════════════════════════════════════════════════════


class TestCrammedLines:
    """Regression tests for the OCR-quirk fixes in the parser cleanup
    pass: multiple Greek-or-German fragments crammed onto one text
    line, page-break running heads between a fragment's apparatus and
    its Greek continuation, and OCR-confused Latin Roman numerals
    leaking into the Greek body."""

    def test_crammed_greek_line_splits_into_multiple_fragments(
        self, tmp_path: Path
    ) -> None:
        # Two Greek B-fragments crammed onto one OCR line, both with
        # `[cross-ref]` brackets. The parser must split them into B 1
        # and B 2.
        src = (
            "12. HERAKLEITOS.\n"
            "B. FRAGMENTE.\n"
            "1. [2 Bywater] Sext. vii 132 τοῦ δὲ λόγου τοῦδ᾽. "
            "2. [92] Sext. vii 133 διὸ δεῖ ἕπεσθαι τῶι κοινῶι.\n"
            "1. Erste Übersetzung.\n"
            "2. Zweite Übersetzung.\n"
        )
        p = tmp_path / "crammed.txt"
        p.write_text(src, encoding="utf-8")
        chunks = list(presocratic.parse_file(p))
        secs = {(c.section, c.lang): c for c in chunks if c.author == "Heraclitus"}
        # All four chunks (B 1 grc/deu, B 2 grc/deu) must exist.
        assert ("22 B 1", "grc") in secs
        assert ("22 B 1", "deu") in secs
        assert ("22 B 2", "grc") in secs
        assert ("22 B 2", "deu") in secs
        # And the Greek text of B 1 must NOT contain B 2's body.
        assert "διὸ δεῖ" not in secs[("22 B 1", "grc")].text

    def test_crammed_german_line_splits_into_multiple_fragments(
        self, tmp_path: Path
    ) -> None:
        # Two German translations crammed on one OCR line. The
        # discriminator is `N. <Capital><lowercase>` patterns.
        src = (
            "12. HERAKLEITOS.\n"
            "B. FRAGMENTE.\n"
            "1. [a] Sext. abc α β γ δ.\n"
            "2. [b] Plut. def ε ζ η θ.\n"
            "1. Erste Übersetzung. 2. Zweite Übersetzung.\n"
        )
        p = tmp_path / "crammed_de.txt"
        p.write_text(src, encoding="utf-8")
        chunks = list(presocratic.parse_file(p))
        secs = {(c.section, c.lang): c for c in chunks if c.author == "Heraclitus"}
        assert ("22 B 1", "deu") in secs
        assert ("22 B 2", "deu") in secs
        # B 1 German must not contain B 2's body.
        assert "Zweite" not in secs[("22 B 1", "deu")].text

    def test_source_cite_with_ocr_roman_numerals_lands_in_book(
        self, tmp_path: Path
    ) -> None:
        # The Latin source citation `Sext. adv. math. vii 132` OCRs
        # `vii` as `ναι` (pseudo-Greek). The improved
        # `_strip_source_citation` looks for the first PAIR of pure-
        # Greek tokens, so the isolated `ναι` stays in the citation
        # rather than starting the body.
        src = (
            "12. HERAKLEITOS.\n"
            "B. FRAGMENTE.\n"
            "1. [2 Bywater] Sext. adv. math. ναι 132 τοῦ δὲ λόγου τοῦδ᾽ ἐόντος.\n"
            "1. Übersetzung von Heraclitus B 1.\n"
        )
        p = tmp_path / "ocr_roman.txt"
        p.write_text(src, encoding="utf-8")
        chunks = list(presocratic.parse_file(p))
        b1_grc = next(
            c
            for c in chunks
            if c.author == "Heraclitus"
            and c.section == "22 B 1"
            and c.lang == "grc"
        )
        # Body starts at the first long Greek run, not at the OCR'd
        # `ναι` (which is really `vii`).
        assert b1_grc.text.startswith("τοῦ δὲ λόγου")
        # The OCR'd Roman numeral lives in book alongside the
        # location reference.
        assert b1_grc.book is not None
        assert "ναι" in b1_grc.book
        assert "132" in b1_grc.book


class TestChapterHeadingLookup:
    def test_phase_1_name_resolves(self) -> None:
        entry = find_by_chapter_heading(12, "HERAKLEITOS")
        assert entry is not None
        assert entry[3] == "Heraclitus"
        assert entry[1] == 22  # modern DK chapter

    def test_unknown_name_returns_none(self) -> None:
        # `STRABO` is an ancient author cited inside A-fragments; not a
        # philosopher. Must NOT resolve to anything (regression
        # against the earlier bug where integer fallback wrongly
        # mapped `2. STRABO ...` to Anaximander).
        assert find_by_chapter_heading(2, "STRABO") is None
        assert find_by_chapter_heading(1, "DIOG") is None

    def test_chapter_int_alone_does_not_match(self) -> None:
        # Integer-only fallback is explicitly disabled. Even when the
        # int IS a valid 1912 chapter number, mismatched name must
        # return None.
        assert find_by_chapter_heading(12, "NOTAPHILOSOPHER") is None


# ════════════════════════════════════════════════════════════════════
# Real-file integration test
# ════════════════════════════════════════════════════════════════════


_OCR_FILE = Path.home() / "Downloads" / "diefragmentederv12diel_hocr_searchtext.txt"


@pytest.mark.skipif(
    not _OCR_FILE.exists(),
    reason="archive.org Vorsokratiker OCR file not present in ~/Downloads",
)
class TestRealFile:
    def test_heraclitus_well_represented(self) -> None:
        chunks = list(presocratic.parse_file(_OCR_FILE))
        heraclitus = [c for c in chunks if c.author == "Heraclitus"]
        # Canonical count is ~140 B-fragments. Allow slop on both
        # sides because page-boundary text continuations can shift
        # the exact total.
        assert len(heraclitus) >= 100, f"too few Heraclitus chunks: {len(heraclitus)}"
        # Both languages present in roughly comparable counts.
        grc_count = sum(1 for c in heraclitus if c.lang == "grc")
        deu_count = sum(1 for c in heraclitus if c.lang == "deu")
        assert grc_count >= 80
        assert deu_count >= 80

    def test_heraclitus_b1_locator_format(self) -> None:
        chunks = list(presocratic.parse_file(_OCR_FILE))
        b1 = [c for c in chunks if c.author == "Heraclitus" and c.section == "22 B 1"]
        # One Greek + one German.
        langs = sorted(c.lang for c in b1)
        assert langs == ["deu", "grc"]

    def test_phase_1_authors_present(self) -> None:
        chunks = list(presocratic.parse_file(_OCR_FILE))
        authors = {c.author for c in chunks}
        # Thales, Anaximander, Pythagoras have no B-fragments in DK
        # (they survive only via testimonia) — their absence is
        # correct. The other Phase-1 names must all appear.
        expected = {
            "Anaximenes",
            "Xenophanes",
            "Heraclitus",
            "Parmenides",
            "Zeno of Elea",
            "Melissus",
            "Empedocles",
            "Anaxagoras",
            "Diogenes of Apollonia",
        }
        missing = expected - authors
        assert not missing, f"Phase-1 authors missing from output: {missing}"

    def test_section_format_is_modern_dk(self) -> None:
        chunks = list(presocratic.parse_file(_OCR_FILE))
        # Sample one Heraclitus section. The modern DK number for
        # Heraclitus is 22 (not 12, which is the 1912 source's number).
        her_section = next(
            c.section for c in chunks if c.author == "Heraclitus"
        )
        assert her_section is not None
        assert her_section.startswith("22 B "), (
            f"expected modern DK 22 prefix, got {her_section!r}"
        )

    def test_phase_1_table_consistency(self) -> None:
        # Sanity check: the table itself should be sane (no duplicate
        # 1912 chapters, no duplicate modern DK chapters, no duplicate
        # canonical names).
        chapters_1912 = [e[0] for e in _PHASE_1]
        chapters_mod = [e[1] for e in _PHASE_1]
        names = [e[3] for e in _PHASE_1]
        assert len(set(chapters_1912)) == len(chapters_1912)
        assert len(set(chapters_mod)) == len(chapters_mod)
        assert len(set(names)) == len(names)
