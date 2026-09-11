"""Tests for `minerva.heading_clean` — the pure text-normalization
helpers that sit between PDF extraction and chunk emission. Split
from `test_corpus_parse.py` so the splitter tests stay focused on
splitting logic.

The functions still appear under `corpus.*` via re-export, so this
file uses that re-export to double-check the surface."""

from __future__ import annotations

from minerva import corpus as corpus_parse


def test_clean_heading_label_drops_letter_spaced_runs():
    # The signature pattern from PDF extraction of letter-spaced chapter titles.
    src = "T H E F I R S T P E R I O D : G R E E K P H I L O S O P H Y"
    assert corpus_parse._clean_heading_label(src) == ""


def test_clean_heading_label_normalizes_normal_headings():
    # Multi-letter words pass through but are title-cased for readability.
    assert corpus_parse._clean_heading_label("CHAPTER ONE: SOMETHING") == "Chapter One: Something"
    assert (
        corpus_parse._clean_heading_label("INDEPENDENCE AND DEPENDENCE OF SELF-CONSCIOUSNESS")
        == "Independence and Dependence of Self-consciousness"
    )


def test_clean_heading_label_strips_only_the_letter_spaced_part():
    # If a label has both well-formed words and a letter-spaced run, only
    # the run is removed and surrounding tokens / punctuation tidied.
    src = "Greek Philosophy T H E F I R S T P E R I O D"
    assert corpus_parse._clean_heading_label(src) == "Greek Philosophy"


def test_clean_heading_label_short_runs_pass_through():
    # 2 or 3 single letters in a row aren't the letter-spaced pattern —
    # these could be initials or honest abbreviations.
    assert corpus_parse._clean_heading_label("A B C") == "A B C"


def test_clean_heading_label_title_cases_all_caps():
    # Headings the LLM otherwise renders as SHOUTING in citations get
    # normalized to a readable Title Case.
    assert (
        corpus_parse._clean_heading_label("LECTURES ON THE HISTORY OF PHILOSOPHY")
        == "Lectures on the History of Philosophy"
    )
    assert (
        corpus_parse._clean_heading_label("INDEPENDENCE AND DEPENDENCE OF SELF-CONSCIOUSNESS")
        == "Independence and Dependence of Self-consciousness"
    )


def test_clean_heading_label_preserves_roman_numerals():
    assert (
        corpus_parse._clean_heading_label("VOLUME II GREEK PHILOSOPHY")
        == "Volume II Greek Philosophy"
    )


def test_clean_heading_label_keeps_proper_names_capitalized():
    # First word is always capitalized; later occurrences of articles get lowered.
    assert (
        corpus_parse._clean_heading_label("GEORG WILHELM FRIEDRICH HEGEL")
        == "Georg Wilhelm Friedrich Hegel"
    )


def test_clean_heading_label_drops_publisher_front_matter():
    # Publisher / copyright signals get dropped entirely.
    assert corpus_parse._clean_heading_label("OXFORD UNIVERSITY PRESS") == ""
    assert corpus_parse._clean_heading_label("CAMBRIDGE UNIVERSITY PRESS 2009") == ""


def test_clean_heading_label_leaves_mixed_case_unchanged():
    # If the label already has lowercase letters somewhere, treat it as
    # intentionally cased and leave it alone.
    assert corpus_parse._clean_heading_label("Already Title Case") == "Already Title Case"


def test_smart_title_case_keeps_german_articles_lowercase():
    # Useful for de-language Hegel / Kant headings normalized from caps.
    assert corpus_parse._smart_title_case("DAS WESEN DER VERNUNFT") == "Das Wesen der Vernunft"


# ---------- title-page artifact heuristics ----------


def _make_lhp2_work():
    return _make_work_full(
        title="Lectures on the History of Philosophy, Vol. II — Greek Philosophy",
        translator="Brown / Stewart",
    )


def _make_work_full(title: str, translator: str = "T", author: str = "Hegel"):
    """Build a CorpusWork with a real title (the default fixture's title is "W")."""
    from minerva.corpus_works import CorpusWork

    return CorpusWork(
        code="x",
        title=title,
        translator=translator,
        edition_year="2020",
        filenames=("x.pdf",),
        fmt="pdf",
        locator="chapter",
        lang="eng",
        corpus="hegel",
        author=author,
    )


def test_title_page_artifact_drops_translator_name():
    w = _make_lhp2_work()
    assert corpus_parse._is_title_page_artifact("Robert F. Brown", w) is True
    assert (
        corpus_parse._is_title_page_artifact(
            "Peter C. Hodgson",
            _make_work_full(
                title="Lectures on the Philosophy of World History (1822–3)",
                translator="Hodgson / Brown",
            ),
        )
        is True
    )


def test_title_page_artifact_drops_author_name():
    w = _make_lhp2_work()
    assert corpus_parse._is_title_page_artifact("Georg Wilhelm Friedrich Hegel", w) is True


def test_title_page_artifact_drops_volume_prefix():
    w = _make_lhp2_work()
    assert corpus_parse._is_title_page_artifact("Volume II Greek Philosophy", w) is True
    assert corpus_parse._is_title_page_artifact("Volume I", w) is True


def test_title_page_artifact_drops_single_title_word():
    w = _make_lhp2_work()
    # "Lectures", "History", "Philosophy" are all in the work's title.
    assert corpus_parse._is_title_page_artifact("Lectures", w) is True
    assert corpus_parse._is_title_page_artifact("History", w) is True
    assert corpus_parse._is_title_page_artifact("Philosophy", w) is True


def test_title_page_artifact_keeps_legitimate_single_word_sections():
    w = _make_lhp2_work()
    # Common section names that aren't part of the title.
    assert corpus_parse._is_title_page_artifact("Preface", w) is False
    assert corpus_parse._is_title_page_artifact("Introduction", w) is False
    assert corpus_parse._is_title_page_artifact("Conclusion", w) is False


def test_title_page_artifact_keeps_legitimate_chapter_headings():
    w = _make_lhp2_work()
    # Multi-word labels not containing an attribution surname or matching
    # the volume pattern should pass through.
    assert corpus_parse._is_title_page_artifact("Pre-Socratic Philosophy", w) is False
    assert corpus_parse._is_title_page_artifact("On the Sophists", w) is False


def test_title_page_artifact_does_not_misclassify_long_labels_with_translator_token():
    # A 6+ word chapter heading that happens to contain the surname
    # token shouldn't be dropped — unless it ALSO duplicates multiple
    # words from the work's title (which would betray a title-page
    # concatenation).
    w = _make_lhp2_work()
    long_label = "The Brown Book and Its Successors in the Tradition"
    assert corpus_parse._is_title_page_artifact(long_label, w) is False


def test_title_page_artifact_drops_concatenated_author_plus_title():
    # Author surname + multiple title words → likely a title page jam.
    w = _make_lhp2_work()
    src = "Georg Wilhelm Friedrich Hegel Lectures on the History of Philosophy"
    assert corpus_parse._is_title_page_artifact(src, w) is True


def test_garbled_letter_spacing_detected():
    # PDF extraction with partially-fused letter-spaced caps:
    # "CONTENTS" → "C Ont E N Ts", "PREFACE" → "P R E Fa C E", and various
    # mid-length variants that survive the strict regex.
    assert corpus_parse._is_garbled_letter_spacing("C Ont E N Ts") is True
    assert corpus_parse._is_garbled_letter_spacing("P R E Fa C E") is True
    assert corpus_parse._is_garbled_letter_spacing("C Ont Ent S") is True
    assert corpus_parse._is_garbled_letter_spacing("Rial Int R O Duc T I on") is True
    # Real chapter heading (not garbled).
    assert corpus_parse._is_garbled_letter_spacing("From Thales to Aristotle") is False
    # Short labels that happen to contain short words shouldn't trigger.
    assert corpus_parse._is_garbled_letter_spacing("On the Soul") is False


def test_fuse_kerned_words_collapses_letter_spaced_caps():
    # Synthesize PyMuPDF-shaped tuples: (x0, y0, x1, y1, text, block, line, word_no).
    # Kerned-cap line: gaps within "PRESOCRATICS" are small relative to char width.
    line = [
        (0.0, 0, 10.0, 10, "A.", 0, 0, 0),
        (16.0, 0, 30.0, 10, "THE", 0, 0, 1),
        (35.0, 0, 60.0, 10, "PRESO", 0, 0, 2),
        (61.0, 0, 95.0, 10, "CRATICS:", 0, 0, 3),  # 1 px gap → fuse
        (105.0, 0, 130.0, 10, "FROM", 0, 0, 4),  # ~10 px gap → keep
    ]
    out = corpus_parse._fuse_kerned_words(line)
    assert out == "A. THE PRESOCRATICS: FROM"


def test_fuse_kerned_words_leaves_mixed_case_lines_alone():
    # Body text — mixed case — should not be fused even if word gaps are tight.
    line = [
        (0.0, 0, 40.0, 10, "mentioned", 0, 0, 0),
        (41.0, 0, 50.0, 10, "by", 0, 0, 1),  # 1 px gap
        (51.0, 0, 60.0, 10, "the", 0, 0, 2),  # 1 px gap
    ]
    out = corpus_parse._fuse_kerned_words(line)
    assert out == "mentioned by the"


def test_fuse_kerned_words_handles_empty_and_single_word():
    assert corpus_parse._fuse_kerned_words([]) == ""
    assert corpus_parse._fuse_kerned_words([(0, 0, 10, 10, "ONLY", 0, 0, 0)]) == "ONLY"


def test_label_too_short_drops_fragments():
    # Multi-token fragments that don't have enough alpha chars to be useful.
    assert corpus_parse._is_label_too_short("Ed Od") is True
    assert corpus_parse._is_label_too_short("Int on") is True
    # Single-token fragments < 4 alpha chars (line-break artifacts).
    assert corpus_parse._is_label_too_short("IL") is True
    assert corpus_parse._is_label_too_short("Hy") is True
    # Real headings pass.
    assert corpus_parse._is_label_too_short("On the Soul") is False
    assert corpus_parse._is_label_too_short("I. From Thales") is False
    assert corpus_parse._is_label_too_short("Preface") is False


def test_merge_continuation_headings_collapses_letter_spaced_label():
    """End-to-end: a wrapped heading whose merged form is letter-spaced
    is reduced to an empty label so the chunk falls back to the
    work-level locator instead of carrying noise."""
    import re as _re

    text = "T H E F I R S T P E R I O D\nG R E E K P H I L O S O P H Y\nreal chapter body\n"
    # Use a simple regex to populate matches; the sanitizer is what we're testing.
    matches = list(_re.finditer(r"(?m)^([A-Z][A-Z ]+)$", text))
    merged = corpus_parse._merge_continuation_headings(text, matches)
    assert len(merged) >= 1
    # Letter-spaced content collapses to empty after cleanup.
    assert merged[0][2] == ""


# ---------- editorial-heading detector ----------


def test_editorial_heading_catches_clean_labels():
    # Canonical headings that label editor / translator apparatus.
    assert corpus_parse._is_editorial_heading("Editorial Introduction") is True
    assert corpus_parse._is_editorial_heading("Editor's Introduction") is True
    assert corpus_parse._is_editorial_heading("Translator's Preface") is True
    assert corpus_parse._is_editorial_heading("Translator's Introduction") is True
    assert corpus_parse._is_editorial_heading("List of Abbreviations") is True
    assert corpus_parse._is_editorial_heading("Glossary") is True
    assert corpus_parse._is_editorial_heading("Bibliography") is True
    assert corpus_parse._is_editorial_heading("Contents") is True
    assert corpus_parse._is_editorial_heading("Foreword") is True
    assert corpus_parse._is_editorial_heading("Acknowledgments") is True
    assert corpus_parse._is_editorial_heading("Name Index") is True
    assert corpus_parse._is_editorial_heading("Subject Index") is True


def test_editorial_heading_catches_ocr_variants():
    # Real OCR-mangled forms observed in LHP Vol I when extracting from
    # the Brown/Stewart PDF. Normalization (strip non-letters, lowercase)
    # collapses them to "editorialintroduction" etc.
    assert corpus_parse._is_editorial_heading("Editorial Intr O Duction") is True
    assert corpus_parse._is_editorial_heading("Editori a L Intro Duction") is True
    assert corpus_parse._is_editorial_heading("Editor Ial Intr O Duction") is True
    assert corpus_parse._is_editorial_heading("E Ditori a L Intr O Duction") is True
    assert corpus_parse._is_editorial_heading("Editorialintroduction") is True
    assert corpus_parse._is_editorial_heading("Listof Abbreviations") is True


def test_editorial_heading_catches_ocr_letter_substitution():
    # Spacing damage was already handled; letter substitution was not.
    # Both labels are real, from work 712 (Hegel, Lectures on the
    # Philosophy of World History), ords 10 and 475.
    assert corpus_parse._is_editorial_heading("Editorial Introouctjon") is True
    assert corpus_parse._is_editorial_heading("Bjbljography") is True


def test_editorial_heading_fuzzy_does_not_fire_on_real_headings():
    # The length>=12 floor is load-bearing: _EDITORIAL_PHRASES holds short
    # substring-matched entries ("contents", "glossary", "foreword") that
    # would otherwise fuzzy-match ordinary chapter titles.
    for label in [
        "The Consummate Religion",
        "Conscience",
        "The Content of Religion",
        "Second Part: Determinate Religion",
        "The Oriental World",
        "Introduction",
        "Preface",
    ]:
        assert corpus_parse._is_editorial_heading(label) is False, label


def test_editorial_heading_fuzzy_rejects_truncated_labels():
    # Truncation, not substitution. Too short to tell from a real heading,
    # so deliberately NOT matched.
    assert corpus_parse._is_editorial_heading("Editoria L Int") is False


def test_editorial_heading_catches_compound_labels():
    # PDF extraction often jams adjacent front-matter heads into one
    # `_HEADING_RE` match. The detector should still fire on these.
    assert corpus_parse._is_editorial_heading("Contents Preface") is True
    assert (
        corpus_parse._is_editorial_heading(
            "Bibliography of Hegel's Sources for the Introduction and Oriental Philosophy"
        )
        is True
    )
    assert (
        corpus_parse._is_editorial_heading("Glossary Selected Bibliography General Index Contents")
        is True
    )


def test_editorial_heading_catches_editorial_notes():
    # Added so the EPUB spine filter can detect the back-matter
    # "Editorial notes" section header (PR EPUB spine[31]).
    assert corpus_parse._is_editorial_heading("Editorial notes") is True
    assert corpus_parse._is_editorial_heading("Editorial Note") is True


def test_editorial_heading_keeps_legitimate_hegel_headings():
    # Hegel himself writes prefaces and introductions — these must NOT
    # be dropped or we'd lose the PhG / PR Vorrede.
    assert corpus_parse._is_editorial_heading("Preface") is False
    assert corpus_parse._is_editorial_heading("Introduction") is False
    assert corpus_parse._is_editorial_heading("Vorrede") is False
    assert corpus_parse._is_editorial_heading("Einleitung") is False
    # Real chapter heads.
    assert corpus_parse._is_editorial_heading("Chapter One") is False
    assert corpus_parse._is_editorial_heading("I. The Sophists") is False
    assert corpus_parse._is_editorial_heading("Sense-Certainty") is False
    assert corpus_parse._is_editorial_heading("") is False


def test_merge_continuation_headings_still_joins_distinct_continuations():
    """Continuation lines that aren't duplicates should still be joined."""
    import re as _re

    text = "FIRST PART OF A WRAPPED HEADING\nSECOND PART OF SAME HEADING\nactual body content\n"
    matches = list(_re.finditer(r"(?m)^([A-Z][A-Z ]+)$", text))
    merged = corpus_parse._merge_continuation_headings(text, matches)
    assert len(merged) == 1
    assert merged[0][2] == "First Part of a Wrapped Heading Second Part of Same Heading"
