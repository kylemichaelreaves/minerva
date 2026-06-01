"""Tests for minerva.lemmatize.is_valid_lemma.

The filter sits between spaCy/Stanza tokenization and the chunk_lemmas
write path. Each test case below is a real lemma observed in the
corpus before the filter landed (sorted-alpha view of the German
concordance was full of these). New observed-junk patterns should be
added here so future filter changes don't regress them.
"""

from __future__ import annotations

import pytest

from minerva.lemmatize import is_valid_lemma

# ──────────────────────────────────────────────────────────────────
#  Rejects — noise that polluted the concordance
# ──────────────────────────────────────────────────────────────────

REJECT_CASES = [
    pytest.param("", id="empty-string"),
    # Pure punctuation
    pytest.param("$", id="single-dollar"),
    pytest.param("--", id="double-dash"),
    pytest.param("(=", id="open-equals"),
    pytest.param("'s", id="contraction-tail"),
    pytest.param("-^", id="dash-caret"),
    pytest.param("^", id="caret-only"),
    # Numeric / numeric-leading
    pytest.param("+20", id="plus-number"),
    pytest.param("-3", id="dash-number"),
    pytest.param("0", id="zero"),
    pytest.param("123", id="pure-digits"),
    # Line-break artifacts (leading hyphen)
    pytest.param("-begriff", id="line-break-begriff"),
    pytest.param("-instinkt", id="line-break-instinkt"),
    pytest.param("-bewegung", id="line-break-bewegung"),
    # Scan/OCR junk that starts with a letter but contains symbols
    pytest.param("A.", id="letter-period"),
    pytest.param("A0", id="letter-digit"),
    pytest.param("A11", id="letter-digits"),
    pytest.param("A=25", id="letter-equals-number"),
    pytest.param("A.smith", id="letter-period-letter"),
]


@pytest.mark.parametrize("lemma", REJECT_CASES)
def test_rejects_junk(lemma: str) -> None:
    assert not is_valid_lemma(lemma), f"{lemma!r} should be rejected"


# ──────────────────────────────────────────────────────────────────
#  Accepts — real lemmas that must survive the filter
# ──────────────────────────────────────────────────────────────────

ACCEPT_CASES = [
    # Multi-letter words across the corpus languages
    pytest.param("sprechen", id="german-verb"),
    pytest.param("Geist", id="german-noun"),
    pytest.param("Über", id="german-umlaut-leading"),
    pytest.param("Äußerung", id="german-umlaut-and-eszett"),
    pytest.param("Wesen", id="german-content-word"),
    pytest.param("essence", id="english-content-word"),
    pytest.param("ὕβρις", id="greek-polytonic"),
    pytest.param("Οἰδίπους", id="greek-proper-noun-capital"),
    pytest.param("conferre", id="latin-verb"),
    # Single-letter words — Greek articles, Latin prepositions
    pytest.param("ὁ", id="greek-article-masc"),
    pytest.param("ἡ", id="greek-article-fem"),
    pytest.param("a", id="latin-preposition-a"),
    pytest.param("e", id="latin-preposition-e"),
    # Hyphenated compounds (mid-word hyphen, not leading)
    pytest.param("black-box", id="hyphenated-compound"),
    pytest.param("Sturm-und-Drang", id="german-multi-hyphen"),
    # Apostrophe variants
    pytest.param("O'Connor", id="apostrophe-name"),
    pytest.param("ἐλθʼ", id="greek-modifier-apostrophe"),
]


@pytest.mark.parametrize("lemma", ACCEPT_CASES)
def test_accepts_real_words(lemma: str) -> None:
    assert is_valid_lemma(lemma), f"{lemma!r} should be accepted"


# ──────────────────────────────────────────────────────────────────
#  Specific regression: the user-reported "All German A→Z" sort
# ──────────────────────────────────────────────────────────────────


def test_concordance_alpha_sort_head_is_clean() -> None:
    """The exact patterns the user saw at the top of the alphabetical
    German concordance — `$`, `'s`, `(=`, `+20`, `--`, `-begriff`,
    `-instinkt` — all reject. This is the concrete regression guard."""

    user_reported_junk = ("$", "'s", "(=", "+20", "--", "-begriff", "-instinkt")
    for lemma in user_reported_junk:
        assert not is_valid_lemma(lemma), (
            f"Regression: {lemma!r} crept back into the concordance"
        )
