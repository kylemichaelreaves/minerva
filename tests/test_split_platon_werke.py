"""Core logic of the German Plato splitter (no PDF needed — the text
helpers are exercised directly)."""

from __future__ import annotations

import pytest

from minerva.corpus.split_platon_werke import _emit_sections, _resolve_heading


def test_resolve_heading_known_dialogue():
    assert _resolve_heading("EUTHYPHRON.\n(De Sancto)\n", 0) == "Euthyphron"
    assert _resolve_heading("POLITEIA\n", 0) == "Politeia"
    assert _resolve_heading("NOMOI\nERSTES BUCH\n", 0) == "Nomoi"


def test_resolve_heading_alkibiades_i_then_ii():
    assert _resolve_heading("ALKIBIADES.\n", 0) == "Alkibiades I"
    assert _resolve_heading("ALKIBIADES.\n", 1) == "Alkibiades II"


def test_resolve_heading_brief_ordinals():
    assert _resolve_heading("SIEBENTER BRIEF\n", 0) == "Epistole VII"
    assert _resolve_heading("ERSTER BRIEF\n", 0) == "Epistole I"
    assert _resolve_heading("DREIZEHNTER BRIEF\n", 0) == "Epistole XIII"


def test_resolve_heading_ignores_non_work_lines():
    # book/speaker/section-divider headings must not start a work
    assert _resolve_heading("ERSTES BUCH ÜBER DIE GESETZE\n", 0) is None
    assert _resolve_heading("SOKRATES: und so weiter\n", 0) is None
    assert _resolve_heading("DIE BRIEFE\n", 0) is None
    assert _resolve_heading("gewöhnlicher Fließtext ohne Überschrift.\n", 0) is None


def test_emit_sections_reconstructs_stephanus():
    # [2 St.1 A] opens page 2 §a; [B]/[C] change section on the page;
    # [3 St.1 A] moves to page 3 §a. Text before the first marker (the
    # heading) is dropped.
    body = (
        "EUTHYPHRON.\n"
        "[2 St.1 A]\nWas hat sich ereignet, o Sokrates? "
        "[B]\nDenn du pflegst doch. "
        "[C]\nEin Prozess, sagst du? "
        "[3 St.1 A]\nEin ganz neuer."
    )
    chunks = list(
        _emit_sections(body, work_title="Euthyphron", source_file="Platon_Werke.pdf")
    )
    locs = [c.section for c in chunks]
    assert locs == ["2a", "2b", "2c", "3a"]
    first = chunks[0]
    assert first.work == "Euthyphron"
    assert first.lang == "deu"
    # Read from the title-page table now rather than injected, so this also
    # pins that Euthyphron really is the 1818 second edition (#206).
    assert first.translator == "Friedrich Schleiermacher"
    assert first.edition_year == "1818"
    assert first.citation_system == "stephanus"
    assert first.title_local is None
    assert "Was hat sich ereignet" in first.text
    assert "EUTHYPHRON." not in first.text  # heading dropped
    # markers are stripped from the emitted prose
    assert "[" not in first.text


def test_emit_sections_newline_split_marker():
    # markers broken across a line break (the PDF's text layer does this)
    body = "[2 \nSt.1 A]\nHallo Welt. [B]\nmehr Text."
    chunks = list(
        _emit_sections(body, work_title="Kriton", source_file="x.pdf")
    )
    assert [c.section for c in chunks] == ["2a", "2b"]


def test_emit_sections_stable_chunk_ids():
    body = "[5 St.1 A]\nText eins. [B]\nText zwei."
    a = list(_emit_sections(body, work_title="Ion", source_file="x.pdf"))
    b = list(_emit_sections(body, work_title="Ion", source_file="x.pdf"))
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]
    assert a[0].chunk_id != a[1].chunk_id


# ── book stamping (#201) ───────────────────────────────────────────────
# Only the Politeia (10 books) and the Nomoi (12) are divided into books.
# Every German chunk of both carried `book IS NULL` while the Greek and
# English sides were populated, so citations lost their "(Bk N)" and the
# new book_recall metric scored a correct hit as a miss.


def test_single_book_dialogue_has_no_book():
    """A dialogue with no book headings must stay NULL — that is what the
    Greek and English sides store for it too."""

    body = "[2 St.1 A]\nWas hat sich ereignet? [B]\nDenn du pflegst doch."
    chunks = list(
        _emit_sections(body, work_title="Euthyphron", source_file="x.pdf")
    )
    assert [c.book for c in chunks] == [None, None]


def test_book_headings_stamp_and_are_stripped_from_prose():
    body = (
        "Erstes Buch vom Staate.\n"
        "[327 St.2 A]\nIch ging gestern hinab. [B]\nUnd wir gingen.\n"
        "Zweites Buch vom Staate.\n"
        "[357 St.2 A]\nAls ich dies gesagt hatte."
    )
    chunks = list(
        _emit_sections(body, work_title="Politeia", source_file="x.pdf")
    )
    by_section = {c.section: c for c in chunks}
    assert by_section["327a"].book == "1"
    # The heading sits inside 327b's segment, closing book 1 — the section
    # it interrupts belongs to the OUTGOING book, and only what follows
    # the next marker is book 2.
    assert by_section["327b"].book == "1"
    assert by_section["357a"].book == "2"
    # The heading is structure, not prose.
    assert "Zweites Buch" not in by_section["327b"].text
    assert "Und wir gingen" in by_section["327b"].text


def test_politeia_chunks_carry_the_translator_of_their_own_book():
    """The two-translator split, through the real emit path (#206).

    Teuffel for I-V and Wiegand for VI-X, per the work's title page. This is
    what makes two `translations` rows correct rather than one naming both:
    the chunks themselves know which half they belong to, and
    `chunks.translation_id` is per-chunk.
    """
    # The whole chain from book 1: `_book_boundaries` accepts a heading only
    # when it numbers the book after the last accepted one, so a body starting
    # mid-work yields no boundaries at all. A real Politeia body always runs
    # from Erstes Buch, and the fixture has to as well.
    ordinals = ["Erstes", "Zweites", "Drittes", "Viertes", "Fünftes", "Sechstes"]
    pages = [327, 357, 392, 419, 449, 484]
    body = "".join(
        f"{ordinal} Buch vom Staate.\n[{page} St.2 A]\nText von Buch {i + 1}.\n"
        for i, (ordinal, page) in enumerate(zip(ordinals, pages, strict=True))
    )
    by_section = {
        c.section: c
        for c in _emit_sections(body, work_title="Politeia", source_file="x.pdf")
    }

    assert by_section["449a"].book == "5"
    assert by_section["449a"].translator == "Wilhelm Siegmund Teuffel"
    assert by_section["484a"].book == "6"
    assert by_section["484a"].translator == "Wilhelm Wiegand"
    # One edition, so one year on both sides of the seam.
    assert by_section["449a"].edition_year == "1855"
    assert by_section["484a"].edition_year == "1855"


def test_a_work_with_no_recorded_attribution_stops_the_ingest():
    """The silent fallback is gone. A new dialogue must have its title page
    read before it can be ingested, rather than inheriting a wrong one."""
    body = "[1 St.1 A]\nIrgendein Text ohne Zuschreibung."
    with pytest.raises(ValueError, match="no title-page attribution"):
        list(_emit_sections(body, work_title="Definitiones", source_file="x.pdf"))


def test_table_of_contents_lines_are_not_book_boundaries():
    """Each work's title page carries a clickable contents list of every
    book as a bare 'Erstes Buch' … 'Zehntes Buch', and that page is inside
    the work's own span. Matching those would stamp the entire Politeia
    with the LAST book in the list."""

    body = (
        "POLITEIA\nDer Staat.\n"
        "Erstes Buch\nZweites Buch\nDrittes Buch\nZehntes Buch\n"
        "Erstes Buch vom Staate.\n"
        "[327 St.2 A]\nIch ging gestern hinab."
    )
    chunks = list(
        _emit_sections(body, work_title="Politeia", source_file="x.pdf")
    )
    assert [c.book for c in chunks] == ["1"]


def test_repeated_heading_does_not_advance_the_book():
    """A running header repeating the current book's heading must not be
    read as a new boundary."""

    body = (
        "Erstes Buch vom Staate.\n"
        "[327 St.2 A]\nIch ging gestern hinab.\n"
        "Erstes Buch vom Staate.\n"
        "[328 St.2 A]\nUnd wir gingen hinab."
    )
    chunks = list(
        _emit_sections(body, work_title="Politeia", source_file="x.pdf")
    )
    assert [c.book for c in chunks] == ["1", "1"]


def test_nomoi_heading_form_is_recognized():
    """The Nomoi spells its headings differently from the Politeia —
    uppercase, and qualified 'ÜBER DIE GESETZE' rather than 'vom Staate'."""

    body = (
        "ERSTES BUCH ÜBER DIE GESETZE\n"
        "[624 St.2 A]\nEin Gott. \n"
        "ZWEITES BUCH ÜBER DIE GESETZE\n"
        "[652 St.2 A]\nWas nun folgt."
    )
    chunks = list(
        _emit_sections(body, work_title="Nomoi", source_file="x.pdf")
    )
    assert [(c.section, c.book) for c in chunks] == [("624a", "1"), ("652a", "2")]
