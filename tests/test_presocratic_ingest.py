"""Ingest tests for the Diels pre-Socratic OCR text.

Two surfaces:

* **Synthetic fixture tests** — hand-built mini-source covering the
  parser's discrimination edge cases (chapter heading vs. A-fragment,
  Greek-vs-German fragment, apparatus rejection, print-line-number
  prefix stripping, OCR'd integer in chapter heading).

* **Real-file integration test** — skipped when the OCR file isn't
  available locally. Confirms counts + locator format for Heraclitus
  using the archive.org download at `data/presocratic/` (gitignored, so
  this skips in CI).

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
    reason="archive.org Vorsokratiker OCR file not present under data/presocratic/",
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

    def test_b100_verses_land_in_b100(self, chunks) -> None:
        # #681: `99. Das Ohr … (Ὁ) Töne` read as a Greek opener and moved
        # the Greek back to 99, so B 100's resumed verse landed in B 99.
        assert "εὖτε μὲν αὐλοῦ" in _body(chunks, "31 B 100", "grc")
        assert "εὖτε μὲν αὐλοῦ" not in _body(chunks, "31 B 99", "grc")

    def test_german_opener_with_a_stray_greek_letter_is_german(self, chunks) -> None:
        assert _body(chunks, "31 B 99", "deu").startswith("Das Ohr ist gleichsam")
        assert "Das Ohr" not in _body(chunks, "31 B 99", "grc")

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
        # `80, [62] …` (Heraclitus B 80): a comma for the full stop. Out of
        # sequence after 98, it is taken for the next fragment (#681).
        line = "80, [62] Oric. c. Cels. vi 42 Koetschau εἰδέναι δὲ χρὴ τὸν πόλεμον ἐόντα ξυνόν"
        chunks = _parse(
            tmp_path, _one_page(_GREEK_OPENER, _GERMAN_OPENER, _NUMBERED_APPARATUS, line)
        )
        assert "πόλεμον ἐόντα" in _body(chunks, "31 B 99", "grc")
        assert "πόλεμον" not in _editorial(chunks)

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


# ════════════════════════════════════════════════════════════════════
# Fragment openers the classifier misread (#681)
# ════════════════════════════════════════════════════════════════════


def _heraclitus_page(*lines: str) -> str:
    return "12. HERAKLEITOS.\nB. FRAGMENTE.\n" + "".join(line + "\n" for line in lines)


def _sections(chunks: list, lang: str) -> list[str]:
    return [c.section for c in chunks if c.lang == lang and c.block_type != "editorial"]


class TestGermanOpenersWithStrayGreek:
    @pytest.mark.parametrize(
        ("line", "section"),
        [
            ("64. Das Weltall aber steuert der Blitz, ὦ. h. er lenkt es.", "22 B 64"),
            ("25. Denn was man sagen muß, darf man auch zweimal sagen. τ΄", "22 B 25"),
            ("72. Wie die hohen Bäume und die Fische in der βαϊχῆαύ..", "22 B 72"),
            # No German function word at all: its first word carries it.
            ("148. Menschenumgebenden Erdstoff (d. ἡ. Körper).", "22 B 148"),
            ("22. Wunderbar schwer zu überzeugen (= Plato Parm. 135 ΑἹ.", "22 B 22"),
        ],
    )
    def test_is_german(self, tmp_path: Path, line: str, section: str) -> None:
        chunks = _parse(tmp_path, _heraclitus_page(line))
        assert _sections(chunks, "deu") == [section]
        assert _sections(chunks, "grc") == []

    def test_does_not_move_the_greek_back(self, tmp_path: Path) -> None:
        src = _heraclitus_page(
            "63. [123] Hippol. ix 10 λέγει δὲ καὶ σαρκὸς ἀνάστασιν ταύτης",
            "65. [24] — — ὅλων αἴτιον καλεῖ δὲ αὐτὸ χρησμοσύνην καὶ κόρον",
            "64. Das Weltall aber steuert der Blitz, ὦ. h. er lenkt es.",
            "259",
            "ἡ δὲ διακόσμησις κατ᾽ αὐτὸν ἐκπύρωσις",
        )
        assert "διακόσμησις" in _body(_parse(tmp_path, src), "22 B 65", "grc")

    def test_latin_citation_with_little_greek_is_still_a_greek_opener(self, tmp_path: Path) -> None:
        # An abbreviated source, not a German word: the Greek follows.
        line = "10. Ausust. de οἷν. ἃ, vııı 2 (D. 174) Anaxagorae successit auditor eius"
        assert _sections(_parse(tmp_path, _heraclitus_page(line)), "grc") == ["22 B 10"]

    def test_quote_before_the_capital_opens_german(self, tmp_path: Path) -> None:
        chunks = _parse(tmp_path, _heraclitus_page("152. “Der Abend, des Tages Greisenalter."))
        assert _body(chunks, "22 B 152", "deu").startswith("“Der Abend")

    def test_stray_greek_letter_in_german_continuation_is_german(self, tmp_path: Path) -> None:
        # `ΟἹ,` is OCR for 61: German, whatever its first two letters.
        src = _one_page(
            _GREEK_OPENER, _GERMAN_OPENER, "ΟἹ, Meerwasser ist das reinste und scheußlichste."
        )
        chunks = _parse(tmp_path, src)
        assert "Meerwasser" in _body(chunks, "31 B 98", "deu")
        assert "Meerwasser" not in _body(chunks, "31 B 98", "grc")


class TestCommaOpeners:
    def test_greek_comma_opener_with_a_bracket(self, tmp_path: Path) -> None:
        src = _heraclitus_page(
            "79. [97] — — ἀνὴρ νήπιος ἤκουσε πρὸς δαίμονος",
            "80, [62] Oric. c. Cels. vi 42 εἰδέναι δὲ χρὴ τὸν πόλεμον ἐόντα ξυνόν",
        )
        chunks = _parse(tmp_path, src)
        assert "πόλεμον" in _body(chunks, "22 B 80", "grc")
        assert "πόλεμον" not in _body(chunks, "22 B 79", "grc")

    def test_german_comma_opener_in_sequence(self, tmp_path: Path) -> None:
        src = _heraclitus_page(
            "31. Des Feuers Wandlungen: erstens Meer.",
            "32, Eins, das allein Weise, will nicht und will doch auch.",
        )
        chunks = _parse(tmp_path, src)
        assert _body(chunks, "22 B 32", "deu").startswith("Eins, das allein Weise")
        assert "Eins" not in _body(chunks, "22 B 31", "deu")

    def test_misread_number_out_of_sequence_is_the_next_fragment(self, tmp_path: Path) -> None:
        # `48,` is OCR for 43: between 42 and 44, never B 48.
        src = _one_page(
            "42. Der Mond deckt ihr die Strahlen ab.",
            "48, Sobald das Sonnenlicht den weiten Kreis des Mondes getroffen.",
            "44. Das Sonnenlicht strahlt dem Olympos entgegen.",
        )
        chunks = _parse(tmp_path, src)
        assert _sections(chunks, "deu") == ["31 B 42", "31 B 43", "31 B 44"]
        assert _body(chunks, "31 B 43", "deu").startswith("Sobald")

    def test_out_of_sequence_number_already_taken_is_not_an_opener(self, tmp_path: Path) -> None:
        src = _one_page(
            "42. Der Mond deckt ihr die Strahlen ab.",
            "43. Sobald das Sonnenlicht den Kreis getroffen.",
            "42. Zweite Lesung.",
            "48, Und kehrt sofort zurück.",
        )
        chunks = _parse(tmp_path, src)
        assert "31 B 48" not in _sections(chunks, "deu")
        assert "Und kehrt" in _body(chunks, "31 B 42", "deu")

    def test_comma_opener_needs_a_bracket_a_source_or_german(self, tmp_path: Path) -> None:
        src = _heraclitus_page(
            "23. [60] — — Δίκης ὄνομα οὐκ ἂν ἤιδεσαν.",
            "24, Τελχῖνες τούτους οἱ μὲν θαλάσσης παῖδάς φασι",
        )
        chunks = _parse(tmp_path, src)
        assert _sections(chunks, "grc") == ["22 B 23"]
        assert "Τελχῖνες" in _body(chunks, "22 B 23", "grc")

    def test_comma_opener_citing_a_source_in_capitals(self, tmp_path: Path) -> None:
        # `94,` is OCR for 24 (Parmenides B 24, Suetonius).
        src = _heraclitus_page(
            "23. [60] — — Δίκης ὄνομα οὐκ ἂν ἤιδεσαν.",
            "94, SUETONIUS (Miller Mel. 417) Τελχῖνες τούτους οἱ μὲν θαλάσσης",
        )
        assert "Τελχῖνες" in _body(_parse(tmp_path, src), "22 B 24", "grc")


class TestAFragments:
    def test_degree_sign_marks_an_a_fragment(self, tmp_path: Path) -> None:
        src = _heraclitus_page(
            "125. [84] Theophr. de vert. 9 καὶ ὁ κυκεὼν διίσταται κινούμενος.",
            "125°. [0] Tzetz. ad Aristoph. τυφλὸν δὲ τὸν Πλοῦτον ποιεῖ",
            "125. Auch der Gerstentrank zersetzt sich. 125°. Möge es euch nie an Reichtum fehlen.",
        )
        chunks = _parse(tmp_path, src)
        assert _sections(chunks, "grc") == ["22 B 125", "22 B 125a"]
        assert _sections(chunks, "deu") == ["22 B 125", "22 B 125a"]
        assert "Πλοῦτον" not in _body(chunks, "22 B 125", "grc")
        assert _body(chunks, "22 B 125a", "deu").startswith("Möge")

    def test_second_a_mark_is_the_b_fragment(self, tmp_path: Path) -> None:
        src = _heraclitus_page(
            "126. Das Kalte erwärmt sich.",
            "126°. Nach dem Gesetze der Zeiten aber wird die Siebenzahl gerechnet.",
            "126°. Stets wächst das eine so, das andere so.",
        )
        chunks = _parse(tmp_path, src)
        assert _sections(chunks, "deu") == ["22 B 126", "22 B 126a", "22 B 126b"]

    @pytest.mark.parametrize(
        ("opener", "section"),
        [
            ("675, [0] Hisdosus ad Chalcid. ita vitalis calor a sole procedens", "22 B 67a"),
            ("672. [0] Anatol. de decade κατὰ λόγον δὲ ὡρέων συμβάλλεται", "22 B 67a"),
            ("67a, [0] Plut. c. princip. ὁ μὲν γὰρ εἰς ἀρετὴν", "22 B 67a"),
            ("67b, [0] — — τίνες οὖν ὕστερον τοῦτ᾽ ἔγνωσαν", "22 B 67b"),
        ],
    )
    def test_ocr_forms_of_the_suffix(self, tmp_path: Path, opener: str, section: str) -> None:
        src = _heraclitus_page("67. [36] — — ὁ θεὸς ἡμέρη εὐφρόνη, χειμὼν θέρος", opener)
        assert section in _sections(_parse(tmp_path, src), "grc")

    @pytest.mark.parametrize(
        "line",
        [
            # Not 196a after 126, nor anything else: no opener at all.
            "1960, [0] Anonym. in Plat. Theaet. ἄλλα τε τινα εἴρηκεν",
            "1422. [0] Anonym. in Plat. Theaet. ἄλλα τε τινα εἴρηκεν",
            "1262°. [0] Anonym. in Plat. Theaet. ἄλλα τε τινα εἴρηκεν",
        ],
    )
    def test_digit_suffix_needs_the_base_fragment_just_before(
        self, tmp_path: Path, line: str
    ) -> None:
        src = _heraclitus_page("126. [39] — ad exeg. τὰ ψυχρὰ θέρεται, θερμὸν ψύχεται", line)
        chunks = _parse(tmp_path, src)
        assert _sections(chunks, "grc") == ["22 B 126"]
        assert "εἴρηκεν" in _body(chunks, "22 B 126", "grc")

    def test_three_digit_number_in_sequence_is_not_a_suffix(self, tmp_path: Path) -> None:
        src = _heraclitus_page(
            "101. [80] Plut. adv. Colot. ἐδιζησάμην ἐμεωυτόν",
            "102. [61] Porphyr. τῶι μὲν θεῶι καλὰ πάντα",
        )
        assert _sections(_parse(tmp_path, src), "grc") == ["22 B 101", "22 B 102"]

    def test_line_number_before_an_a_fragment_is_stripped(self, tmp_path: Path) -> None:
        src = _heraclitus_page(
            "101. [80] Plut. adv. Colot. ἐδιζησάμην ἐμεωυτόν",
            "15 101%. [15] Polyb. xii 27 δυεῖν γὰρ ὄντων κατὰ φύσιν ὡσανεί τινων ὀργάνων",
        )
        assert "22 B 101a" in _sections(_parse(tmp_path, src), "grc")

    def test_crammed_greek_b_and_c_fragments(self, tmp_path: Path) -> None:
        # `154°.` after 154a and 154b is 154c.
        src = _heraclitus_page(
            "154. [0] Plut. de esu carn. ἢ τοῖς μὲν πρώτοις",
            "1542, [0] Plut. de esu carn. ii 1 καὶ πέποται ὁ τῆς συνηθείας",
            "κυκεών, ὥσπερ ὁ τῆς Κίρκης γόους τε 154b, [0] --- — τίνες οὖν ὕστερον τοῦτ᾽ "
            "ἔγνωσαν 154°. [0] Suidas s. v. αὐτίκα. καὶ παροιμία",
        )
        chunks = _parse(tmp_path, src)
        assert _sections(chunks, "grc") == ["22 B 154", "22 B 154a", "22 B 154b", "22 B 154c"]
        assert "τίνες οὖν" in _body(chunks, "22 B 154b", "grc")
        assert "παροιμία" in _body(chunks, "22 B 154c", "grc")


class TestNumberlessOpeners:
    def test_ditto_openers_take_the_next_numbers(self, tmp_path: Path) -> None:
        src = _heraclitus_page(
            "18. [7) — — 1117 (u 121, 24) ἐὰν μὴ ἔλπηται, ἀνέλπιστον οὐκ ἐξευρήσει",
            "[6] Clem. Strom. ii 24 ἀπίστους εἶναί τινας ἐπιστύφων φησιν ἀκοῦσαι",
            "[86] — — iii 14 (ii 201, 28) γενόμενοι ζώειν ἐθέλουσι μόρους τ᾽ ἔχειν",
            "[64] — — — 21 (u 205,7) θάνατός ἐστιν ὁκόσα ἐγερθέντες ὁρέομεν",
        )
        chunks = _parse(tmp_path, src)
        assert _sections(chunks, "grc") == ["22 B 18", "22 B 19", "22 B 20", "22 B 21"]
        assert "ἐγερθέντες" in _body(chunks, "22 B 21", "grc")

    def test_ditto_opener_before_any_fragment_is_not_numbered(self, tmp_path: Path) -> None:
        src = _heraclitus_page("[86] — — iii 14 (ii 201, 28) γενόμενοι ζώειν ἐθέλουσι")
        assert _sections(_parse(tmp_path, src), "grc") == []


class TestOpenersCitingAnAuthorInCapitals:
    def test_unknown_uppercase_name_with_text_after_is_an_opener(self, tmp_path: Path) -> None:
        # `3. OLYMPIODOR. …` matched the chapter-heading regex and was dropped.
        src = (
            "3. ANAXIMENES.\nB. FRAGMENTE.\n"
            "2. Aet. i 3,4 οἷον ἡ ψυχή, φησίν, ἡ ἡμετέρα ἀὴρ οὖσα συγκρατεῖ ἡμᾶς\n"
            "3. OLYMPIODOR. de arte sacra c. 25 μίαν δὲ κινουμένην ἄπειρον ἀρχήν\n"
        )
        chunks = _parse(tmp_path, src)
        assert "κινουμένην" in _body(chunks, "13 B 3", "grc")
        assert "κινουμένην" not in _body(chunks, "13 B 2", "grc")

    def test_bare_unknown_heading_is_still_not_an_opener(self, tmp_path: Path) -> None:
        src = _one_page(_GERMAN_OPENER, "47. ARCHELAOS.")
        assert _sections(_parse(tmp_path, src), "deu") == ["31 B 98"]


_HERACLITUS_B14_B30 = Path(__file__).parent / "fixtures" / "presocratic_heraclitus_b14_b30.txt"


@pytest.fixture(scope="module")
def heraclitus_b14_b30() -> list:
    return list(presocratic.parse_file(_HERACLITUS_B14_B30))


class TestHeraclitusDittoPage:
    """Verbatim OCR of pp. 81–84, where B 19–25 lost their numbers."""

    def test_numberless_fragments_are_split_out_of_b18(self, heraclitus_b14_b30) -> None:
        chunks = heraclitus_b14_b30
        assert _sections(chunks, "grc") == [f"22 B {n}" for n in range(14, 32)]
        assert "ἀκοῦσαι οὐκ ἐπιστάμενοι" in _body(chunks, "22 B 19", "grc")
        assert "μόροι γὰρ μέζονες" in _body(chunks, "22 B 25", "grc")
        assert "ἀκοῦσαι" not in _body(chunks, "22 B 18", "grc")

    def test_german_comma_opener(self, heraclitus_b14_b30) -> None:
        assert _body(heraclitus_b14_b30, "22 B 29", "deu").startswith("Eins gibt es")


# ════════════════════════════════════════════════════════════════════
# DK's doubtful, false and forged fragments (#683)
# ════════════════════════════════════════════════════════════════════
#
# Kept, but typed `spurious`: not the author's words, so the lemmatizer,
# the concordance and retrieval treat them as they treat apparatus.


def _fragment(chunks: list, section: str, lang: str):
    """The one non-editorial chunk for section/lang, of whatever type."""

    (c,) = [
        c for c in chunks if c.section == section and c.lang == lang and c.block_type != "editorial"
    ]
    return c


def _types(chunks: list, lang: str) -> dict[str, str | None]:
    return {
        c.section: c.block_type for c in chunks if c.lang == lang and c.block_type != "editorial"
    }


_DOUBTFUL_PAGE = (
    "40. [0] Herodian. π. μον. λέξ. ἡ δὲ πηγὴ σεσέληνε.",
    "41. [0] Etym. gen. σίλλος ὁ σιλλογράφος.",
    "{heading}",
    "42. [0] Herodian. π. μον. λέξεως καί κ᾽ ἐπιθυμήσειε νέος νῆς ἀμφιπόλοιο.",
    "40. Die Quelle ist ausgetrocknet.",
    "41. Grube.",
    "42. Da würde Lust bekommen ein Junger nach einer jungen Magd.",
)


class TestNonCanonicalSections:
    @pytest.mark.parametrize(
        "heading",
        [
            "ZWEIFELHAFTES.",
            "ZWEIFELHAFTE FRAGMENTE.",
            "ZWEIFELHAFTE, FALSCHE UND GEFÄLSCHTE FRAGMENTE.",
            "GEFÄLSCHTE FRAGMENTE.",
            "GEFÄLSCHTES.",
            "GEFALSCHTES.",
            "UNECHTES.",
            "UNECHTES,.",
            "FALSCHES.",
        ],
    )
    def test_fragments_after_a_heading_are_spurious(self, tmp_path: Path, heading: str) -> None:
        src = _heraclitus_page(*(line.format(heading=heading) for line in _DOUBTFUL_PAGE))
        chunks = _parse(tmp_path, src)
        expected = {"22 B 40": None, "22 B 41": None, "22 B 42": "spurious"}
        assert _types(chunks, "grc") == expected
        # The German carries no heading of its own: the number decides.
        assert _types(chunks, "deu") == expected

    def test_heading_is_not_text(self, tmp_path: Path) -> None:
        src = _heraclitus_page(*(line.format(heading="UNECHTES,.") for line in _DOUBTFUL_PAGE))
        chunks = _parse(tmp_path, src)
        assert all("UNECHTES" not in c.text for c in chunks)

    def test_heading_with_the_fragment_on_the_same_line(self, tmp_path: Path) -> None:
        src = _heraclitus_page(
            "153. Baubo = Bauch.",
            "ZWEIFELHAFTES. 154. Das war damals noch nicht die Zeit.",
            "UNECHTES. 155. Telauges, berühmter Sproß der Theano. 156. Den Arzt Pausanias.",
        )
        chunks = _parse(tmp_path, src)
        assert _types(chunks, "deu") == {
            "22 B 153": None,
            "22 B 154": "spurious",
            "22 B 155": "spurious",
            "22 B 156": "spurious",
        }
        assert _fragment(chunks, "22 B 154", "deu").text == "Das war damals noch nicht die Zeit."

    def test_heading_with_a_greek_opener_on_the_same_line(self, tmp_path: Path) -> None:
        src = _heraclitus_page(
            "41. [0] Etym. gen. σίλλος ὁ σιλλογράφος.",
            "ZWEIFELHAFTE FRAGMENTE. 42. HERODIAN. 1. μον. λέξεως καί κ᾽ ἐπιθυμήσειε νέος",
        )
        chunks = _parse(tmp_path, src)
        assert _types(chunks, "grc") == {"22 B 41": None, "22 B 42": "spurious"}
        assert "ἐπιθυμήσειε" in _fragment(chunks, "22 B 42", "grc").text

    def test_heading_after_the_fragment_on_the_same_line(self, tmp_path: Path) -> None:
        src = _heraclitus_page(
            "41. Grube. ZWEIFELHAFTE FRAGMENTE.",
            "42. Da würde Lust bekommen ein Junger nach einer jungen Magd.",
        )
        chunks = _parse(tmp_path, src)
        assert _types(chunks, "deu") == {"22 B 41": None, "22 B 42": "spurious"}
        assert _fragment(chunks, "22 B 41", "deu").text == "Grube."

    def test_a_margin_number_after_the_heading_is_nothing(self, tmp_path: Path) -> None:
        # `217` is Karsten's verse count, not a page: the German resumes.
        src = _heraclitus_page(
            "153. [0] Hesych. βαυβώ τιθήνη Δήμητρος.",
            "153. Baubo = Bauch.",
            "UNECHTES. 217",
            "und so heißt es auch bei den anderen.",
        )
        chunks = _parse(tmp_path, src)
        assert _fragment(chunks, "22 B 153", "deu").text.endswith("den anderen.")

    def test_running_head_does_not_end_the_section(self, tmp_path: Path) -> None:
        # The old `doubtful` state was cleared by the next page's running
        # head, a B-marker, so it never reached past a page.
        src = _heraclitus_page(
            "19. [0] Simpl. cael. 558, 8 οὕτω τοι κατὰ δόξαν ἔφυ τάδε",
            "ZWEIFELHAFTES.",
            "20. [0] Hippol. Ref. v 8 αὐτὰρ ὑπ᾽ αὐτήν ἐστιν ἀταρπιτὸς ὀκρυόεσσα",
            "B. FR. 18—19. ZWEIFELH. 20. UNECHTES. 21—25. 19. ZENON. 165",
            "21. [0] Aet. ii 30, 4 περὶ ἐμφάσεως σελήνης ψευδοφανῆ τὸν ἀστέρα καλεῖ",
        )
        types = _types(_parse(tmp_path, src), "grc")
        assert types == {"22 B 19": None, "22 B 20": "spurious", "22 B 21": "spurious"}

    def test_next_chapter_is_canonical_again(self, tmp_path: Path) -> None:
        src = _heraclitus_page(
            "ZWEIFELHAFTES.",
            "20. [0] Hippol. Ref. v 8 αὐτὰρ ὑπ᾽ αὐτήν ἐστιν ἀταρπιτὸς ὀκρυόεσσα",
            "18. PARMENIDES.",
            "B. FRAGMENTE.",
            "20. [0] Hippol. Ref. v 8 αὐτὰρ ὑπ᾽ αὐτήν ἐστιν ἀταρπιτὸς ὀκρυόεσσα",
        )
        chunks = _parse(tmp_path, src)
        assert _fragment(chunks, "22 B 20", "grc").block_type == "spurious"
        assert _fragment(chunks, "28 B 20", "grc").block_type is None

    def test_misnumbered_fragment_before_the_heading_stays_canonical(self, tmp_path: Path) -> None:
        # `90.` is OCR for Xenophanes B 20: a number past the section's
        # first, but printed before its heading.
        src = _heraclitus_page(
            "90. [82 K.] — ii 111 ὡς δὲ Ξ. ὁ Κολοφώνιος ἀκηκοέναι φησί",
            "41. [0] Etym. gen. σίλλος ὁ σιλλογράφος.",
            "ZWEIFELHAFTES.",
            "42. [0] Herodian. π. μον. λέξεως καί κ᾽ ἐπιθυμήσειε νέος νῆς ἀμφιπόλοιο.",
        )
        types = _types(_parse(tmp_path, src), "grc")
        assert types == {"22 B 41": None, "22 B 42": "spurious", "22 B 90": None}

    def test_heading_before_the_fragments_is_ignored(self, tmp_path: Path) -> None:
        # Anaximander's testimonia have a ZWEIFELHAFTES of their own.
        src = "12. HERAKLEITOS.\nA. LEHRE.\nZWEIFELHAFTES.\nB. FRAGMENTE.\n" + (
            "1. [2] Sext. vii 132 τοῦ δὲ λόγου τοῦδ᾽ ἐόντος ἀεὶ ἀξύνετοι.\n"
        )
        assert _types(_parse(tmp_path, src), "grc") == {"22 B 1": None}

    def test_typing_leaves_the_chunk_id_alone(self, tmp_path: Path) -> None:
        # Typed in place, so embeddings and lemma state survive a re-ingest.
        plain = _parse(tmp_path, _heraclitus_page(*_DOUBTFUL_PAGE[:2], *_DOUBTFUL_PAGE[3:]))
        typed = _parse(
            tmp_path, _heraclitus_page(*(x.format(heading="UNECHTES.") for x in _DOUBTFUL_PAGE))
        )
        assert [c.chunk_id for c in plain] == [c.chunk_id for c in typed]
        assert {c.block_type for c in typed} == {None, "spurious"}


class TestLatinFragments:
    def test_latin_text_in_the_greek_column_is_kept(self, tmp_path: Path) -> None:
        src = _heraclitus_page(
            "18. [0] Cael. Aurel. Morb. chron. iv 9 Parmenides libris quos de natura",
            "femina virque simul Veneris cum germina miscent,",
            "nam si virtutes permixto semine pugnent",
            "18. Denn wenn Mann und Frau der Liebe Keime mischen.",
        )
        chunks = _parse(tmp_path, src)
        grc = _body(chunks, "22 B 18", "grc")
        assert "femina virque simul" in grc
        assert "nam si virtutes" in grc
        assert "femina" not in _body(chunks, "22 B 18", "deu")

    def test_a_source_citation_is_still_not_text(self, tmp_path: Path) -> None:
        src = _heraclitus_page(
            "18. [0] Theophr. de sens. 9 κώδων. σάρκινος ὄζος.", "Theophr. p. 5. 7. ed. Paris. 1836"
        )
        assert "Paris" not in _body(_parse(tmp_path, src), "22 B 18", "grc")

    def test_german_is_not_taken_for_latin(self, tmp_path: Path) -> None:
        src = _heraclitus_page(
            "18. [0] Theophr. de sens. 9 κώδων. σάρκινος ὄζος.",
            "259",
            "ἀλλ᾽ ἄγε μύθων κλῦθι",
            "und es ist nicht so, wie die Menschen in der Stadt meinen.",
        )
        assert "Menschen" not in _body(_parse(tmp_path, src), "22 B 18", "grc")


_PARMENIDES_B13_B25 = Path(__file__).parent / "fixtures" / "presocratic_parmenides_b13_b25.txt"
_HERACLITUS_B125_B139 = Path(__file__).parent / "fixtures" / "presocratic_heraclitus_b125_b139.txt"


@pytest.fixture(scope="module")
def parmenides_b13_b25() -> list:
    return list(presocratic.parse_file(_PARMENIDES_B13_B25))


@pytest.fixture(scope="module")
def heraclitus_b125_b139() -> list:
    return list(presocratic.parse_file(_HERACLITUS_B125_B139))


class TestParmenidesExcerpt:
    """Verbatim OCR of pp. 162–165: B 18 in Latin, B 20 doubtful, 21–25
    spurious."""

    def test_doubtful_and_spurious_are_typed(self, parmenides_b13_b25) -> None:
        for lang in ("grc", "deu"):
            types = _types(parmenides_b13_b25, lang)
            assert {s for s, t in types.items() if t == "spurious"} == {
                f"28 B {n}" for n in range(20, 26)
            } & set(types), lang
            assert types["28 B 19"] is None

    def test_b18_latin_verse_is_in_the_greek_edition(self, parmenides_b13_b25) -> None:
        grc = _body(parmenides_b13_b25, "28 B 18", "grc")
        assert "femina virque simul Veneris cum germina miscent" in grc
        assert "nam si virtutes permixto semine pugnent" in grc

    def test_german_of_the_doubtful_b22(self, parmenides_b13_b25) -> None:
        c = _fragment(parmenides_b13_b25, "28 B 22", "deu")
        assert c.text.startswith("Wunderbar schwer zu überzeugen")
        assert c.block_type == "spurious"


class TestHeraclitusDoubtfulExcerpt:
    """Verbatim OCR of pp. 102–105: B 126a–139."""

    def test_canonical_up_to_126(self, heraclitus_b125_b139) -> None:
        types = _types(heraclitus_b125_b139, "grc")
        assert types["22 B 125"] is None
        assert types["22 B 125a"] is None
        assert types["22 B 126"] is None

    def test_spurious_from_126a(self, heraclitus_b125_b139) -> None:
        for lang in ("grc", "deu"):
            types = _types(heraclitus_b125_b139, lang)
            spurious = sorted(s for s, t in types.items() if t == "spurious")
            assert "22 B 126a" in spurious, lang
            assert "22 B 137" in spurious, lang
            assert all(t == "spurious" for s, t in types.items() if s >= "22 B 127"), lang

    def test_german_126b(self, heraclitus_b125_b139) -> None:
        assert _fragment(heraclitus_b125_b139, "22 B 126b", "deu").text.startswith("Stets")
