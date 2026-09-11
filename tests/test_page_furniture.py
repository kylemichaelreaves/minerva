"""Page-furniture separation for PDF-extracted works (#533)."""

from minerva.corpus import page_furniture as pf


def test_strips_a_leading_running_head():
    text = "THE LECTURES OF 1822-3 This is the new and ultimate banner."
    assert pf.strip_running_head(text, pf.RUNNING_HEADS_LWH) == (
        "This is the new and ultimate banner."
    )


def test_running_head_strip_tolerates_ocr():
    # Real forms from work 712: 'l' for 'L', 'R' for '8', 'f' for 'F'.
    for head in ("THE lECTURES OF 1822-3", "THE LECTURES OF 1R22-3", "THE LECTURES Of 1822-3"):
        assert pf.strip_running_head(f"{head} Body text.", pf.RUNNING_HEADS_LWH) == "Body text."


def test_leaves_text_alone_when_there_is_no_running_head():
    text = "In addition ro these two large constellations in Eucope."
    assert pf.strip_running_head(text, pf.RUNNING_HEADS_LWH) == text


def test_splits_a_trailing_note_block_when_the_marker_is_present():
    # Marker '.4' upstream is what licenses treating '4.' as a note.
    text = "Caesar's Commentaries, belong here too.4 In particular. 4. On Herodotus, see the Fragment."
    body, notes = pf.split_trailing_notes(text)
    assert body == "Caesar's Commentaries, belong here too.4 In particular."
    assert notes == "4. On Herodotus, see the Fragment."


def test_refuses_to_split_when_no_marker_licenses_it():
    # Without an upstream marker this is prose, not a note. Refusing is the
    # safe direction: a bad split silently deletes Hegel.
    text = "He names three writers. 4. On Herodotus, see the Fragment."
    body, notes = pf.split_trailing_notes(text)
    assert notes is None
    assert body == text


def test_strips_a_trailing_page_number():
    assert pf.strip_trailing_page_number("…and obtain a picture of the age. 135") == (
        "…and obtain a picture of the age."
    )


def test_does_not_strip_a_number_that_ends_a_sentence():
    text = "The lectures were delivered in 1822."
    assert pf.strip_trailing_page_number(text) == text


def test_splits_when_the_marker_is_a_space_separated_token():
    # Real form from work 712 (ord 103/169/295): the superscript often lands
    # as its own whitespace-bounded token rather than glued to a word.
    text = "Reason is formation in general, thus 31 finite before the end. 31. On formation, see the essay."
    body, notes = pf.split_trailing_notes(text)
    assert body == "Reason is formation in general, thus 31 finite before the end."
    assert notes == "31. On formation, see the essay."


def test_standalone_marker_inside_a_longer_number_does_not_license_a_split():
    # '31' here is the tail of '1831', not a standalone marker — the digit
    # immediately before it rules that out. Refusing is still the safe
    # direction.
    text = "The war began in 1831 and lasted for years. 31. On formation, see the essay."
    body, notes = pf.split_trailing_notes(text)
    assert notes is None
    assert body == text


def test_strips_one_leading_page_number_before_a_running_head():
    text = "138 INTRODUCTION, 1830-1 Gentlemen, we begin today."
    assert pf.strip_running_head(text, pf.RUNNING_HEADS_LWH) == "Gentlemen, we begin today."


def test_strips_two_leading_page_numbers_before_a_running_head():
    text = "138 139 INTRODUCTION, 1830--1 Gentlemen, we begin today."
    assert pf.strip_running_head(text, pf.RUNNING_HEADS_LWH) == "Gentlemen, we begin today."


def test_refuses_a_colon_introduced_enumeration_even_when_a_marker_licenses_it():
    # Real shape from work 712, ord 461: Hegel's own three-point enumeration
    # ("...three developments ... us: 1. ... 2. ... 3. ...") coincided with
    # a bare "1" upstream that satisfied the marker check, and the split
    # ate his prose. A colon immediately before the candidate means this is
    # the author's own list, not an editor's note -- refuse regardless of
    # marker licensing.
    text = (
        "In lecture 1 Hegel introduces three developments that are of interest to us: "
        "1. By its very nature, the church acquires for itself a worldly existence. "
        "2. The principle of the modern church is of a different nature. "
        "3. This formal universality must obtain a concrete content."
    )
    body, notes = pf.split_trailing_notes(text)
    assert notes is None
    assert body == text


def test_leaves_a_table_of_contents_style_number_run_alone():
    # Three or more leading numbers is a listing (page refs in a ToC), not a
    # recto/verso page pair ahead of a running head — the cap at two keeps
    # this refused.
    text = "12 34 56 INTRODUCTION, 1830-1 Gentlemen, we begin today."
    assert pf.strip_running_head(text, pf.RUNNING_HEADS_LWH) == text


def test_splits_when_the_marker_is_glued_to_the_word_after_it():
    """#539 shape 1: the extractor renders the superscript marker glued
    FORWARD — `8To` — as often as it glues it backward (`too.4`).
    `_marker_present` required the digits to be followed by a non-word
    character, so it refused these. Measured: 2 refusals in work 712."""

    text = (
        "so it may here be presupposed as demonstrated. 8To those of you "
        "gentlemen who are not yet acquainted with philosophy. "
        "8. In the margin: Faith, survey, result."
    )
    body, notes = pf.split_trailing_notes(text)
    assert notes == "8. In the margin: Faith, survey, result."
    assert body.endswith("acquainted with philosophy.")


def test_splits_when_the_note_open_separator_is_ocr_damaged():
    """#539 shape 2: the sentinel needs a literal `.`, but the scan
    frequently renders it as a middle dot. Measured: 11 refusals."""

    text = (
        "whether it is possible to know God, as he asks here.23 "
        "And so the question stands. "
        "23 · In the margin: Apply to history - explain - human passions."
    )
    _body, notes = pf.split_trailing_notes(text)
    assert notes is not None
    assert notes.startswith("23 · In the margin")


def test_splits_when_the_note_text_begins_lower_case_after_ocr():
    """#539 shape 2, second half: `[A-Z(\\["']` after the sentinel is
    what the OCR damage breaks — `65. fn the m<Jrgin:` for "In the
    margin". Accepting a lower-case opener recovers those."""

    text = (
        "not that it is exhausted in its concrete application.65 "
        "But rather the reverse. "
        "65. fn the m<Jrgin: People deceived, war waged, Goethe."
    )
    _body, notes = pf.split_trailing_notes(text)
    assert notes is not None
    assert notes.startswith("65. fn the m<Jrgin")


def test_still_refuses_a_colon_introduced_enumeration_after_the_widening():
    """The widenings above must not reopen the case the colon guard
    exists to close: Hegel introducing his own enumeration."""

    text = "There are three developments to set out for us: 1. The first of them."
    body, notes = pf.split_trailing_notes(text)
    assert notes is None
    assert body == text


def test_still_refuses_when_nothing_licenses_a_split():
    """The widenings license *more* splits at already-valid note-opens;
    they must not license one where no marker is attested at all."""

    text = "He names three writers. 4. On Herodotus, see the Fragment."
    body, notes = pf.split_trailing_notes(text)
    assert notes is None
    assert body == text


def test_the_empty_side_guard_refuses_rather_than_emitting_an_empty_chunk(monkeypatch):
    """#538: the guard is unreachable through the public functions — its
    True branch fires 0 times across every chunk in the corpus — because
    `_marker_present` and `_NOTE_OPEN_RE` jointly guarantee both sides
    are non-empty.

    It is kept rather than deleted because #539 loosened both of those
    regexes in this same change, so the guarantees that make it dead are
    the ones just weakened. Reaching it needs the sentinel patched, which
    is the honest way to test an intentionally-unreachable guard.
    """

    import re

    # A sentinel that matches at offset 0, so `body` strips to empty.
    monkeypatch.setattr(pf, "_NOTE_OPEN_RE", re.compile(r"^(\d{1,3})\.\s+"))
    monkeypatch.setattr(pf, "_marker_present", lambda text, number, before: True)

    text = "4. On Herodotus, see the Fragment."
    body, notes = pf.split_trailing_notes(text)
    assert notes is None
    assert body == text
