"""Tests for the chronological author + canonical book ordering used
by the ``/api/works`` Read-tab list."""

from __future__ import annotations

from itertools import pairwise

from minerva.author_ordering import (
    AUTHOR_ORDINAL,
    LANG_ORDINAL,
    author_sort_key,
    lang_sort_key,
)


def test_pre_socratics_precede_plato() -> None:
    # Every Phase-1 pre-Socratic sorts before Plato.
    presocratics = [
        "Thales",
        "Anaximander",
        "Anaximenes",
        "Pythagoras",
        "Xenophanes",
        "Heraclitus",
        "Parmenides",
        "Zeno of Elea",
        "Empedocles",
        "Anaxagoras",
        "Melissus",
        "Diogenes of Apollonia",
    ]
    plato = author_sort_key("Plato")
    for name in presocratics:
        assert author_sort_key(name) < plato, name


def test_canonical_chronological_sequence() -> None:
    sequence = [
        "Homer",
        "Thales",
        "Heraclitus",
        "Plato",
        "Aristotle",
        "Septuagint",
        "New Testament",
        "Vulgate",
        "Augustine",
        "Aquinas",
        "Descartes",
        "Hobbes",
        "Pascal",
        "Spinoza",
        "Locke",
        "Hume",
        "Rousseau",
        "Kant",
        "Hegel",
    ]
    keys = [author_sort_key(a) for a in sequence]
    assert keys == sorted(keys), (
        "expected sequence to be strictly chronological; got "
        + repr(list(zip(sequence, keys, strict=True)))
    )


def test_unknown_author_sorts_last() -> None:
    assert author_sort_key("Nobody") > author_sort_key("Hegel")


def test_lang_source_first() -> None:
    # Greek and Latin (the two source languages we ingest from) sort
    # before the translation languages.
    assert lang_sort_key("grc") < lang_sort_key("eng")
    assert lang_sort_key("lat") < lang_sort_key("deu")
    assert lang_sort_key("deu") < lang_sort_key("eng")


def test_ordinals_have_room_to_insert() -> None:
    # Gaps of at least 5 between consecutive sorted ordinals leave
    # room to slot new authors without renumbering. Catches accidental
    # off-by-one packing of the table.
    sorted_keys = sorted(AUTHOR_ORDINAL.values())
    for a, b in pairwise(sorted_keys):
        assert b - a >= 5, f"ordinals too tight near {a} → {b}"


def test_lang_ordinal_covers_corpus_languages() -> None:
    # All five languages that ingest currently produces must have an
    # ordinal — missing ones would silently sort to the end.
    for lang in ("grc", "lat", "deu", "fra", "eng"):
        assert lang in LANG_ORDINAL, f"{lang} missing from LANG_ORDINAL"
