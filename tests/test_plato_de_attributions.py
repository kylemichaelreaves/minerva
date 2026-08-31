"""Title-page attributions for the German Plato volume (#206).

The splitter used to take one translator per work from a seven-entry override
table and fall back to `("Friedrich Schleiermacher", "1818")` for everything
else. The fallback was silent, so 41 of 48 works got a confident attribution
nobody had checked — and it was wrong far more often than #206 knew.

The volume states its own attributions, once per work, in a fixed formula:

    Nach der Übersetzung von <translator> in: <edition>, <city> <year>, bearbeitet.

`_ATTRIBUTION` transcribes those, each entry carrying the PDF page its formula
appears on so the claim is checkable against the source. These tests pin the
transcription, the two-translator Politeia, and — most importantly — that an
unlisted work now raises instead of defaulting.
"""

from __future__ import annotations

import pytest

from minerva.corpus.split_platon_werke import (
    _ATTRIBUTION,
    attribution_for,
)


def who(work: str, book: str | None = None) -> tuple[str, str]:
    """(translator, year) — `Attribution` also carries the source page, which
    is provenance rather than part of the claim under test."""
    a = attribution_for(work, book)
    return (a.translator, a.year)


class TestTheRecordedAttributions:
    def test_politeia_is_teuffel_for_the_first_five_books(self) -> None:
        # p779: "Nach der Übersetzung der Bücher I-V von Wilhelm Siegmund
        # Teuffel und der Bücher VI-X von Wilhelm Wiegand in: Platon's Werke.
        # Zehn Bücher vom Staate. Stuttgart, 1855"
        for book in ("1", "2", "3", "4", "5"):
            assert who("Politeia", book) == ("Wilhelm Siegmund Teuffel", "1855"), book

    def test_politeia_is_wiegand_for_the_last_five(self) -> None:
        for book in ("6", "7", "8", "9", "10"):
            assert who("Politeia", book) == ("Wilhelm Wiegand", "1855"), book

    def test_the_letters_are_wiegand_not_schleiermacher(self) -> None:
        """p1342: "nach der Übersetzung von Dr. Wilhelm Wiegand in: Platon's
        Werke, Fünfte Gruppe: Zweifelhaftes und Unächtes … Stuttgart, 1859".

        All 13 were attributed to Schleiermacher 1818 by the fallback — a wrong
        *translator*, not merely a wrong year, and not something #206 mentioned.
        """
        for n in ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII"):
            assert who(f"Epistole {n}") == ("Wilhelm Wiegand", "1859"), n

    @pytest.mark.parametrize(
        ("work", "translator", "year"),
        [
            # The two the old table already had right.
            ("Phaidros", "Ludwig Georgii", "1853"),
            ("Epinomis", "Franz Susemihl", "1863"),
            # Susemihl's other volumes are each a different year; the old code
            # gave all of them 1863.
            ("Symposion", "Franz Susemihl", "1855"),
            ("Timaios", "Franz Susemihl", "1856"),
            ("Kritias", "Franz Susemihl", "1857"),
            ("Parmenides", "Franz Susemihl", "1865"),
            # Only these two Schleiermacher dialogues are actually 1818.
            ("Euthyphron", "Friedrich Schleiermacher", "1818"),
            ("Apologia", "Friedrich Schleiermacher", "1818"),
            # The rest are later Auflagen — 41 works carried a flat 1818.
            ("Kriton", "Friedrich Schleiermacher", "1855"),
            ("Phaidon", "Friedrich Schleiermacher", "1861"),
            ("Kratylos", "Friedrich Schleiermacher", "1857"),
            ("Alkibiades I", "Friedrich Schleiermacher", "1826"),
            ("Alkibiades II", "Friedrich Schleiermacher", "1855"),
            ("Hippias Meizon", "Friedrich Schleiermacher", "1861"),
            ("Hippias Elatton", "Friedrich Schleiermacher", "1855"),
        ],
    )
    def test_transcribed_from_the_title_page(self, work, translator, year) -> None:
        assert who(work) == (translator, year)

    def test_every_work_the_volume_contains_is_recorded(self) -> None:
        # 35 dialogues (Alkibiades I/II counted separately) + 13 Letters = 48,
        # which is exactly the number of German Plato works in the index. If
        # this moves, a work was added or lost.
        assert len(_ATTRIBUTION) == 48

    def test_every_entry_cites_the_page_it_was_read_from(self) -> None:
        """Provenance, so a future reader can check the transcription instead of
        trusting it."""
        for work, attr in _ATTRIBUTION.items():
            assert attr.source_page > 0, work

    def test_no_entry_is_the_old_flat_default(self) -> None:
        """A regression guard with teeth: the bug was 41 works sharing
        ("Friedrich Schleiermacher", "1818"). Only two should now."""
        flat = [
            w
            for w, a in _ATTRIBUTION.items()
            if a.translator == "Friedrich Schleiermacher" and a.year == "1818"
        ]
        assert sorted(flat) == ["Apologia", "Euthyphron"]


class TestTheFallbackIsGone:
    def test_an_unrecorded_work_raises_instead_of_defaulting(self) -> None:
        """The underlying problem. An unlisted work used to receive a confident
        Schleiermacher 1818; now the ingest stops and says what to do."""
        with pytest.raises(ValueError, match="no title-page attribution"):
            attribution_for("Kleitophon II")

    def test_the_error_names_the_work_and_the_remedy(self) -> None:
        with pytest.raises(ValueError) as exc:
            attribution_for("Definitiones")
        msg = str(exc.value)
        assert "Definitiones" in msg
        assert "title page" in msg

    def test_politeia_without_a_book_raises_rather_than_guessing(self) -> None:
        """Its translator is a function of the book. A chunk that reached here
        with no book means the book-boundary scan failed, and picking either
        translator would bury that."""
        with pytest.raises(ValueError, match="book"):
            attribution_for("Politeia", None)

    def test_politeia_with_a_book_outside_i_to_x_raises(self) -> None:
        with pytest.raises(ValueError, match="book"):
            attribution_for("Politeia", "11")
