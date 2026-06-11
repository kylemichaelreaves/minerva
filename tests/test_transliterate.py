"""Tests for the Perseus beta-code → polytonic Unicode converter."""

from __future__ import annotations

import pytest

from minerva.transliterate import (
    betacode_to_unicode,
    display_text,
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


# ---------- looks_like_betacode false-positive guards ----------
# The old heuristic triggered on ANY of `*()/\=|+`, so already-Unicode
# polytonic Greek containing a parenthesis or slash got every ASCII
# letter inside it converted to Greek — at display time (every grc
# chunk passes through `reader/queries.py`'s display_text call) AND at
# ingest (`tei.py`'s _flush hook).


@pytest.mark.parametrize(
    "text",
    [
        # Parenthetical inside polytonic Greek.
        "ἐν ἀρχῇ ἦν ὁ λόγος (καὶ ὁ λόγος ἦν πρὸς τὸν θεόν)",
        # Slash-separated variant readings.
        "λόγος/μῦθος",
        # '+' used as an editorial crux marker.
        "ἀρετὴ + σοφία",
        # Monotonic (Greek and Coptic block) with parens.
        "η αρετή (η σοφία)",
    ],
)
def test_unicode_greek_with_marker_punctuation_is_not_betacode(text):
    assert not looks_like_betacode(text)
    assert display_text(text, "grc") == text


def test_latin_sigla_inside_greek_text_survive():
    # The mixed case from real apparatus: a Latin abbreviation inside
    # an already-Unicode Greek chunk. Under the old any-marker check the
    # '(' triggered conversion and "cf." became Greek gibberish.
    text = "τὸ ἀγαθόν (cf. Resp. 509d)"
    assert not looks_like_betacode(text)
    assert display_text(text, "grc") == text


def test_genuine_betacode_still_converts():
    # Real beta-code keeps converting: letter+diacritic sequences and
    # '*' capital markers are positive evidence.
    assert looks_like_betacode("*(ippa/rxos")
    assert looks_like_betacode("e)n a)rxh=| h)=n o( lo/gos")
    assert display_text("*sofisth/s", "grc") == "Σοφιστής"
    assert betacode_to_unicode("e)n a)rxh=|") == display_text("e)n a)rxh=|", "grc")


def test_marker_without_letter_context_is_not_betacode():
    # A marker with no beta-code letter attached is not evidence:
    # digits-and-punctuation strings pass through.
    assert not looks_like_betacode("(7)")
    assert not looks_like_betacode("3 + 4 = 7")
    assert not looks_like_betacode("|||")
