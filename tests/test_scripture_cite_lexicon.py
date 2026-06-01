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
