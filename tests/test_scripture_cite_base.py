"""Behavior-pinning tests for the four scripture-cite rule variants.

Written BEFORE the de/en/fr/lat quadruplication was collapsed into
the shared :class:`_base.BaseScriptureCiteRule` — every assertion
here pins observable output (rule name, Candidate fields, spans,
confidences, source_method, lang/self-reference gating) so the
refactor is provably behavior-preserving.
"""

from __future__ import annotations

from minerva.refs.rules import ChunkInfo
from minerva.refs.rules.scripture_cite import (
    ScriptureCiteRule,
    ScriptureCiteRuleDe,
    ScriptureCiteRuleEn,
    ScriptureCiteRuleFr,
)


def _chunk(
    text: str,
    *,
    lang: str,
    author: str = "Hegel",
) -> ChunkInfo:
    return ChunkInfo(
        chunk_id="c1",
        author=author,
        work="W",
        lang=lang,
        section=None,
        text=text,
    )


# ════════════════════════════════════════════════════════════════════
# Latin (Vulgate)
# ════════════════════════════════════════════════════════════════════


class TestLatPinned:
    def test_full_cite_all_fields(self) -> None:
        rule = ScriptureCiteRule()
        assert rule.name == "scripture_cite_vulgate"
        text = "sicut dicitur Matth. 5-48: estote ergo"
        cands = list(rule.scan(_chunk(text, lang="lat", author="Aquinas")))
        assert len(cands) == 1
        c = cands[0]
        assert c.source_chunk_id == "c1"
        assert c.source_form_snapshot == "Matth. 5-48"
        assert text[c.source_span_start : c.source_span_end] == "Matth. 5-48"
        assert c.target_author == "Vulgate"
        assert c.target_work == "Matthew"
        assert c.target_locator == "Matt 5:48"
        assert c.reference_type == "cites"
        assert c.confidence == 0.90
        assert c.source_method == "rule_strong"
        assert c.quoted_phrase is None
        assert c.note is None
        assert c.target_chunk_id is None

    def test_chapter_only_conf_075(self) -> None:
        rule = ScriptureCiteRule()
        cands = list(rule.scan(_chunk("vide Matth. 5 ubi", lang="lat")))
        assert len(cands) == 1
        assert cands[0].target_locator == "Matt 5"
        assert cands[0].confidence == 0.75
        assert cands[0].source_method == "rule_weak"

    def test_ambiguous_bare_conf_065(self) -> None:
        rule = ScriptureCiteRule()
        cands = list(rule.scan(_chunk("vide Cor. 13-4: caritas", lang="lat")))
        assert len(cands) == 1
        assert cands[0].target_work == "1 Corinthians"
        assert cands[0].confidence == 0.65
        assert cands[0].source_method == "rule_weak"

    def test_ordinal_prefix_disambiguates(self) -> None:
        rule = ScriptureCiteRule()
        cands = list(rule.scan(_chunk("ut habetur I Cor. 13-4: caritas", lang="lat")))
        assert len(cands) == 1
        assert cands[0].target_work == "1 Corinthians"
        assert cands[0].confidence == 0.90

    def test_ad_prefix_stays_ambiguous(self) -> None:
        # "ad Cor." marks an epistle but does NOT disambiguate 1 vs 2
        # Corinthians, so it must stay in the ambiguous band, not the
        # full-confidence rule_strong band (issue #52).
        rule = ScriptureCiteRule()
        cands = list(rule.scan(_chunk("ut habetur ad Cor. 13-4: caritas", lang="lat")))
        assert len(cands) == 1
        assert cands[0].target_work == "1 Corinthians"
        assert cands[0].confidence == 0.65
        assert cands[0].source_method == "rule_weak"

    def test_lang_and_self_reference_gates(self) -> None:
        rule = ScriptureCiteRule()
        assert list(rule.scan(_chunk("Matth. 5-48", lang="eng"))) == []
        assert list(rule.scan(_chunk("Matth. 5-48", lang="lat", author="Vulgate"))) == []

    def test_unknown_abbrev_skipped(self) -> None:
        rule = ScriptureCiteRule()
        assert list(rule.scan(_chunk("Xyzzy. 5-48", lang="lat"))) == []


class TestLatWordCollisionBare:
    """The trailing period is the only evidence a word-collision
    abbreviation is a citation at all (#508).

    ``Ex``/``Is``/``Io``/``Num``/``Os`` are ordinary Latin words —
    the preposition, the pronoun, the interjection, the interrogative
    particle, the noun. `_CITE_RE` makes the period optional so
    spelled-out genitive forms ("Sapientiae 11-21", "Actuum 10" — both
    live in the corpus) still match, and sentence-initial
    capitalisation then makes prose indistinguishable from a cite.
    Measured over all 67,728 `lat` chunks: 5 of 174 abbreviations
    appear as a lowercase word before a number, and `ex` leads them
    ("patet ex 30 affectuum definitione"). Zero capitalised bare
    occurrences exist today, so this is latency, not a live wrong row.
    """

    def test_bare_ex_is_downgraded(self) -> None:
        rule = ScriptureCiteRule()
        cands = list(rule.scan(_chunk("Ex 3 modis potest dici.", lang="lat")))
        assert len(cands) == 1
        assert cands[0].target_locator == "Exod 3"
        assert cands[0].confidence == 0.65
        assert cands[0].source_method == "rule_weak"

    def test_bare_collision_with_verse_is_downgraded(self) -> None:
        rule = ScriptureCiteRule()
        cands = list(rule.scan(_chunk("Is 40-3 vox clamantis", lang="lat")))
        assert len(cands) == 1
        assert cands[0].target_work == "Isaiah"
        assert cands[0].confidence == 0.65

    def test_periodised_collision_keeps_full_confidence(self) -> None:
        # The regression #508's own proposed fix would have caused:
        # `_AMBIGUOUS_BARE` is keyed on abbr + ordinal prefix and never
        # consults the period, so adding these to it would have taken
        # the 21 live `Num.` cites from 0.90 to 0.65 as well.
        rule = ScriptureCiteRule()
        for text, work in [
            ("Ex. 3-14 dicitur", "Exodus"),
            ("Num. 23-19 dicitur", "Numbers"),
            ("Os. 8-12 dicitur", "Hosea"),
        ]:
            cands = list(rule.scan(_chunk(text, lang="lat")))
            assert len(cands) == 1, text
            assert cands[0].target_work == work
            assert cands[0].confidence == 0.90, text
            assert cands[0].source_method == "rule_strong", text

    def test_bare_spelled_out_forms_keep_full_confidence(self) -> None:
        # The 134 live bare matches in the corpus are these: genuine
        # cites in the spelled-out genitive, written without a period.
        rule = ScriptureCiteRule()
        # Capitalised, because `_CITE_RE` requires `[A-Z]` — the two
        # lowercase genuine cites the corpus carries (`sapientiae
        # 11-21`, `actuum 10`) are missed entirely, which is a
        # separate gap and is filed, not fixed here.
        for text, locator in [
            ("Isaiae 54-13 dicitur", "Isa 54:13"),
            ("sicut Sapientiae 11-21 dicitur", "Wis 11:21"),
            ("Et Actuum 10, dicit Petrus", "Acts 10"),
        ]:
            cands = list(rule.scan(_chunk(text, lang="lat")))
            assert len(cands) == 1, text
            assert cands[0].target_locator == locator
            assert cands[0].confidence >= 0.75, text

    def test_other_languages_have_no_collision_set(self) -> None:
        # Only the Latin subclass sets one; the shared regex is
        # untouched, so de/en/fr behaviour is unchanged.
        for rule in (ScriptureCiteRuleDe(), ScriptureCiteRuleEn(), ScriptureCiteRuleFr()):
            assert rule.word_collision == frozenset()


# ════════════════════════════════════════════════════════════════════
# German (Luther)
# ════════════════════════════════════════════════════════════════════


class TestDePinned:
    def test_full_cite_all_fields(self) -> None:
        rule = ScriptureCiteRuleDe()
        assert rule.name == "scripture_cite_luther_de"
        text = "wie es heißt Röm 8,15 und weiter"
        cands = list(rule.scan(_chunk(text, lang="deu")))
        assert len(cands) == 1
        c = cands[0]
        assert c.source_form_snapshot == "Röm 8,15"
        assert text[c.source_span_start : c.source_span_end] == "Röm 8,15"
        assert c.target_author == "Luther Bibel 1912"
        assert c.target_work == "Romans"
        assert c.target_locator == "Rom 8:15"
        assert c.reference_type == "cites"
        assert c.confidence == 0.90
        assert c.source_method == "rule_strong"

    def test_named_instance_keeps_name(self) -> None:
        rule = ScriptureCiteRuleDe(name="hegel_scripture_cite_de")
        assert rule.name == "hegel_scripture_cite_de"
        assert rule.target_author == "Luther Bibel 1912"

    def test_period_separator_and_prefix(self) -> None:
        rule = ScriptureCiteRuleDe()
        cands = list(rule.scan(_chunk("Joh. 3. 17", lang="deu"))) + list(
            rule.scan(_chunk("1 Mose 2, 7", lang="deu"))
        )
        assert [c.target_work for c in cands] == ["John", "Genesis"]
        # Bare "Joh" is ambiguous (Gospel vs epistles) → low band.
        assert cands[0].confidence == 0.65
        assert cands[0].source_method == "rule_weak"
        # Prefixed Mose-form is unambiguous → full band.
        assert cands[1].confidence == 0.90

    def test_period_form_needs_a_verse_after_the_chapter(self) -> None:
        # The period separator would otherwise read sentence-final
        # punctuation after a chapter number as a cite.
        rule = ScriptureCiteRuleDe()
        assert list(rule.scan(_chunk("Er las Joh. 3. Dann ging er.", lang="deu"))) == []

    def test_lang_and_self_reference_gates(self) -> None:
        rule = ScriptureCiteRuleDe()
        assert list(rule.scan(_chunk("Röm 8,15", lang="eng"))) == []
        assert list(rule.scan(_chunk("Röm 8,15", lang="deu", author="Luther Bibel 1912"))) == []


# ════════════════════════════════════════════════════════════════════
# English (KJV)
# ════════════════════════════════════════════════════════════════════


class TestEnPinned:
    def test_full_cite_all_fields(self) -> None:
        rule = ScriptureCiteRuleEn()
        assert rule.name == "scripture_cite_kjv_en"
        text = "as it is said Matt 5:48 and so on"
        cands = list(rule.scan(_chunk(text, lang="eng", author="Hobbes")))
        assert len(cands) == 1
        c = cands[0]
        assert c.source_form_snapshot == "Matt 5:48"
        assert text[c.source_span_start : c.source_span_end] == "Matt 5:48"
        assert c.target_author == "King James Bible"
        assert c.target_work == "Matthew"
        assert c.target_locator == "Matt 5:48"
        assert c.confidence == 0.90
        assert c.source_method == "rule_strong"

    def test_period_separator_17th_century(self) -> None:
        rule = ScriptureCiteRuleEn()
        cands = list(rule.scan(_chunk("see Gen. 3. 5 there", lang="eng")))
        assert len(cands) == 1
        assert cands[0].target_work == "Genesis"
        assert cands[0].target_locator == "Gen 3:5"

    def test_ambiguous_bare_low_confidence(self) -> None:
        rule = ScriptureCiteRuleEn()
        cands = list(rule.scan(_chunk("see Cor. 13:4 there", lang="eng")))
        assert len(cands) == 1
        assert cands[0].target_work == "1 Corinthians"
        assert cands[0].confidence == 0.65
        assert cands[0].source_method == "rule_weak"

    def test_lang_and_self_reference_gates(self) -> None:
        rule = ScriptureCiteRuleEn()
        assert list(rule.scan(_chunk("Matt 5:48", lang="deu"))) == []
        assert list(rule.scan(_chunk("Matt 5:48", lang="eng", author="King James Bible"))) == []


# ════════════════════════════════════════════════════════════════════
# French (Sacy)
# ════════════════════════════════════════════════════════════════════


class TestFrPinned:
    def test_full_cite_all_fields(self) -> None:
        rule = ScriptureCiteRuleFr()
        assert rule.name == "scripture_cite_sacy_fr"
        text = "comme dit Rm 1, 18 ailleurs"
        cands = list(rule.scan(_chunk(text, lang="fra", author="Pascal")))
        assert len(cands) == 1
        c = cands[0]
        assert c.source_form_snapshot == "Rm 1, 18"
        assert text[c.source_span_start : c.source_span_end] == "Rm 1, 18"
        assert c.target_author == "Sacy"
        assert c.target_work == "Romans"
        assert c.target_locator == "Rom 1:18"
        assert c.confidence == 0.90
        assert c.source_method == "rule_strong"

    def test_colon_separator_also_accepted(self) -> None:
        rule = ScriptureCiteRuleFr()
        cands = list(rule.scan(_chunk("voir Mt 5:48 plus loin", lang="fra")))
        assert len(cands) == 1
        assert cands[0].target_work == "Matthew"
        assert cands[0].target_locator == "Matt 5:48"

    def test_ambiguous_bare_low_confidence(self) -> None:
        rule = ScriptureCiteRuleFr()
        cands = list(rule.scan(_chunk("voir Co 13, 4 plus loin", lang="fra")))
        assert len(cands) == 1
        assert cands[0].target_work == "1 Corinthians"
        assert cands[0].confidence == 0.65
        assert cands[0].source_method == "rule_weak"

    def test_lang_and_self_reference_gates(self) -> None:
        rule = ScriptureCiteRuleFr()
        assert list(rule.scan(_chunk("Rm 1, 18", lang="eng"))) == []
        assert list(rule.scan(_chunk("Rm 1, 18", lang="fra", author="Sacy"))) == []


# ════════════════════════════════════════════════════════════════════
# French — 19th-c Roman-chapter convention (Renan)
# ════════════════════════════════════════════════════════════════════


class TestFrRomanPinned:
    """Renan's citation shape: comma after the book name, chapter in
    Roman numerals (either case), verse in digits — "Luc, xxiii, 34".
    The plain FR rule requires Arabic chapters and never fired on any
    of Renan's ~1,265 cite-bearing chunks."""

    def test_lowercase_roman_chapter(self) -> None:
        from minerva.refs.rules.scripture_cite import ScriptureCiteRuleFrRoman

        rule = ScriptureCiteRuleFrRoman()
        cands = list(
            rule.scan(_chunk("Cf. Luc, xxiii. 34, sur le pardon.", lang="fra", author="Renan"))
        )
        assert len(cands) == 1
        assert cands[0].target_author == "Sacy"
        assert cands[0].target_work == "Luke"
        assert cands[0].target_locator == "Luke 23:34"

    def test_uppercase_roman_chapter(self) -> None:
        from minerva.refs.rules.scripture_cite import ScriptureCiteRuleFrRoman

        rule = ScriptureCiteRuleFrRoman()
        cands = list(
            rule.scan(_chunk("mort de Jacques dans Matth., XXIV, 9;", lang="fra", author="Renan"))
        )
        assert len(cands) == 1
        assert cands[0].target_locator == "Matt 24:9"

    def test_arabic_chapter_still_works(self) -> None:
        from minerva.refs.rules.scripture_cite import ScriptureCiteRuleFrRoman

        rule = ScriptureCiteRuleFrRoman()
        cands = list(rule.scan(_chunk("voir Jean 12, 40 encore", lang="fra", author="Renan")))
        assert len(cands) == 1
        assert cands[0].target_locator == "John 12:40"

    def test_french_pronoun_after_roman_chapter_is_not_a_verse(self) -> None:
        # "Marc, ii, il dit" — 'il' is letters from the Roman set but
        # the verse group is digits-only, so nothing fires.
        from minerva.refs.rules.scripture_cite import ScriptureCiteRuleFrRoman

        rule = ScriptureCiteRuleFrRoman()
        cands = list(rule.scan(_chunk("Marc, ii, il dit ceci.", lang="fra", author="Renan")))
        assert cands == []

    def test_unknown_book_name_does_not_fire(self) -> None:
        # 'Philon' passes the abbr shape but fails the lexicon gate.
        from minerva.refs.rules.scripture_cite import ScriptureCiteRuleFrRoman

        rule = ScriptureCiteRuleFrRoman()
        cands = list(rule.scan(_chunk("selon Philon, ii, 21, les esséniens", lang="fra")))
        assert cands == []

    def test_implausible_roman_value_rejected(self) -> None:
        # 'cc' parses as Roman 200 — beyond any chapter count; the
        # base parser returns None and the match is skipped.
        from minerva.refs.rules.scripture_cite import ScriptureCiteRuleFrRoman

        rule = ScriptureCiteRuleFrRoman()
        cands = list(rule.scan(_chunk("Luc, cc, 3", lang="fra")))
        assert cands == []
