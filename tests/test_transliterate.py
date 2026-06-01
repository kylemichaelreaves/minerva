"""Tests for the Perseus beta-code → polytonic Unicode converter."""

from __future__ import annotations

import pytest

from minerva.transliterate import (
    betacode_to_unicode,
    display_title,
    looks_like_betacode,
)


@pytest.mark.parametrize(
    ("beta", "expected"),
    [
        # Plato titles from the live Perseus bundle.
        ("*(ippa/rxos", "Ἱππάρχος"),
        ("*qea/ghs", "Θεάγης"),
        ("*)alkibia/dhs a", "Ἀλκιβιάδης α"),
        ("*ti/maios", "Τίμαιος"),
        ("*fai=dros", "Φαῖδρος"),
        ("*kratu/los", "Κρατύλος"),
        ("*sofisth/s", "Σοφιστής"),
        ("*gorgi/as", "Γοργίας"),
        ("*)/iwn", "Ἴων"),
        # Word-final sigma collapses to ς.
        ("logos", "λογος"),
        # Trailing single-letter "α" after a space stays separate.
        ("*kri/twn a", "Κρίτων α"),
    ],
)
def test_betacode_to_unicode_handles_canonical_titles(beta, expected):
    assert betacode_to_unicode(beta) == expected


def test_looks_like_betacode_detects_diacritics_and_caps():
    # Marker characters: presence of any one triggers the check.
    assert looks_like_betacode("*sofisth/s")
    assert looks_like_betacode("a/")
    assert looks_like_betacode("a|")
    assert looks_like_betacode("a)")
    # Plain Latin / English titles must NOT be treated as beta-code,
    # because some `gr`-tagged Perseus rows ship with English titles
    # ("Letter 7", "Republic") and converting them would produce noise.
    assert not looks_like_betacode("Letter 7")
    assert not looks_like_betacode("Republic")
    assert not looks_like_betacode("Theaetetus")


def test_display_title_only_transliterates_real_betacode():
    assert display_title("*sofisth/s", "grc") == "Σοφιστής"
    # Latin "Republic" stored under lang=grc stays untouched —
    # this is the false-positive guard.
    assert display_title("Republic", "grc") == "Republic"
    # Non-Greek langs always pass through unchanged.
    assert display_title("Republic", "eng") == "Republic"
    assert display_title("Kritik der reinen Vernunft", "deu") == ("Kritik der reinen Vernunft")
    assert display_title("Phänomenologie des Geistes", "deu") == ("Phänomenologie des Geistes")


def test_betacode_to_unicode_passes_through_empty_and_punctuation():
    assert betacode_to_unicode("") == ""
    assert betacode_to_unicode("   ") == "   "
