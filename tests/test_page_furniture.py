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
