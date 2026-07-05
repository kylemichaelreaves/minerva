"""Canonical Plato title map (authors/plato_titles)."""

from __future__ import annotations

from minerva.authors import plato_titles as pt


def test_canonical_count_is_48():
    # 33 split dialogues + Republic + Laws + 13 Letters.
    assert len(pt.CANONICAL) == 48
    assert len(set(pt.CANONICAL)) == 48  # no dupes


def test_beta_code_and_english_map_to_same_canonical():
    for raw_grc, raw_en, canon in [
        ("*eu)qu/frwn", "Euthyphro", "Euthyphron"),
        ("*politiko/s", "Statesman", "Politikos"),
        ("*sumposi/on", "Symposium", "Symposion"),
    ]:
        assert pt.canonical_for(raw_grc) == canon
        assert pt.canonical_for(raw_en) == canon


def test_already_unified_and_letters():
    assert pt.canonical_for("Republic") == "Politeia"
    assert pt.canonical_for("Laws") == "Nomoi"
    assert pt.canonical_for("Letter 7") == "Epistole VII"
    assert pt.canonical_for("Letter 1") == "Epistole I"


def test_german_headings_including_variants():
    assert pt.canonical_for("POLITEIA") == "Politeia"
    assert pt.canonical_for("HIPPIAS  MAIOR.") == "Hippias Meizon"  # double space + period
    assert pt.canonical_for("AMATORES") == "Erastai"
    assert pt.canonical_for("APOLOGIA SOCRATIS") == "Apologia"


def test_local_title_only_english():
    assert pt.local_title("Politeia", "eng") == "Republic"
    assert pt.local_title("Politikos", "eng") == "Statesman"
    assert pt.local_title("Euthyphron", "grc") is None
    assert pt.local_title("Euthyphron", "deu") is None


def test_unknown_returns_none():
    assert pt.canonical_for("Nicomachean Ethics") is None
    assert pt.canonical_for("") is None
    assert pt.canonical_for(None) is None
