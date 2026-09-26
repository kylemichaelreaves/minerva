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

from minerva.authors.presocratic_works import _PHASE_1, find_by_chapter_heading
from minerva.sources import presocratic

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

    def test_heraclitus_b1_greek_and_german_paired(self, synthetic_path: Path) -> None:
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

    def test_chapter_heading_with_trailing_comma_recognised(self, synthetic_path: Path) -> None:
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

    def test_crammed_greek_line_splits_into_multiple_fragments(self, tmp_path: Path) -> None:
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

    def test_crammed_german_line_splits_into_multiple_fragments(self, tmp_path: Path) -> None:
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

    def test_source_cite_with_ocr_roman_numerals_lands_in_book(self, tmp_path: Path) -> None:
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
            if c.author == "Heraclitus" and c.section == "22 B 1" and c.lang == "grc"
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


_OCR_FILE = Path("data/presocratic/diefragmentederv12diel_hocr_searchtext.txt")


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
        her_section = next(c.section for c in chunks if c.author == "Heraclitus")
        assert her_section is not None
        assert her_section.startswith("22 B "), f"expected modern DK 22 prefix, got {her_section!r}"

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


# ════════════════════════════════════════════════════════════════════
# Line numbers vs. apparatus (#673, #680)
# ════════════════════════════════════════════════════════════════════
#
# Diels numbers every fifth verse in the margin, and the apparatus at
# the foot of each page refers to verses by the same numbers. A leading
# integer therefore marks both, and the parser used to read it as
# "apparatus" either way: numbered verse was dropped (#680) and the
# apparatus's own unnumbered continuation lines were routed into the
# fragments as text (#673).


def _parse(tmp_path: Path, src: str) -> list:
    p = tmp_path / "dk.txt"
    p.write_text(src, encoding="utf-8")
    return list(presocratic.parse_file(p))


def _body(chunks: list, section: str, lang: str) -> str:
    """Text of the one body (non-editorial) chunk for section/lang."""

    (c,) = [c for c in chunks if c.section == section and c.lang == lang and c.block_type is None]
    return c.text


def _editorial(chunks: list) -> str:
    return " ".join(c.text for c in chunks if c.block_type == "editorial")


_PAGE = (
    "21. EMPEDOKLES,.\n"
    "B. FRAGMENTE.\n"
    "98. [215 K.] Simpl. phys. 32,3 ἡ δὲ Χθὼν τούτοισιν ἴση συνέκυρσε μάλιστα,\n"
    "5 ἐκ τῶν αἷμά τε γέντο καὶ ἄλλης εἴδεα σαρκός.\n"
    "98. Nachdem aber die Erde vor Anker gegangen, begegneten sie diesen.\n"
    "4 εὐστέρνοις Arist., Simpl. phys. D: εὐτύκτοις Simpl. phys. EF\n"
    "Νήστιδος] vgl. B 6,3 Karsten\n"
    "Aufl. und Hss. übereinstimmend nach Wilamowitz\n"
    "Diels, Fragm. d. Vorsokr. I. 3. Aufl. 17\n"
    "17*\n"
    "258 21. EMPEDOKLES.\n"
    "10 εὖτε μὲν αὐλοῦ πορθμὸν ἐπ᾽ εὐειδεῖ χερὶ θεῖσα\n"
    "15 πνεύματος ἐλλείποντος ἐσέρχεται αἴσιμον ὕδωρ.\n"
    "aus glänzendem Erze spielt. Solange es die Mündung des Halses hält.\n"
    "κλεψύδραις wenige Hss. (Simpl. de caelo 524, 10). Über die Sache vgl. Photiadis\n"
)


class TestLineNumbersVersusApparatus:
    def test_numbered_verse_line_is_kept(self, tmp_path: Path) -> None:
        # #680: `5 ἐκ τῶν …` is verse 5 of B 98, not apparatus.
        text = _body(_parse(tmp_path, _PAGE), "31 B 98", "grc")
        assert "ἐκ τῶν αἷμά τε γέντο" in text

    def test_numbered_verse_line_loses_its_margin_number(self, tmp_path: Path) -> None:
        text = _body(_parse(tmp_path, _PAGE), "31 B 98", "grc")
        assert "μάλιστα, ἐκ τῶν" in text

    def test_numbered_verse_after_page_break_is_kept(self, tmp_path: Path) -> None:
        text = _body(_parse(tmp_path, _PAGE), "31 B 98", "grc")
        assert "εὖτε μὲν αὐλοῦ" in text
        assert "πνεύματος ἐλλείποντος" in text

    def test_numbered_apparatus_line_is_not_text(self, tmp_path: Path) -> None:
        # Carries an apparatus signature (`D:`), so it stays apparatus
        # even though it follows German directly.
        text = _body(_parse(tmp_path, _PAGE), "31 B 98", "grc")
        assert "εὐστέρνοις" not in text

    def test_apparatus_continuation_with_greek_is_not_text(self, tmp_path: Path) -> None:
        # #673: unnumbered, Greek-bearing, so content routing used to
        # send it to the last Greek fragment.
        text = _body(_parse(tmp_path, _PAGE), "31 B 98", "grc")
        assert "Νήστιδος" not in text

    def test_apparatus_continuation_without_greek_is_not_german_text(self, tmp_path: Path) -> None:
        text = _body(_parse(tmp_path, _PAGE), "31 B 98", "deu")
        assert "Wilamowitz" not in text

    def test_page_footer_is_not_german_text(self, tmp_path: Path) -> None:
        text = _body(_parse(tmp_path, _PAGE), "31 B 98", "deu")
        assert "Vorsokr" not in text
        assert "17*" not in text

    def test_german_resuming_after_page_break_is_kept(self, tmp_path: Path) -> None:
        # The page opens with Greek verse, then the German translation
        # carries on. The German must not be dropped for following Greek.
        text = _body(_parse(tmp_path, _PAGE), "31 B 98", "deu")
        assert "aus glänzendem Erze spielt" in text

    def test_greek_after_german_on_the_same_page_is_apparatus(self, tmp_path: Path) -> None:
        # Page layout is Greek, then German, then apparatus. Greek that
        # follows the German before the next page break is apparatus.
        text = _body(_parse(tmp_path, _PAGE), "31 B 98", "grc")
        assert "κλεψύδραις" not in text

    def test_apparatus_is_kept_as_editorial_chunks(self, tmp_path: Path) -> None:
        chunks = _parse(tmp_path, _PAGE)
        ed = [c for c in chunks if c.block_type == "editorial"]
        assert ed, "apparatus should be kept, typed editorial"
        assert {c.section for c in ed} == {"31 B 98"}
        assert {c.lang for c in ed} == {"grc"}
        joined = _editorial(chunks)
        for piece in ("εὐστέρνοις", "Νήστιδος", "Wilamowitz", "κλεψύδραις"):
            assert piece in joined

    def test_editorial_chunk_ids_are_distinct_from_body(self, tmp_path: Path) -> None:
        chunks = _parse(tmp_path, _PAGE)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))


# A verbatim excerpt of the 1912 OCR (Empedocles B 96–103, pp. 257–260),
# so this runs in CI, where `data/` is absent.
_EXCERPT = Path(__file__).parent / "fixtures" / "presocratic_empedocles_b96_b103.txt"


@pytest.fixture(scope="module")
def chunks() -> list:
    return list(presocratic.parse_file(_EXCERPT))


class TestEmpedoclesExcerpt:
    def test_numbered_verse_of_b98_present(self, chunks) -> None:
        assert "ἐκ τῶν αἷμά τε γέντο" in _body(chunks, "31 B 98", "grc")
        # `1 δὲ Χθὼν …` too: the verse counter prints 1 as well as fives.
        assert "δὲ Χθὼν τούτοισιν" in _body(chunks, "31 B 98", "grc")

    @pytest.mark.parametrize(
        "verse",
        ["εὖτε μὲν αὐλοῦ", "πνεύματος ἐλλείποντος", "εἰσόκε χειρὶ μεθῆι", "αἰθέρος εὐθὺς ῥεῦμα"],
    )
    def test_b100_verses_after_page_breaks_are_greek_text(self, chunks, verse) -> None:
        greek = " ".join(c.text for c in chunks if c.lang == "grc" and c.block_type is None)
        assert verse in greek

    @pytest.mark.xfail(
        strict=True,
        reason="#681: `99. Das Ohr … (Ὁ) Töne` reads as a Greek opener and "
        "moves last_greek_frag back to 99, so B 100's resumed verse lands in B 99",
    )
    def test_b100_verses_land_in_b100(self, chunks) -> None:
        assert "εὖτε μὲν αὐλοῦ" in _body(chunks, "31 B 100", "grc")

    @pytest.mark.parametrize("section", ["31 B 98", "31 B 99", "31 B 100", "31 B 103"])
    def test_no_apparatus_in_greek(self, chunks, section) -> None:
        text = _body(chunks, section, "grc")
        for sig in ("Hss.", "κλεψύδραις wenige", "εὐστέρνοις", "Steinhart"):
            assert sig not in text

    def test_german_of_b100_resumes_across_both_page_breaks(self, chunks) -> None:
        text = _body(chunks, "31 B 100", "deu")
        assert "aus glänzendem Erze" in text
        assert "Innern abströmt" in text

    def test_no_page_chrome_in_german(self, chunks) -> None:
        for c in chunks:
            if c.lang == "deu":
                assert "Vorsokr" not in c.text
                assert "17*" not in c.text

    def test_footer_spawns_no_phantom_fragment(self, chunks) -> None:
        # ` 3. Aufl.` in the footer used to split off a German `31 B 3`.
        assert not [c for c in chunks if c.section == "31 B 3"]

    def test_apparatus_kept_as_editorial(self, chunks) -> None:
        joined = _editorial(chunks)
        assert "κλεψύδραις wenige Hss." in joined
        assert "πνοῆς Hss." in joined


def _one_page(*lines: str) -> str:
    return "21. EMPEDOKLES,.\nB. FRAGMENTE.\n" + "".join(line + "\n" for line in lines)


_GREEK_OPENER = "98. [215 K.] Simpl. phys. 32,3 ἡ δὲ Χθὼν τούτοισιν ἴση συνέκυρσε μάλιστα,"
_GERMAN_OPENER = "98. Nachdem aber die Erde vor Anker gegangen, begegneten sie diesen."
_NUMBERED_APPARATUS = "4 εὐστέρνοις Arist., Simpl. phys. D: εὐτύκτοις Simpl. phys. EF"
# Running Greek, no Latin script: text however it is reached.
_PLAIN_GREEK = "περιχωρήσει ἐπὶ πλέον. καὶ τὰ συμμισγόμενά τε καὶ ἀποκρινόμενα πάντα ἔγνω νοῦς."


class TestPageBreaks:
    @pytest.mark.parametrize(
        "head",
        [
            "B. FRAGMENTE. 99—100. 259",
            "B, FRAGMENTE. 6—7. 429",
            "Β. FRAGMENTE. 11—13. 405",
            "B. FR. 18—19. ZWEIFELH. 20. 165",
            "258 21. EMPEDOKLES.",
            "21. EMPEDOKLES.",
            "259",
        ],
    )
    def test_page_break_ends_the_apparatus(self, tmp_path: Path, head: str) -> None:
        # Greek resuming after the break is text again, and it is only
        # recognisable as text by the break: it carries a Latin siglum.
        src = _one_page(
            _GREEK_OPENER, _GERMAN_OPENER, _NUMBERED_APPARATUS, head, "ἀλλ᾽ ἄγε μύθων κλῦθι Stein"
        )
        assert "μύθων κλῦθι" in _body(_parse(tmp_path, src), "31 B 98", "grc")

    def test_heading_is_skipped(self, tmp_path: Path) -> None:
        src = _one_page(_GREEK_OPENER, _GERMAN_OPENER, "GEFÄLSCHTE FRAGMENTE.")
        assert "GEFÄLSCHTE" not in _body(_parse(tmp_path, src), "31 B 98", "deu")


class TestLeavingTheApparatus:
    def test_plain_greek_resumes_the_text_after_a_missed_page_break(self, tmp_path: Path) -> None:
        src = _one_page(_GREEK_OPENER, _GERMAN_OPENER, _NUMBERED_APPARATUS, _PLAIN_GREEK)
        assert "περιχωρήσει" in _body(_parse(tmp_path, src), "31 B 98", "grc")

    def test_numbered_plain_greek_resumes_the_text(self, tmp_path: Path) -> None:
        src = _one_page(_GREEK_OPENER, _GERMAN_OPENER, _NUMBERED_APPARATUS, "15 " + _PLAIN_GREEK)
        assert "περιχωρήσει" in _body(_parse(tmp_path, src), "31 B 98", "grc")

    def test_opener_with_ocr_comma_resumes_the_text(self, tmp_path: Path) -> None:
        # `80, [62] …` (Heraclitus B 80) is an opener the classifier misses.
        line = "80, [62] Oric. c. Cels. vi 42 Koetschau εἰδέναι δὲ χρὴ τὸν πόλεμον ἐόντα ξυνόν"
        src = _one_page(_GREEK_OPENER, _GERMAN_OPENER, _NUMBERED_APPARATUS, line)
        assert "πόλεμον ἐόντα" in _body(_parse(tmp_path, src), "31 B 98", "grc")

    def test_crammed_opener_ends_the_apparatus(self, tmp_path: Path) -> None:
        line = "ἐκπνεῖ Hss. 19 κέρματα 99. [p. 483 K.] Theophr. de sens. 9 κώδων. σάρκινος ὄζος."
        chunks = _parse(
            tmp_path, _one_page(_GREEK_OPENER, _GERMAN_OPENER, _NUMBERED_APPARATUS, line)
        )
        assert "σάρκινος ὄζος" in _body(chunks, "31 B 99", "grc")
        assert "ἐκπνεῖ Hss." in _editorial(chunks)
        assert "ἐκπνεῖ" not in _body(chunks, "31 B 98", "grc")

    def test_stray_greek_letter_is_not_greek_below_the_german(self, tmp_path: Path) -> None:
        # `ΟἹ,` is OCR for 61: the line is German, not apparatus. (Content
        # routing still files it by its Greek letter, which is #681.)
        src = _one_page(
            _GREEK_OPENER, _GERMAN_OPENER, "ΟἹ, Meerwasser ist das reinste und scheußlichste."
        )
        assert "Meerwasser" not in _editorial(_parse(tmp_path, src))


class TestApparatusWithoutAFragment:
    def test_apparatus_before_any_fragment_is_dropped(self, tmp_path: Path) -> None:
        chunks = _parse(
            tmp_path, _one_page(_NUMBERED_APPARATUS, "Νήστιδος vgl. B 6", _GREEK_OPENER)
        )
        assert not _editorial(chunks)
        assert "Νήστιδος" not in _body(chunks, "31 B 98", "grc")


class TestNumberedLinesInText:
    def test_garbled_line_number_is_still_verse(self, tmp_path: Path) -> None:
        # `16` for 15: the number is no guide, the content is.
        src = _one_page(_GREEK_OPENER, "16 καὶ ἦν ἐν τῶι παντί.")
        assert "καὶ ἦν ἐν τῶι παντί" in _body(_parse(tmp_path, src), "31 B 98", "grc")

    def test_diels_bracketed_insertion_is_not_a_lemma_bracket(self, tmp_path: Path) -> None:
        src = _one_page(
            _GREEK_OPENER, "5 καὶ ἀλλαχοῦ δὲ οὕτως φησί [Β 6]. καὶ τοῦτο δὲ ὁ Α. ἀξιοῖ."
        )
        assert "ἀλλαχοῦ" in _body(_parse(tmp_path, src), "31 B 98", "grc")

    def test_stray_ocr_signature_in_running_greek_is_still_verse(self, tmp_path: Path) -> None:
        line = "10 ἥ τε σεμνότης αὕτη καὶ ἡ προσποίητος πίστις καὶ ἡ ἀπάθεια, εἴ τις περιστήσειεν] φόβον"
        assert "σεμνότης" in _body(
            _parse(tmp_path, _one_page(_GREEK_OPENER, line)), "31 B 98", "grc"
        )

    def test_german_note_quoting_greek_is_not_verse(self, tmp_path: Path) -> None:
        line = "8 Die Emendation des Namens gab der lat. Übersetzer, doch bleibt ππ unsicher"
        chunks = _parse(tmp_path, _one_page(_GREEK_OPENER, line))
        assert "Emendation" not in _body(chunks, "31 B 98", "grc")

    def test_numbered_latin_testimony_is_skipped_without_opening_the_apparatus(
        self, tmp_path: Path
    ) -> None:
        # The German resuming below it must not be swallowed as apparatus.
        src = _one_page(
            _GREEK_OPENER,
            _GERMAN_OPENER,
            "259",
            "ἀλλ᾽ ἄγε μύθων κλῦθι",
            "20 discipulus Asclepiadis libro primo De semine dixit libro physico: etenim",
            "die Seele ein und dasselbe, nämlich Luft, die zwar wärmer ist als die äußere.",
        )
        chunks = _parse(tmp_path, src)
        assert "die Seele ein und dasselbe" in _body(chunks, "31 B 98", "deu")
        assert "discipulus" not in _editorial(chunks)

    def test_numbered_latin_greek_testimony_is_skipped(self, tmp_path: Path) -> None:
        line = "20 causam erroris fuisse, quia in Empedocli carmine versus hic invenitur δειλοί"
        chunks = _parse(tmp_path, _one_page(_GREEK_OPENER, line))
        assert "causam" not in _body(chunks, "31 B 98", "grc")
        assert not _editorial(chunks)

    def test_numbered_apparatus_right_after_greek_opens_the_apparatus(self, tmp_path: Path) -> None:
        chunks = _parse(
            tmp_path, _one_page(_GREEK_OPENER, _NUMBERED_APPARATUS, "Νήστιδος vgl. B 6")
        )
        assert "Νήστιδος" in _editorial(chunks)
        assert "Νήστιδος" not in _body(chunks, "31 B 98", "grc")


class TestGermanResumingAtPageTop:
    def _page_top(self, tmp_path: Path, *lines: str) -> list:
        src = _one_page(_GREEK_OPENER, _GERMAN_OPENER, "259", "ἀλλ᾽ ἄγε μύθων κλῦθι", *lines)
        return _parse(tmp_path, src)

    def test_latin_citation_after_greek_stays_out_of_the_german(self, tmp_path: Path) -> None:
        chunks = self._page_top(tmp_path, "Theophr. p. 5. 7. ed. Paris. 1836")
        assert "Theophr" not in _body(chunks, "31 B 98", "deu")

    def test_ocr_german_words_in_latin_do_not_make_it_german(self, tmp_path: Path) -> None:
        # `sic` read as `sie`, `in` as `im`.
        line = "ita vitalis calor sie procedens im omnibus quae vivunt et est in medio telae"
        chunks = self._page_top(tmp_path, line)
        assert "vitalis" not in _body(chunks, "31 B 98", "deu")

    def test_line_starting_like_an_opener_does_not_resume(self, tmp_path: Path) -> None:
        # `48,` is OCR for 43: another fragment, not 98 carrying on.
        chunks = self._page_top(
            tmp_path, "48, Sobald das Sonnenlicht den Kreis des Mondes getroffen, kehrt es zurück."
        )
        assert "Sonnenlicht" not in _body(chunks, "31 B 98", "deu")

    def test_resumed_german_splits_at_a_crammed_opener(self, tmp_path: Path) -> None:
        line = "teter Kehrichthaufen, und es ist so. 99. Auch der Gerstentrank zersetzt sich, wenn man ihn nicht umrührt."
        chunks = self._page_top(tmp_path, line)
        assert "Kehrichthaufen" in _body(chunks, "31 B 98", "deu")
        assert "Gerstentrank" in _body(chunks, "31 B 99", "deu")

    def test_no_resume_after_a_german_opener_on_the_page(self, tmp_path: Path) -> None:
        src = _one_page(
            _GREEK_OPENER,
            "259",
            "97. Die Wirbelsäule hat ihre Form daher.",
            "ἀλλ᾽ ἄγε μύθων κλῦθι",
            "und es ist nicht so, wie die Menschen meinen.",
        )
        assert "Menschen meinen" not in _body(_parse(tmp_path, src), "31 B 97", "deu")

    def test_margin_column_of_fragment_numbers_blocks_resuming(self, tmp_path: Path) -> None:
        # The OCR moved the page's openers into a margin column: the German
        # below has lost its numbers, and is not 98 carrying on.
        src = _one_page(
            _GREEK_OPENER,
            _GERMAN_OPENER,
            "19.",
            "20.",
            "259",
            "ἀλλ᾽ ἄγε μύθων κλῦθι",
            "Leute, die weder zu hören noch zu reden verstehen.",
        )
        assert "Leute" not in _body(_parse(tmp_path, src), "31 B 98", "deu")
