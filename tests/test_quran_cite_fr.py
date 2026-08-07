"""Renan's French Roman-numeral Quran citations (#223).

The Quran is fully ingested (6,236 `ara` chunks) and had **zero**
incoming cross-references, because the only rule that ever targeted it
matched transliterated surah *names* plus Arabic numerals
(`Al-Baqarah 255`) and was removed in #53 / PR #224 as unfired-and-unsafe.
Renan writes a French **book name** plus **Roman** numerals.

Every locator-bearing Quran citation in the corpus, found by scanning all
142 chunks that name the Quran in any language:

    Coran, xviir, 94 et suiv.; xxi, 96      L'Antéchrist ¶23
    Coran, sur. xv, 80                      Histoire du peuple d'Israël
    Coran, v, i, 92                         Histoire du peuple d'Israël

Three sites, four citations — matching the issue's estimate exactly. The
readings are confirmed by content, not just by shape:

* Surah 18 (Al-Kahf) 83–98 is the Dhul-Qarnayn / Gog-and-Magog passage,
  and Renan's sentence is about Gog and Magog personifying the Scythian
  invasion. 21:96 (Al-Anbiyaa) is the other Gog-and-Magog verse. So
  `xviir` is `xviii` — 18 — with an OCR'd final `i`.
* Surah 15 (Al-Hijr, "the rocky tract") 80 is the rock-dwellers passage,
  and Renan's sentence glosses "Hagar est l'Arabie Pétrée".
"""

from __future__ import annotations

from minerva.refs.rules import ChunkInfo
from minerva.refs.rules.quran_cite_fr import QuranCiteRuleFrRoman

RULE = QuranCiteRuleFrRoman()


def _chunk(text: str, *, lang: str = "fra", author: str = "Renan") -> ChunkInfo:
    return ChunkInfo(
        chunk_id="renan-1",
        author=author,
        work="L'Antéchrist",
        lang=lang,
        section="¶23",
        text=text,
    )


def _cands(text: str, **kw):
    return list(RULE.scan(_chunk(text, **kw)))


class TestTheThreeRealSites:
    def test_sur_abbreviation_form(self):
        """`Coran, sur. xv, 80` — Histoire du peuple d'Israël."""

        (c,) = _cands("Hagar est l'Arabie Pétrée (Coran, sur. xv, 80), par l'équivalence.")

        assert c.target_author == "Quran"
        assert c.target_work == "Al-Hijr"
        assert c.target_locator == "15:80"
        assert c.reference_type == "cites"
        assert "Coran, sur. xv, 80" in c.source_form_snapshot

    def test_bare_form_with_ocr_damaged_numeral_and_a_continuation(self):
        """`Coran, xviir, 94 et suiv.; xxi, 96` — two citations, one of
        them with an OCR'd Roman numeral."""

        cands = _cands(
            "ils personnifient l'invasion scythique ou barbare en général. "
            "Comparez Coran, xviir, 94 et suiv.; xxi, 96. L'application messianique"
        )

        assert [(c.target_work, c.target_locator) for c in cands] == [
            ("Al-Kahf", "18:94"),
            ("Al-Anbiyaa", "21:96"),
        ]

    def test_three_number_form_is_deliberately_not_matched(self):
        """`Coran, v, i, 92` is ambiguous — it reads as volume/surah/verse
        but the Quran has no volumes, and `v, i` could be a damaged `vi`
        or a stray footnote marker. #223 flags it as needing a decision;
        the decision is to skip it, because the value of this rule is
        precision (a bare `Coran` + locator is unambiguous) and #53 was
        closed precisely for guessing.

        If it is ever resolved, it is one citation in the whole corpus.
        """

        assert _cands("Coran, v, i, 92; Freytag, Lex., IV, p. 256; Corpus inscr.") == []


class TestScoping:
    def test_does_not_fire_on_non_french_chunks(self):
        assert _cands("Compare Coran, xv, 80 for the same idea.", lang="eng") == []

    def test_does_not_fire_on_the_quran_s_own_chunks(self):
        assert _cands("Coran, sur. xv, 80", author="Quran") == []

    def test_bare_mention_without_a_locator_emits_nothing(self):
        """17 of Renan's Quran mentions are bare. Matching those is the
        recall gamble #53 was closed for."""

        assert _cands("Le Coran est, en effet, le dernier aboutissant littéraire.") == []
        assert _cands("des équivalents exacts des surates du Coran, des manifestes") == []

    def test_a_page_number_after_the_book_name_is_not_a_locator(self):
        """Hegel's index has `Qur'an 162 247` — page numbers, not a
        surah:ayah pair. The rule requires the French name, so this is
        already out of scope, but pin it: two bare Arabic numerals with
        no comma must never look like a citation."""

        assert _cands("Coran 162 247") == []


class TestNumeralHandling:
    def test_arabic_numerals_are_accepted_too(self):
        (c,) = _cands("Coran, 15, 80 — the same passage in modern notation.")
        assert c.target_locator == "15:80"

    def test_uppercase_roman_numerals_are_accepted(self):
        (c,) = _cands("Coran, XV, 80.")
        assert c.target_locator == "15:80"

    def test_a_trailing_r_is_read_as_an_ocr_damaged_final_i(self):
        """`r` is not a Roman numeral, so a trailing one on an otherwise
        valid numeral is unambiguously OCR damage — and here the repair
        is confirmed by content (surah 18 is the Gog-and-Magog surah)."""

        (c,) = _cands("Coran, xviir, 94")
        assert c.target_locator == "18:94"

    def test_a_surah_number_beyond_the_canon_is_rejected(self):
        """There are 114 surahs. 115 is a misparse, not a citation."""

        assert _cands("Coran, cxv, 3") == []

    def test_ayah_zero_is_rejected(self):
        assert _cands("Coran, xv, 0") == []

    def test_an_unparseable_numeral_is_skipped(self):
        assert _cands("Coran, zz, 80") == []

    def test_subtractive_roman_numerals_resolve_to_the_right_surah(self):
        """`iv`, `ix`, `xl`, `xliv` are ordinary surah numbers — An-Nisa
        (4) and At-Tawbah (9) are among the most-cited surahs anywhere.
        A parser that only summed left-to-right would read `ix` as 11 and
        target the wrong surah silently, so these are pinned by name and
        not only by number."""

        cases = {
            "Coran, iv, 34": ("An-Nisaa", "4:34"),
            "Coran, ix, 5": ("At-Tawbah", "9:5"),
            "Coran, xl, 7": ("Ghafir", "40:7"),
            "Coran, xliv, 3": ("Ad-Dukhan", "44:3"),
            "Coran, xcix, 1": ("Az-Zalzalah", "99:1"),
        }
        for text, (work, locator) in cases.items():
            (c,) = _cands(text)
            assert (c.target_work, c.target_locator) == (work, locator), text


class TestNumeralParserDirectly:
    """The two `None` returns are unreachable through `scan` — the run
    regex only admits `[ivxlc]`/digits, so a bad character never reaches
    the parser. Covered directly so the guards are not dead weight nobody
    has ever executed."""

    def test_a_non_numeral_character_yields_none(self):
        from minerva.refs.rules.quran_cite_fr import _parse_numeral

        assert _parse_numeral("zz") is None
        assert _parse_numeral("xvz") is None

    def test_an_empty_or_zero_numeral_yields_none(self):
        from minerva.refs.rules.quran_cite_fr import _parse_numeral

        assert _parse_numeral("") is None
        assert _parse_numeral("0") is None


class TestCandidateShape:
    def test_emitted_as_a_strong_rule_row_with_a_span(self):
        text = "Hagar est l'Arabie Pétrée (Coran, sur. xv, 80), par l'équivalence."
        (c,) = _cands(text)

        assert c.source_method == "rule_strong"
        assert c.confidence >= 0.85
        assert text[c.source_span_start : c.source_span_end] == c.source_form_snapshot
        # Locator is left for the runner's exact-section lookup to bind;
        # the rule makes no chunk-level claim of its own.
        assert c.target_chunk_id is None

    def test_the_locator_matches_the_shape_quran_chunks_store(self):
        """Quran chunks carry `section` as `"<surah>:<ayah>"`
        (`sources/quran.py`), which is what `insert_candidate` looks up.
        A locator in any other shape silently never binds."""

        (c,) = _cands("Coran, sur. xv, 80")
        surah, _, ayah = c.target_locator.partition(":")
        assert surah.isdigit() and ayah.isdigit()
