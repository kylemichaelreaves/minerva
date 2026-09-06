"""Unit tests for scripture_cite lexicon and language-specific cite regex."""

from __future__ import annotations

from minerva.refs.rules import ChunkInfo
from minerva.refs.rules.scripture_cite import (
    _CITE_RE,
    _LEXICON,
    ScriptureCiteRule,
    ScriptureCiteRuleDe,
    ScriptureCiteRuleEn,
    ScriptureCiteRuleFr,
    _sbl_abbr_for,
)
from minerva.refs.rules.scripture_cite.de import _CITE_RE_DE, _LEXICON_DE
from minerva.refs.rules.scripture_cite.en import _CITE_RE_EN
from minerva.refs.rules.scripture_cite.fr import _CITE_RE_FR


def _chunk(text: str, *, lang: str = "lat") -> ChunkInfo:
    return ChunkInfo(
        chunk_id="c1",
        author="Aquinas",
        work="Summa",
        lang=lang,
        section=None,
        text=text,
    )


def test_lexicon_matth_maps_to_matthew():
    assert _LEXICON.get((None, "Matth")) == "Matthew"
    assert _sbl_abbr_for("Matthew") == "Matt"


def test_lexicon_ordinal_corinthians():
    assert _LEXICON.get(("I", "Cor")) == "1 Corinthians"


def test_lat_cite_regex_parses_matth_5_48():
    m = _CITE_RE.search("see Matth. 5-48 for the beatitude.")
    assert m is not None
    assert m.group("abbr") == "Matth"
    assert m.group("chap") == "5"
    assert m.group("verse") == "48"


def test_de_smoke_rom_8_15():
    m = _CITE_RE_DE.search("Röm 8,15")
    assert m is not None
    assert _LEXICON_DE.get((None, "Röm")) == "Romans"
    rule = ScriptureCiteRuleDe()
    hits = list(rule.scan(_chunk("Röm 8,15", lang="deu")))
    assert len(hits) == 1
    assert hits[0].target_locator == "Rom 8:15"


def test_en_smoke_matt_5_48():
    m = _CITE_RE_EN.search("Matt 5:48")
    assert m is not None
    rule = ScriptureCiteRuleEn()
    hits = list(rule.scan(_chunk("Matt 5:48", lang="eng")))
    assert hits and hits[0].target_work == "Matthew"


def test_fr_smoke_rm_comma():
    m = _CITE_RE_FR.search("Rm 1, 18")
    assert m is not None
    rule = ScriptureCiteRuleFr()
    hits = list(rule.scan(_chunk("Rm 1, 18", lang="fra")))
    assert hits and hits[0].target_work == "Romans"


def test_ambiguous_bare_cor_low_confidence_via_rule():
    rule = ScriptureCiteRule()
    hits = list(rule.scan(_chunk("ut in Cor. 13-4 dictum est.")))
    assert len(hits) == 1
    assert hits[0].confidence < 0.85


# ──────────────────────────────────────────────────────────────────
# Lowercase spelled-out cites (#511 half 2)
# ──────────────────────────────────────────────────────────────────
#
# `_CITE_RE`'s abbrev class anchors on a capital initial, which is what
# keeps `patet ex 30 affectuum` from binding Exodus 30 (#508). Aquinas
# nonetheless writes the *spelled-out* genitive forms lowercase mid
# sentence, and those were missed entirely. Measured over all 67,728
# `lat` chunks: 12 lowercase-initial lexicon forms sit before a number,
# 2 are genuine cites, and both are ≥4 letters — every one of the 10
# collision hits is ≤3 (`ex`, `io`, `is`, `tim`). Hence a length floor
# rather than a relaxed anchor.


def test_lowercase_spelled_out_genitive_is_a_cite():
    """`sicut sapientiae 11-21 dicitur` → Wis 11:21.

    Aquinas, chunk 74dd9482bbec9ec16fd4."""
    rule = ScriptureCiteRule()
    hits = list(
        rule.scan(_chunk("sicut sapientiae 11-21 dicitur: omnia in numero"))
    )
    assert len(hits) == 1
    assert hits[0].target_work == "Wisdom"
    assert hits[0].target_locator == "Wis 11:21"


def test_lowercase_spelled_out_chapter_only_cite():
    """`Et actuum 10, dicit Petrus` → Acts 10, chapter-level.

    Aquinas, chunk 956312c711ff565e8654."""
    rule = ScriptureCiteRule()
    hits = list(rule.scan(_chunk("Et actuum 10, dicit Petrus: hunc")))
    assert len(hits) == 1
    assert hits[0].target_work == "Acts"
    assert hits[0].target_locator == "Acts 10"


def test_short_lowercase_abbrev_stays_prose():
    """The length floor is what keeps #508's collision class closed.

    `ex` is 2 letters, so `patet ex 30 affectuum` (Spinoza, chunk
    bf1bf64a39a6a22463c7) must still produce nothing — a blanket
    `re.IGNORECASE` would bind Exodus 30 here."""
    rule = ScriptureCiteRule()
    assert list(rule.scan(_chunk("Patet ex 30 affectuum definitione"))) == []
    assert list(rule.scan(_chunk("fed is 3 cujus authoritate"))) == []


def test_capitalised_forms_are_unaffected():
    """The relaxation adds an alternative; it must not displace the
    anchored branch or change what it yields."""
    rule = ScriptureCiteRule()
    hits = list(rule.scan(_chunk("see Matth. 5-48 for the beatitude.")))
    assert len(hits) == 1
    assert hits[0].target_locator == "Matt 5:48"


def test_lowercase_lookup_does_not_leak_across_languages():
    """The lowercase keys are added to the Latin lexicon only. German
    `Weisheit` shares no form with `sapientiae`, but the German rule
    must keep its own case rules regardless."""
    hits = list(ScriptureCiteRuleDe().scan(_chunk("sapientiae 11-21", lang="deu")))
    assert hits == []


def test_lowercase_floor_admits_exactly_four_letters_and_up():
    """Pins where the floor sits, not merely that one exists.

    `matt` is 4 letters and must bind; `luc` is 3 and must not. Both
    assertions are behavioural on purpose — raising
    `_MIN_LOWERCASE_ABBR` to 5 fails the first, lowering it to 3 fails
    the second, and only a floor of exactly 4 passes both. An equality
    check on the constant would short-circuit both and prove neither."""
    rule = ScriptureCiteRule()

    four = list(rule.scan(_chunk("ut matt. 5-48 dicitur")))
    assert len(four) == 1
    assert four[0].target_locator == "Matt 5:48"

    assert list(rule.scan(_chunk("ut luc. 5-48 dicitur"))) == []


def test_lowercase_ambiguous_bare_keeps_its_discount():
    """The lowercase branch must not launder an ambiguous cite.

    `_AMBIGUOUS_BARE` holds 17 entries of ≥4 letters (`Corinthiorum`,
    `Petri`, `Thessalonicenses`, …), so admitting lowercase spelled-out
    forms makes them reachable in a case the membership test was never
    written for. Bare `corinthiorum` is 1-vs-2 Corinthians exactly as
    `Corinthiorum` is, and must carry `_CONF_AMBIGUOUS` either way.

    `_WORD_COLLISION` needs no such test: every entry in it is ≤3
    letters, so the length floor keeps #508's class out of the
    lowercase branch entirely."""
    rule = ScriptureCiteRule()
    upper = list(rule.scan(_chunk("ut in Corinthiorum 13-4 dictum est.")))
    lower = list(rule.scan(_chunk("ut in corinthiorum 13-4 dictum est.")))
    assert len(upper) == len(lower) == 1
    assert upper[0].confidence < 0.85
    assert lower[0].confidence == upper[0].confidence
    assert lower[0].source_method == upper[0].source_method
