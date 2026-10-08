"""Batch 13g: scripture-cite prefixes, footnote markers and the verse canon.

* #719 — a spaced Arabic ordinal ("2 Cor.", "1 Ioan.") was invisible to
  the Latin rule, so the bare default won and bound the wrong book.
* #577 — French "N." is Renan's footnote marker, not an ordinal; the
  prefix swallowed it and the lookup then dropped the whole cite.
* #519 — a verse locator was emitted without checking that the verse
  exists; the committed verse canon refuses it, or disambiguates it.
* #576 — Spinoza registered no scripture rule at all.
"""

from __future__ import annotations

import sqlite3

import pytest

from minerva.refs.rules import ChunkInfo
from minerva.refs.rules.scripture_cite import (
    ScriptureCiteRule,
    ScriptureCiteRuleEn,
    ScriptureCiteRuleFr,
    ScriptureCiteRuleFrRoman,
    ScriptureCiteRuleLatRoman,
    verse_canon,
)


def _chunk(text: str, *, lang: str, author: str = "Aquinas") -> ChunkInfo:
    return ChunkInfo(chunk_id="c1", author=author, work="W", lang=lang, section=None, text=text)


def _scan(rule, text: str, *, lang: str, author: str = "Aquinas"):
    return list(rule.scan(_chunk(text, lang=lang, author=author)))


# ════════════════════════════════════════════════════════════════════
# #719 — Latin spaced Arabic ordinal
# ════════════════════════════════════════════════════════════════════


class TestLatinSpacedArabicOrdinal:
    @pytest.mark.parametrize(
        ("text", "locator"),
        [
            ("unde dicitur 2 Cor. 3-18, nos vero", "2Cor 3:18"),
            ("et 2 Petr. 1-16, non enim", "2Pet 1:16"),
            ("sicut 1 Ioan. 4-10, in hoc est", "1John 4:10"),
            ("et 1 Ioan. 3-9, omnis qui natus", "1John 3:9"),
            ("ut dicitur 1 Cor. 13-9, ex parte", "1Cor 13:9"),
        ],
    )
    def test_the_ordinal_pins_the_book(self, text: str, locator: str) -> None:
        cands = _scan(ScriptureCiteRule(), text, lang="lat")
        assert [c.target_locator for c in cands] == [locator]

    def test_the_span_includes_the_ordinal(self) -> None:
        text = "unde dicitur 2 Cor. 3-18, nos vero"
        (c,) = _scan(ScriptureCiteRule(), text, lang="lat")
        assert text[c.source_span_start : c.source_span_end] == "2 Cor. 3-18"
        assert c.source_form_snapshot == "2 Cor. 3-18"

    def test_a_pinned_ordinal_is_not_ambiguous(self) -> None:
        (c,) = _scan(ScriptureCiteRule(), "unde 2 Cor. 3-18", lang="lat")
        assert c.confidence == 0.90

    def test_a_number_before_an_unnumbered_book_is_not_its_ordinal(self) -> None:
        """'art. 3 Matth. 5-3' — the 3 belongs to the article. The book has
        no numbered sense, so the cite falls back to the bare book and the
        span starts at it, not at the stray digit."""

        text = "ut patet art. 3 Matth. 5-3, beati"
        (c,) = _scan(ScriptureCiteRule(), text, lang="lat")
        assert c.target_locator == "Matt 5:3"
        assert text[c.source_span_start : c.source_span_end] == "Matth. 5-3"

    @pytest.mark.parametrize(
        ("rule", "text", "lang"),
        [
            # Hobbes, Molesworth: 2 Peter 3:13, "new heavens and a new earth".
            (ScriptureCiteRuleLatRoman(), "2 Pet. iii. 13", "lat"),
            # Hobbes, Leviathan: 1 John 4:1, "try the spirits".
            (ScriptureCiteRuleEn(), "1 Joh. 4.1", "eng"),
        ],
    )
    def test_an_ordinal_before_an_ambiguous_book_never_falls_back(self, rule, text, lang) -> None:
        """When the book has numbered senses the digit IS its ordinal, and a
        lexicon miss is a gap in the table. Falling back to the bare form
        would bind its default — 1 Peter, the Gospel of John — which is
        the very defect #719 is about."""

        assert all(
            c.target_locator.split()[0] not in {"1Pet", "John"}
            for c in _scan(rule, text, lang=lang, author="Hobbes")
        )


# ════════════════════════════════════════════════════════════════════
# #577 — French ordinals and footnote markers
# ════════════════════════════════════════════════════════════════════


class TestFrenchFootnoteMarker:
    @pytest.mark.parametrize(
        ("text", "locator"),
        [
            ("4. Jean, xii, 31; xiv, 30.", "John 12:31"),
            ("3. Jean, i, 29, 36.", "John 1:29"),
            ("1. Jean, x, 30.", "John 10:30"),
        ],
    )
    def test_a_footnote_number_is_not_an_ordinal(self, text: str, locator: str) -> None:
        cands = _scan(ScriptureCiteRuleFrRoman(), text, lang="fra", author="Renan")
        assert cands[0].target_locator == locator
        assert text[cands[0].source_span_start :].startswith("Jean")

    @pytest.mark.parametrize(
        "text", ["1. Ch. VI, 22 et suiv.", "2. Ch. XXI, 15-17.", "4. Ch. XIX, 9."]
    )
    def test_renan_chapitre_is_not_chronicles(self, text: str) -> None:
        """'1. Ch. VI, 22' is footnote 1, *chapitre* VI of the book under
        discussion. It used to bind 1 Chronicles 6:22."""

        assert _scan(ScriptureCiteRuleFrRoman(), text, lang="fra", author="Renan") == []
        assert _scan(ScriptureCiteRuleFr(), text, lang="fra", author="Renan") == []


class TestFrenchOrdinals:
    @pytest.mark.parametrize(
        ("text", "locator"),
        [
            ("cf. 1 Sam., xv, 22.", "1Sam 15:22"),
            ("cf. 1 Rois, iii, 4; ", "1Kgs 3:4"),
            ("cf. II Chron., xiv, 7.", "2Chr 14:7"),
            ("cf. I Chron., viii, 33.", "1Chr 8:33"),
            ("cf. 1 Chron., viii, 33.", "1Chr 8:33"),
            ("cf. I Sam., xv, 22.", "1Sam 15:22"),
            ("cf. 2 Jean, i, 7.", "2John 1:7"),
            ("cf. 1 Cor., ix, 9.", "1Cor 9:9"),
        ],
    )
    def test_both_ordinal_styles_resolve(self, text: str, locator: str) -> None:
        cands = _scan(ScriptureCiteRuleFrRoman(), text, lang="fra", author="Renan")
        assert [c.target_locator for c in cands] == [locator]

    def test_bare_chron_is_ambiguous(self) -> None:
        (c,) = _scan(ScriptureCiteRuleFrRoman(), "cf. Chron., i, 3.", lang="fra", author="Renan")
        assert c.target_locator == "1Chr 1:3"
        assert c.confidence == 0.65


# ════════════════════════════════════════════════════════════════════
# #519 — the verse canon
# ════════════════════════════════════════════════════════════════════


class TestVerseCanonFiltersTheEmit:
    def test_an_impossible_verse_is_refused(self) -> None:
        # Revelation 22 has 21 verses.
        assert _scan(ScriptureCiteRule(), "ut dicitur Apoc. 22-27, et", lang="lat") == []

    def test_an_impossible_chapter_is_refused(self) -> None:
        # Revelation has 22 chapters; the chapter-only locator is checked too.
        assert _scan(ScriptureCiteRule(), "ut dicitur Apoc. 23, et", lang="lat") == []

    def test_an_ambiguous_cite_is_disambiguated_by_the_verse(self) -> None:
        # 1 Cor 5 has 13 verses; 2 Cor 5:14 is "caritas enim Christi urget nos".
        (c,) = _scan(ScriptureCiteRule(), "unde ad Cor. 5-14, caritas", lang="lat")
        assert c.target_locator == "2Cor 5:14"
        assert c.target_work == "2 Corinthians"
        assert c.confidence == 0.65  # still a guess about which epistle

    def test_a_possible_ambiguous_cite_keeps_its_default(self) -> None:
        (c,) = _scan(ScriptureCiteRule(), "unde ad Cor. 13-4, caritas", lang="lat")
        assert c.target_locator == "1Cor 13:4"

    def test_the_roman_rule_is_checked_too(self) -> None:
        # Acts 10 has 48 verses.
        assert _scan(ScriptureCiteRuleLatRoman(), "Act. x. 94", lang="lat", author="Hobbes") == []

    def test_french_targets_sacy(self) -> None:
        # Genesis 11 has 32 verses — Gobineau's OCR'd 'Gen. XI, 52'.
        assert (
            _scan(ScriptureCiteRuleFrRoman(), "Gen. XI, 52.", lang="fra", author="Gobineau") == []
        )

    def test_a_target_outside_the_canon_is_not_filtered(self) -> None:
        rule = ScriptureCiteRule(target_author="Some Other Bible")
        (c,) = _scan(rule, "ut dicitur Apoc. 22-27, et", lang="lat")
        assert c.target_locator == "Rev 22:27"


def _bible_db(rows: list[tuple[str, str]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE works (id INTEGER PRIMARY KEY, author TEXT);"
        "CREATE TABLE chunks (chunk_id TEXT, work_id INTEGER, section TEXT);"
    )
    authors = sorted({a for a, _ in rows})
    for i, a in enumerate(authors, 1):
        conn.execute("INSERT INTO works VALUES (?, ?)", (i, a))
    for n, (a, sec) in enumerate(rows):
        conn.execute("INSERT INTO chunks VALUES (?, ?, ?)", (f"c{n}", authors.index(a) + 1, sec))
    return conn


class TestVerseCanonModule:
    def test_build_records_the_highest_verse_per_chapter(self) -> None:
        conn = _bible_db(
            [
                ("Vulgate", "Gen 1:1"),
                ("Vulgate", "Gen 1:3"),  # a gap at 1:2 does not lower the count
                ("Vulgate", "Gen 3:2"),
                ("Vulgate", "Rev 1:1"),
                ("Aquinas", "Gen 1:99"),  # not a Bible: ignored
            ]
        )
        canon = verse_canon.build_canon(conn)
        assert canon["Vulgate"] == {"Gen": [3, 0, 2], "Rev": [1]}
        assert "Aquinas" not in canon

    def test_drift_is_reported_both_ways(self) -> None:
        conn = _bible_db([("Vulgate", "Gen 1:1"), ("Vulgate", "Gen 1:2")])
        assert verse_canon.canon_drift(conn, {"Vulgate": {"Gen": [2]}}) == []
        errs = verse_canon.canon_drift(conn, {"Vulgate": {"Gen": [3]}, "Sacy": {"Gen": [1]}})
        assert any("Vulgate" in e for e in errs)
        assert any("Sacy" in e for e in errs)

    def test_lookup(self) -> None:
        canon = {"Vulgate": {"Gen": [3, 0, 2]}}
        assert verse_canon.exists(canon, "Vulgate", "Gen", 1, 3) is True
        assert verse_canon.exists(canon, "Vulgate", "Gen", 1, 4) is False
        assert verse_canon.exists(canon, "Vulgate", "Gen", 2, None) is False
        assert verse_canon.exists(canon, "Vulgate", "Gen", 3, None) is True
        assert verse_canon.exists(canon, "Vulgate", "Gen", 4, 1) is False
        assert verse_canon.exists(canon, "Sacy", "Gen", 1, 1) is None

    def test_a_book_the_edition_lacks_is_not_filtered(self) -> None:
        """The corpus's KJV has no Apocrypha; Hobbes's "2 Esdras 14.21" is
        a real cite that cannot bind, not an impossible one."""

        assert verse_canon.exists({"Vulgate": {"Gen": [3]}}, "Vulgate", "Exod", 1, 1) is None
        assert "2Esd" not in verse_canon.load_canon()["King James Bible"]

    def test_the_committed_canon_covers_the_four_target_bibles(self) -> None:
        canon = verse_canon.load_canon()
        assert set(canon) == {"Vulgate", "Sacy", "King James Bible", "Luther Bibel 1912"}
        assert canon["Vulgate"]["Rev"][21] == 21
        assert canon["Vulgate"]["1Cor"][4] == 13

    def test_write_and_validate_round_trip(self, tmp_path) -> None:
        path = tmp_path / "verse_counts.json"
        verse_canon.write_canon({"Vulgate": {"Gen": [2]}}, path)
        assert verse_canon.load_canon(path) == {"Vulgate": {"Gen": [2]}}


# ════════════════════════════════════════════════════════════════════
# #576 — Spinoza registers the scripture rules
# ════════════════════════════════════════════════════════════════════


class TestSpinozaRegistersScriptureRules:
    def test_both_latin_rules_are_registered(self) -> None:
        from minerva.refs.rules import spinoza

        kinds = {type(r) for r in spinoza.RULES}
        assert ScriptureCiteRule in kinds
        assert ScriptureCiteRuleLatRoman in kinds

    def test_a_spinoza_cite_fires(self) -> None:
        from minerva.refs.rules import spinoza

        chunk = _chunk("ut Gen. v. 18-20 narratur", lang="lat", author="Spinoza")
        locs = [
            c.target_locator
            for r in spinoza.RULES
            for c in r.scan(chunk)
            if c.target_author == "Vulgate"
        ]
        assert locs == ["Gen 5:18"]


class TestTheCanonFeedsTheRulesFingerprint:
    """A regenerated canon must invalidate `refs_scan_state` (#287)."""

    def test_a_canon_change_moves_the_digest(self, monkeypatch) -> None:
        from minerva.refs.rules.fingerprint import fingerprint_rules
        from minerva.refs.rules.scripture_cite import _base

        rules = (ScriptureCiteRule(),)
        before = fingerprint_rules(rules)
        changed = {**_base._VERSE_CANON, "Vulgate": {**_base._VERSE_CANON["Vulgate"], "Gen": [1]}}
        monkeypatch.setattr(_base, "_VERSE_CANON", changed)
        assert fingerprint_rules(rules) != before
