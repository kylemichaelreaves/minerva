"""Tests for the Molesworth Latin Hobbes parser.

The parser this replaced read IA scans of the 17th-century printings
and produced one chunk per chapter, up to 127,001 characters (#535).
The pins here are about the page Molesworth's 1839 reprint actually
presents — a two-column page whose marginal gloss the OCR linearizes
into the body lines — and about the two chapters whose headings do not
survive the scan intact.

The load-bearing one is `TestMarginMarkerStripping`. The marginal
chapter marker and an ordinary body citation of a chapter are the same
string; Hobbes is the corpus's heaviest biblical citer, so a stripper
that does not distinguish them deletes scripture references.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minerva.sources.hobbes_la import (
    _classify,
    _drop_margin_orphans,
    _find_margin_turnover,
    _join_body,
    _Line,
    _paragraphs,
    _roman_to_int,
    _strip_inline_margin,
    parse_dir,
    parse_file,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LEVIATHAN_LAT = _REPO_ROOT / "data" / "hobbes" / "raw_lat" / "leviathan_lat.txt"
_DE_CIVE_LAT = _REPO_ROOT / "data" / "hobbes" / "raw_lat" / "de_cive_lat.txt"

# A committed excerpt in the real shape, so `parse_file` end-to-end is
# exercised in CI and not only on a machine that happens to hold the
# corpus. See `tests/fixtures/hobbes_la/README.md` — and #133, where the
# e2e suite had the identical problem and nobody noticed for months.
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "hobbes_la" / "molesworth_sample.txt"

# Both Latin files are large data inputs that aren't carried in every
# checkout. The integration tests skip without them; every unit test
# and every fixture test below runs regardless.
_HAS_LEVIATHAN = _LEVIATHAN_LAT.is_file()
_HAS_DE_CIVE = _DE_CIVE_LAT.is_file()


@pytest.fixture(scope="module")
def sample_chunks() -> list:
    return list(
        parse_file(_FIXTURE, work_title="Leviathan", work_code="leviathan_lat")
    )


@pytest.fixture(scope="module")
def leviathan_chunks() -> list:
    if not _HAS_LEVIATHAN:
        pytest.skip(f"Latin Leviathan not present at {_LEVIATHAN_LAT}")
    return list(
        parse_file(
            _LEVIATHAN_LAT,
            work_title="Leviathan",
            work_code="leviathan_lat",
        )
    )


@pytest.fixture(scope="module")
def de_cive_chunks() -> list:
    if not _HAS_DE_CIVE:
        pytest.skip(f"De Cive not present at {_DE_CIVE_LAT}")
    return list(
        parse_file(
            _DE_CIVE_LAT,
            work_title="De Cive",
            work_code="de_cive_lat",
        )
    )


# ════════════════════════════════════════════════════════════════════
# Unit: the marginal chapter marker vs. a body citation
# ════════════════════════════════════════════════════════════════════


class TestMarginMarkerStripping:
    """The single highest-consequence rule in the parser.

    ``cap. xiv.`` at a line's edge is the marginal chapter marker,
    printed down the outer edge of every page. The same string in the
    middle of a line is Hobbes citing a chapter — his own, or a book of
    scripture. Stripping unanchored destroys the citations.
    """

    @pytest.mark.parametrize(
        "line,expected",
        [
            # Margin marker run into the head of a body line.
            (
                "cap.  iv.  fieri  solent  homines  insigniter  sapientes",
                "fieri  solent  homines  insigniter  sapientes",
            ),
            # …and into the tail.
            (
                "Cogitationes  hominum  primo  sigillatim,  deinde  cap.  i.",
                "Cogitationes  hominum  primo  sigillatim,  deinde",
            ),
            # No space after the period.
            (
                "possint  alter  alteri  quid  concipiunt  cap.iv.",
                "possint  alter  alteri  quid  concipiunt",
            ),
            # OCR variants of the word: gap. / cav. for cap.
            (
                "gap.  vi.  adolescentibus  laudatur,  ut  signum",
                "adolescentibus  laudatur,  ut  signum",
            ),
            (
                "cav. xxxv.  dictionem  spiritualem,  quantum  praetendunt",
                "dictionem  spiritualem,  quantum  praetendunt",
            ),
        ],
    )
    def test_margin_marker_is_stripped_at_line_edges(
        self, line: str, expected: str
    ) -> None:
        assert _strip_inline_margin(line) == expected

    @pytest.mark.parametrize(
        "line",
        [
            # Hobbes citing his own earlier chapters.
            "ostensum  est  (cap.  xiv.)  pactum  de  seipso  contra",
            "tione  et  scientia  dictum  est  supra  (cap.  v.  et  vi.).",
            "ante  est  (in  cap.  i.  et  n).  Quoniam  autem  inces-",
            "diximus, cap. viii. art. 7, 8, et filios patribus, cap.",
            # Hobbes citing scripture by chapter — the reason this
            # matters. `refs/rules/hobbes.py` runs scripture-cite rules
            # over exactly these.
            "Paulus ad Hebr. cap. vi. versu ultimo, Christum",
            "Propheta  Joel,  (cap.  ii.  30, 31),describens  diem  judi-",
            "Sanctus  Johannes,  (cap.  v.  22):  Pater  judicat  nemi-",
            "De  libro  Judicum,  ex  cap.  xviii.  30,  manifcsturn",
        ],
    )
    def test_body_citations_survive_untouched(self, line: str) -> None:
        assert _strip_inline_margin(line) == line.strip()

    @pytest.mark.skipif(not _HAS_LEVIATHAN, reason="Latin Leviathan not present")
    def test_scripture_chapter_citations_survive_into_chunks(
        self, leviathan_chunks: list
    ) -> None:
        """End-to-end: the citations above reach the chunks."""

        joined = " ".join(c.text for c in leviathan_chunks)
        assert "ad Hebr. cap." in joined or "cap. xiv.)" in joined, (
            "no parenthetical/scriptural 'cap. <roman>' citation survived "
            "into any chunk — the margin stripper is over-reaching"
        )


# ════════════════════════════════════════════════════════════════════
# Unit: line classification
# ════════════════════════════════════════════════════════════════════


class TestClassify:
    @pytest.mark.parametrize(
        "line,chap",
        [
            ("CAPUT  I. ", 1),
            ("CAPUT XVIII.", 18),
            # De Cive's chapter XIV heads "CAPUT. XIV." — a stray
            # period the OCR put after the word. Without it that
            # chapter is absorbed into XIII.
            ("CAPUT. XIV.", 14),
            # Trailing I misread as L.
            ("CAPUT  XLIL", 42),
            ("CAPUT  XLVIL", 47),
        ],
    )
    def test_caput_headings(self, line: str, chap: int) -> None:
        got = _classify(line, max_chap=47)
        assert got.kind == "caput"
        assert got.payload == chap

    @pytest.mark.parametrize(
        "line",
        [
            "28  DE  HOMINE. ",  # page number then running head
            "DE  HOMINE.  121",  # running head then page number
            "DE  CIVITATE  CHRISTIANA.  267",
            "DB  HOMINB.  39",  # OCR-mangled running head
            "DE  HOMTNE.  17",
            "VOL.  III.  D",  # printer's signature
            "c  2",
            "  296  ",  # bare page number
        ],
    )
    def test_page_chrome_is_dropped(self, line: str) -> None:
        assert _classify(line, max_chap=47).kind == "drop"

    def test_out_of_range_chapter_is_dropped_not_body(self) -> None:
        # "CAPUT LXXXIX." past a 47-chapter work is OCR noise shaped
        # like a heading. It must not become text.
        assert _classify("CAPUT  LXXXIX.", max_chap=47).kind == "drop"

    def test_body_line_keeps_raw_for_the_gap_filler(self) -> None:
        got = _classify("cap.  xxxv.  pietatis,  dicuntur  sanctificari", max_chap=47)
        assert got.kind == "body"
        assert got.payload == "pietatis,  dicuntur  sanctificari"
        # The marker is gone from the text but kept in `raw`, which is
        # the only evidence left of a chapter whose heading the OCR lost.
        assert "cap." in got.raw

    def test_line_that_is_only_a_margin_marker_is_blank(self) -> None:
        assert _classify("cap.  xv.", max_chap=47).kind == "blank"

    def test_blank(self) -> None:
        assert _classify("   ", max_chap=47).kind == "blank"


# ════════════════════════════════════════════════════════════════════
# Unit: paragraph assembly across page breaks
# ════════════════════════════════════════════════════════════════════


class TestParagraphAssembly:
    def test_blank_after_unfinished_sentence_does_not_break(self) -> None:
        """The page-break case. L1009/L1017 of `leviathan_lat.txt`:
        the paragraph runs off the foot of one page and resumes on the
        next, with a running head and two blank runs in between."""

        lines = [
            _Line("body", "vel stultior est quam vulgus. Neque sine literis"),
            _Line("blank"),
            _Line("blank"),
            _Line("drop"),  # running head
            _Line("blank"),
            _Line("body", "fieri solent homines insigniter sapientes"),
        ]
        assert list(_paragraphs(lines)) == [
            "vel stultior est quam vulgus. Neque sine literis "
            "fieri solent homines insigniter sapientes"
        ]

    def test_blank_after_finished_sentence_breaks(self) -> None:
        lines = [
            _Line("body", "aliusve doctoris cujuscunque humani."),
            _Line("blank"),
            _Line("body", "Res nominata est, quaecunque cogitari"),
        ]
        assert list(_paragraphs(lines)) == [
            "aliusve doctoris cujuscunque humani.",
            "Res nominata est, quaecunque cogitari",
        ]

    @pytest.mark.parametrize("ender", [".", "?", "!", ":", '."', ".)"])
    def test_terminal_punctuation_variants_end_a_paragraph(self, ender: str) -> None:
        lines = [
            _Line("body", f"prima pars{ender}"),
            _Line("blank"),
            _Line("body", "secunda pars."),
        ]
        assert len(list(_paragraphs(lines))) == 2

    def test_trailing_hyphen_joins_without_space(self) -> None:
        assert _join_body(["acci-", "dentis in corpore"]) == "accidentis in corpore"

    def test_untrailing_lines_join_with_space(self) -> None:
        assert _join_body(["alias ab aliis", "dependentes"]) == (
            "alias ab aliis dependentes"
        )

    def test_final_paragraph_is_emitted_without_trailing_blank(self) -> None:
        assert list(_paragraphs([_Line("body", "ultima sententia")])) == [
            "ultima sententia"
        ]

    def test_drop_lines_alone_never_emit_a_paragraph(self) -> None:
        assert list(_paragraphs([_Line("drop"), _Line("blank")])) == []


# ════════════════════════════════════════════════════════════════════
# Unit: orphaned marginal glosses
# ════════════════════════════════════════════════════════════════════


class TestMarginOrphans:
    def test_short_isolated_line_next_to_a_page_break_is_dropped(self) -> None:
        lines = [
            _Line("body", "vel stultior est quam vulgus. Neque sine literis"),
            _Line("blank"),
            _Line("body", "Deserraone."),  # stranded marginal gloss
            _Line("blank"),
            _Line("drop"),  # running head, 2 lines away
            _Line("blank"),
            _Line("body", "fieri solent homines insigniter sapientes"),
        ]
        out = _drop_margin_orphans(lines)
        assert out[2].kind == "blank"
        # …and with it gone the paragraph joins cleanly.
        assert list(_paragraphs(out)) == [
            "vel stultior est quam vulgus. Neque sine literis "
            "fieri solent homines insigniter sapientes"
        ]

    def test_short_isolated_line_far_from_a_page_break_is_kept(self) -> None:
        """`momento fere temporis.` (L517) is short and isolated and is
        real body text. Distance from the page break is the only thing
        separating it from a gloss, which is why the rule uses it."""

        lines = (
            [_Line("drop")]
            + [_Line("body", "filler sentence here.") for _ in range(20)]
            + [
                _Line("blank"),
                _Line("body", "momento fere temporis."),
                _Line("blank"),
            ]
        )
        out = _drop_margin_orphans(lines)
        assert out[-2].kind == "body"

    def test_long_isolated_line_is_kept(self) -> None:
        long_body = "x" * 60
        lines = [_Line("drop"), _Line("blank"), _Line("body", long_body)]
        assert _drop_margin_orphans(lines)[2].kind == "body"

    def test_line_adjacent_to_body_is_kept(self) -> None:
        lines = [
            _Line("drop"),
            _Line("body", "short one."),
            _Line("body", "continues here"),
        ]
        assert _drop_margin_orphans(lines)[1].kind == "body"

    def test_no_page_breaks_means_nothing_is_dropped(self) -> None:
        lines = [_Line("blank"), _Line("body", "brevis."), _Line("blank")]
        assert _drop_margin_orphans(lines) == lines


# ════════════════════════════════════════════════════════════════════
# Unit: recovering a chapter whose heading the OCR lost
# ════════════════════════════════════════════════════════════════════


class TestMarginTurnover:
    def _run(self, markers: list[str | None]) -> list[_Line]:
        out: list[_Line] = []
        for m in markers:
            if m is None:
                out.append(_Line("drop"))
            else:
                out.append(_Line("body", "textus", raw=m))
        return out

    def test_turnover_returns_the_preceding_page_break(self) -> None:
        lines = self._run(
            ["cap. xxxiv. textus", None, "cap. xxxv. textus", "cap. xxxv. textus"]
        )
        # The page break at index 1 is where chapter XXXV began.
        assert _find_margin_turnover(lines, target_chap=35) == 1

    def test_single_marker_is_not_enough_signal(self) -> None:
        lines = self._run(["cap. xxxiv. textus", None, "cap. xxxv. textus"])
        assert _find_margin_turnover(lines, target_chap=35) is None

    def test_absent_chapter_returns_none(self) -> None:
        lines = self._run(["cap. xxxiv. textus", None, "cap. xxxiv. textus"])
        assert _find_margin_turnover(lines, target_chap=35) is None

    def test_falls_back_to_the_marker_when_no_page_break_precedes(self) -> None:
        lines = self._run(["cap. xxxv. a", "cap. xxxv. b"])
        assert _find_margin_turnover(lines, target_chap=35) == 0


# ════════════════════════════════════════════════════════════════════
# Unit: `_roman_to_int`
# ════════════════════════════════════════════════════════════════════


class TestRomanToInt:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("I", 1),
            ("XVIII", 18),
            ("XLVII", 47),
            # Trailing I misread as L — the one numeral defect
            # Molesworth's headings actually suffer.
            ("XLIL", 42),
            ("XLVIL", 47),
            ("XIL", 12),
            # T for I.
            ("XTI", 12),
            # Legitimate forms that must survive intact. XL is 40 and
            # has no I to restore, so the trailing-L rule must not fire.
            ("XL", 40),
            ("XLI", 41),
            ("L", 50),
            ("LX", 60),
            # Arabic passthrough.
            ("4", 4),
            ("21", 21),
            # Internal whitespace from the scan.
            ("X L I", 41),
        ],
    )
    def test_conversions(self, raw: str, expected: int) -> None:
        assert _roman_to_int(raw) == expected

    @pytest.mark.parametrize("raw", ["", "   ", "hello", "!!"])
    def test_non_numerals_return_none(self, raw: str) -> None:
        assert _roman_to_int(raw) is None


# ════════════════════════════════════════════════════════════════════
# Integration: chapter coverage
# ════════════════════════════════════════════════════════════════════


class TestLeviathanChapters:
    def test_all_47_chapters_present(self, leviathan_chunks: list) -> None:
        chapters = {int(c.book.split()[1]) for c in leviathan_chunks}
        assert chapters == set(range(1, 48)), (
            f"missing: {sorted(set(range(1, 48)) - chapters)}"
        )

    def test_chapter_35_recovered_from_the_margin(
        self, leviathan_chunks: list
    ) -> None:
        """Caput XXXV has neither a heading nor a title line in the
        scan; it exists only because the marginal marker turns over.
        Check it is genuinely XXXV — *De significatione in scripturis
        regni Dei, sancti, sacri, et sacramenti* — and not a slice of
        XXXIV wearing the number."""

        text = " ".join(
            c.text for c in leviathan_chunks if c.book == "Cap 35"
        ).lower()
        assert text, "Cap 35 absent"
        assert "sanctum" in text
        assert "sacramentum" in text


class TestDeCiveChapters:
    def test_all_18_chapters_present(self, de_cive_chunks: list) -> None:
        chapters = {int(c.book.split()[1]) for c in de_cive_chunks}
        assert chapters == set(range(1, 19)), (
            f"missing: {sorted(set(range(1, 19)) - chapters)}"
        )

    def test_chapter_14_survives_its_stray_period(
        self, de_cive_chunks: list
    ) -> None:
        c14 = [c for c in de_cive_chunks if c.book == "Cap 14"]
        assert c14, "Cap 14 absent — 'CAPUT. XIV.' heading not matched"
        assert sum(len(c.text) for c in c14) > 2000


# ════════════════════════════════════════════════════════════════════
# Integration: chunk shape — this is what #535 was filed about
# ════════════════════════════════════════════════════════════════════


class TestChunkGranularity:
    """#535: the old parser emitted one chunk per chapter, up to
    127,001 characters, and that chunk was both the retrieval unit and
    the Reader's paragraph."""

    @pytest.mark.parametrize(
        "fixture_name,min_chunks",
        [("leviathan_chunks", 900), ("de_cive_chunks", 400)],
    )
    def test_chunked_per_paragraph_not_per_chapter(
        self, fixture_name: str, min_chunks: int, request: pytest.FixtureRequest
    ) -> None:
        chunks = request.getfixturevalue(fixture_name)
        assert len(chunks) >= min_chunks

    @pytest.mark.parametrize(
        "fixture_name", ["leviathan_chunks", "de_cive_chunks"]
    )
    def test_no_chapter_sized_chunks(
        self, fixture_name: str, request: pytest.FixtureRequest
    ) -> None:
        chunks = request.getfixturevalue(fixture_name)
        longest = max(chunks, key=lambda c: len(c.text))
        assert len(longest.text) < 8000, (
            f"{longest.section} is {len(longest.text)} chars; the English "
            f"Hobbes files cap paragraphs at 8000"
        )

    @pytest.mark.parametrize(
        "fixture_name", ["leviathan_chunks", "de_cive_chunks"]
    )
    def test_section_and_book_follow_the_english_hobbes_shape(
        self, fixture_name: str, request: pytest.FixtureRequest
    ) -> None:
        """English Hobbes uses ``book`` for the chapter and ``¶N`` for
        the paragraph within it; the Latin now matches."""

        chunks = request.getfixturevalue(fixture_name)
        for c in chunks[:50]:
            assert c.book is not None and c.book.startswith("Cap ")
            assert c.section == f"{c.book}, ¶{c.section.split('¶')[1]}"

    @pytest.mark.parametrize(
        "fixture_name", ["leviathan_chunks", "de_cive_chunks"]
    )
    def test_paragraph_numbers_restart_each_chapter(
        self, fixture_name: str, request: pytest.FixtureRequest
    ) -> None:
        chunks = request.getfixturevalue(fixture_name)
        firsts = {}
        for c in chunks:
            firsts.setdefault(c.book, c.section)
        assert all(s.endswith(", ¶1") for s in firsts.values())

    @pytest.mark.parametrize(
        "fixture_name", ["leviathan_chunks", "de_cive_chunks"]
    )
    def test_chunk_ids_are_unique(
        self, fixture_name: str, request: pytest.FixtureRequest
    ) -> None:
        chunks = request.getfixturevalue(fixture_name)
        ids = [c.chunk_id for c in chunks]
        assert len(set(ids)) == len(ids)


# ════════════════════════════════════════════════════════════════════
# Integration: the OCR defects #535 was filed about are gone
# ════════════════════════════════════════════════════════════════════


class TestOcrDefectsCleared:
    @pytest.mark.parametrize(
        "fixture_name", ["leviathan_chunks", "de_cive_chunks"]
    )
    def test_page_chrome_all_but_gone_from_chunk_text(
        self, fixture_name: str, request: pytest.FixtureRequest
    ) -> None:
        """Running heads, page numbers and printer's signatures are
        dropped as lines. A handful survive anyway, because the OCR
        sometimes merges a whole page break into one line — ``…e
        apostoloVOL. III. c c 386 DE CIVITATE CHRiSTIANA. rum, alia…``
        — where there is no line to drop. Measured 2026-09-12: one such
        line per file. Pinned as a ceiling, not asserted to zero, so
        the number has to be looked at again if it moves."""

        import re

        chunks = request.getfixturevalue(fixture_name)
        joined = " ".join(c.text for c in chunks)
        leaked = re.findall(r"VOL\.\s*[IVXL]+\.\s*\w?\s*\w?\s*\d", joined)
        assert len(leaked) <= 2, f"page chrome leaking into text: {leaked}"

    def test_the_reported_token_is_gone(self, de_cive_chunks: list) -> None:
        """#535's headline: ``triwmph`` for *triumphum*, and the other
        long-s misreads quoted alongside it."""

        joined = " ".join(c.text for c in de_cive_chunks)
        for token in ("triwmph", "Cbrifti", "Damel", "$eniet", "Dabid"):
            assert token not in joined

    @pytest.mark.parametrize(
        "fixture_name", ["leviathan_chunks", "de_cive_chunks"]
    )
    def test_run_together_tokens_all_but_gone(
        self, fixture_name: str, request: pytest.FixtureRequest
    ) -> None:
        """#561's Hobbes share was 98 occurrences across these two
        files. The re-source is what clears it; this pins that it stays
        cleared."""

        import re

        chunks = request.getfixturevalue(fixture_name)
        joined = " ".join(c.text for c in chunks)
        runs = re.findall(r"\b[A-Za-zÀ-ÿ]{24,}\b", joined)
        assert len(runs) <= 5, f"{len(runs)} run-on tokens: {runs[:10]}"


# ════════════════════════════════════════════════════════════════════
# End-to-end over the committed fixture
# ════════════════════════════════════════════════════════════════════
#
# Everything above this line is either a unit test or gated on a corpus
# file that `data/*` keeps out of git. That gate is why this section
# exists: without it `parse_file` and the chapter recovery around it are
# measured only on a developer's machine, and CI's coverage of this
# module reads 63% where a local run reads 97%.


class TestFixtureEndToEnd:
    def test_chapter_numbers_and_paragraph_locators(
        self, sample_chunks: list
    ) -> None:
        assert [c.section for c in sample_chunks] == [
            "Cap 1, ¶1",
            "Cap 1, ¶2",
            "Cap 1, ¶3",
            "Cap 2, ¶1",
            "Cap 2, ¶2",
            "Cap 3, ¶1",
            "Cap 4, ¶1",
            "Cap 4, ¶2",
            "Cap 5, ¶1",
        ]

    def test_chapter_4_is_recovered_from_the_margin(
        self, sample_chunks: list
    ) -> None:
        """The fixture has no ``CAPUT IV.`` line — only two ``cap. iv.``
        marginal markers, exactly as the real Leviathan's Caput XXXV."""

        assert "molesworth_sample.txt" in _FIXTURE.name
        assert "CAPUT  IV." not in _FIXTURE.read_text(encoding="utf-8")
        cap4 = [c for c in sample_chunks if c.book == "Cap 4"]
        assert len(cap4) == 2
        assert "Rerum nomina imponuntur" in cap4[0].text

    def test_chapter_5_survives_its_stray_period(
        self, sample_chunks: list
    ) -> None:
        assert "CAPUT.  V." in _FIXTURE.read_text(encoding="utf-8")
        assert any(c.book == "Cap 5" for c in sample_chunks)

    def test_page_chrome_and_orphan_glosses_are_gone(
        self, sample_chunks: list
    ) -> None:
        joined = " ".join(c.text for c in sample_chunks)
        for gone in (
            "DE HOMINE",  # running head
            "VOL. III.",  # printer's signature
            "Deimagmauone",  # orphaned marginal gloss
            "De sermone.",  # orphaned marginal gloss
        ):
            assert gone not in joined, f"{gone!r} leaked into chunk text"

    def test_margin_markers_are_stripped_but_citations_are_not(
        self, sample_chunks: list
    ) -> None:
        """Both halves of the rule, on one fixture: the run-in ``cap. i.``
        at a line's head is gone, and ``(cap. i. et ii.)`` mid-sentence
        is intact."""

        by_section = {c.section: c.text for c in sample_chunks}
        assert by_section["Cap 1, ¶3"].startswith("contrapressio seu conatus")
        assert "(cap. i. et ii.)" in by_section["Cap 2, ¶1"]
        assert "1 Cor. ix. 9" in by_section["Cap 2, ¶1"]
        assert "Deut. xxv. 4" in by_section["Cap 4, ¶1"]
        assert "Prov. ix. 10" in by_section["Cap 5, ¶1"]

    def test_hyphenated_words_rejoin_across_the_line_break(
        self, sample_chunks: list
    ) -> None:
        text = sample_chunks[0].text
        assert "accidentis" in text  # "acci-" + "dentis"
        assert "objectum" in text  # "ob-" + "jectum"
        assert "acci- dentis" not in text

    def test_chunk_metadata(self, sample_chunks: list) -> None:
        c = sample_chunks[0]
        assert (c.corpus, c.author, c.work, c.lang) == (
            "hobbes",
            "Hobbes",
            "Leviathan",
            "lat",
        )
        assert c.translator == "(Original)"
        # First publication, not the 1839 reprint we read it from —
        # the convention every other Latin original in the corpus uses.
        assert c.edition_year == "1668"
        assert c.block_type is None
        assert len({x.chunk_id for x in sample_chunks}) == len(sample_chunks)

    def test_de_cive_edition_year(self) -> None:
        chunks = list(
            parse_file(_FIXTURE, work_title="De Cive", work_code="de_cive_lat")
        )
        assert chunks[0].edition_year == "1642"

    def test_unknown_work_code_falls_back_without_crashing(self) -> None:
        chunks = list(
            parse_file(_FIXTURE, work_title="Whatever", work_code="unknown_code")
        )
        assert chunks, "an unregistered work code should still parse"

    def test_chapters_past_the_works_count_are_dropped(self) -> None:
        """`_MAX_CHAPTER_BY_CODE` caps De Cive at 18 and Leviathan at 47.
        A fixture parsed as a 2-chapter work keeps only 1 and 2."""

        chunks = list(
            parse_file(_FIXTURE, work_title="Tiny", work_code="leviathan_lat")
        )
        assert max(int(c.book.split()[1]) for c in chunks) == 5


class TestParseDir:
    def test_skips_unknown_filenames(self, tmp_path, capsys) -> None:
        (tmp_path / "not_a_hobbes_work.txt").write_text("CAPUT I.\n\nverba.\n")
        assert list(parse_dir(tmp_path)) == []
        assert "skipping unknown file" in capsys.readouterr().out

    def test_skips_non_txt_and_directories(self, tmp_path) -> None:
        (tmp_path / "leviathan_lat.md").write_text("ignored")
        (tmp_path / "subdir").mkdir()
        assert list(parse_dir(tmp_path)) == []

    def test_parses_a_registered_latin_file(self, tmp_path) -> None:
        (tmp_path / "leviathan_lat.txt").write_text(
            _FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
        )
        chunks = list(parse_dir(tmp_path))
        assert chunks
        assert {c.work for c in chunks} == {"Leviathan"}

    def test_skips_the_english_hobbes_files(self, tmp_path) -> None:
        """`find_work` knows the English works too; only the Latin ones
        belong to this parser."""

        (tmp_path / "leviathan.txt").write_text("By Thomas Hobbes\n")
        assert list(parse_dir(tmp_path)) == []
