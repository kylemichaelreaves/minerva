"""Tests for the Quran citation rule (refs/rules/quran_cite.py).

Scaffolding for Phase E (Arabic-philosophy ingest) — no live Arabic-
philosophy chunks exist yet, so this is pure regex behavior covered
against hand-built fixtures.
"""

from __future__ import annotations

import pytest

from minerva.refs.rules import ChunkInfo
from minerva.refs.rules.quran_cite import QURAN_CITE, QuranCiteRule


def _chunk(text: str, *, lang: str = "eng", author: str = "Avicenna") -> ChunkInfo:
    return ChunkInfo(
        chunk_id="test-chunk",
        author=author,
        work="W",
        lang=lang,
        text=text,
        section=None,
    )


@pytest.mark.parametrize(
    "phrase,expected_surah,expected_ayah",
    [
        ("Q 2:255",           2, 255),
        ("Q. 2:255",          2, 255),
        ("Quran 2:255",       2, 255),
        ("Qur'an 2:255",      2, 255),
        ("Qurʾan 2:255",      2, 255),
        ("Quran 1:1",         1, 1),
        ("Sura 36:1",         36, 1),
        ("Surah 36:1",        36, 1),
        ("Surah 114:6",       114, 6),
    ],
)
def test_title_prefixed_citations(phrase: str, expected_surah: int, expected_ayah: int) -> None:
    cands = list(QURAN_CITE.scan(_chunk(f"As is said in {phrase}, the verse means…")))
    assert len(cands) == 1, f"expected one candidate, got {len(cands)}"
    c = cands[0]
    assert c.target_author == "Quran"
    assert c.target_locator == f"{expected_surah}:{expected_ayah}"
    assert c.reference_type == "cites"
    assert c.source_method == "rule_strong"
    assert c.confidence >= 0.9


@pytest.mark.parametrize(
    "phrase,expected_surah,expected_ayah",
    [
        ("Al-Baqarah 2:255",  2, 255),
        ("al-Baqarah 255",    2, 255),
        ("Al-Fatihah 1",      1, 1),
        ("An-Nas 6",          114, 6),
        ("Ya-Sin 36",         36, 36),
    ],
)
def test_surah_name_citations(phrase: str, expected_surah: int, expected_ayah: int) -> None:
    cands = list(QURAN_CITE.scan(_chunk(f"In {phrase} we read…")))
    assert len(cands) >= 1, f"expected at least one candidate for {phrase!r}"
    # The surah-name pass may emit a candidate; the title-prefix pass
    # would not (no Q/Quran/Surah prefix). Either way the resolved
    # surah:ayah should match.
    match = [c for c in cands if c.target_locator == f"{expected_surah}:{expected_ayah}"]
    assert match, (
        f"expected surah:ayah {expected_surah}:{expected_ayah} for {phrase!r}; "
        f"got {[c.target_locator for c in cands]}"
    )


def test_name_and_number_must_agree() -> None:
    """``Al-Baqarah 3:5`` is contradictory (surah 2 named, surah 3
    numbered). The rule drops the candidate rather than emit a wrong one."""
    cands = list(QURAN_CITE.scan(_chunk("see Al-Baqarah 3:5 here")))
    # Should not produce a (2, 5) row from the name alone OR a (3, 5)
    # row from the inconsistent locator.
    assert all(c.target_locator != "3:5" for c in cands)
    assert all(c.target_locator != "2:5" for c in cands)


def test_does_not_fire_on_quran_chunks_themselves() -> None:
    cands = list(QURAN_CITE.scan(_chunk("Q 2:255 says", author="Quran")))
    assert cands == []


def test_lang_gating_excludes_grc() -> None:
    """Default ``langs`` is (eng, fra, deu, ara, lat). A Greek chunk
    is outside the gate — no candidates emitted."""
    cands = list(QURAN_CITE.scan(_chunk("Q 2:255 says", lang="grc")))
    assert cands == []


def test_out_of_range_surah_silently_drops() -> None:
    cands = list(QURAN_CITE.scan(_chunk("Q 200:1 is nonsense")))
    assert all(c.target_locator != "200:1" for c in cands)


def test_multiple_citations_in_one_chunk() -> None:
    text = (
        "Avicenna cites Q 2:255 alongside Sura 36:38 and Al-Fatihah 1:1 "
        "in his discussion of necessary being."
    )
    cands = list(QURAN_CITE.scan(_chunk(text)))
    locators = {c.target_locator for c in cands}
    # All three citations should be picked up. Note Al-Fatihah 1:1
    # produces "1:1" — same as a Q1:1 prefix form would.
    assert "2:255" in locators
    assert "36:38" in locators
    assert "1:1" in locators


def test_custom_lang_scope() -> None:
    """Per-author overrides: a caller can narrow ``langs`` to scope
    a rule at construction time."""
    rule = QuranCiteRule(langs=("ara",))
    cands_eng = list(rule.scan(_chunk("Q 2:255 cite", lang="eng")))
    cands_ara = list(rule.scan(_chunk("Q 2:255 cite", lang="ara")))
    assert cands_eng == []
    assert len(cands_ara) == 1
