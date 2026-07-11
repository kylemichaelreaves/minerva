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


def test_local_title_english():
    assert pt.local_title("Politeia", "eng") == "Republic"
    assert pt.local_title("Politikos", "eng") == "Statesman"
    # Display corrections: Roman numerals for Alcibiades + Letters, and the
    # Epinomis subtitle dropped.
    assert pt.local_title("Alkibiades I", "eng") == "Alcibiades I"
    assert pt.local_title("Alkibiades II", "eng") == "Alcibiades II"
    assert pt.local_title("Epinomis", "eng") == "Epinomis"
    assert pt.local_title("Epistole VII", "eng") == "Letter VII"
    assert pt.local_title("Epistole XIII", "eng") == "Letter XIII"


def test_local_title_german():
    # Conventional German titles where they differ from the Greek name…
    assert pt.local_title("Politeia", "deu") == "Der Staat"
    assert pt.local_title("Nomoi", "deu") == "Die Gesetze"
    assert pt.local_title("Politikos", "deu") == "Der Staatsmann"
    assert pt.local_title("Sophistes", "deu") == "Der Sophist"
    assert pt.local_title("Symposion", "deu") == "Das Gastmahl"
    assert pt.local_title("Apologia", "deu") == "Apologie des Sokrates"
    # …else the Greek name (no override), and the Greek original never has one.
    assert pt.local_title("Kriton", "deu") is None
    assert pt.local_title("Euthyphron", "grc") is None


def test_corrected_display_forms_still_recognized():
    # The cleaner display strings must also resolve back to canonical, so a
    # future source that stores them ingests correctly.
    assert pt.canonical_for("Alcibiades I") == "Alkibiades I"
    assert pt.canonical_for("Epinomis") == "Epinomis"


def test_unknown_returns_none():
    assert pt.canonical_for("Nicomachean Ethics") is None
    assert pt.canonical_for("") is None
    assert pt.canonical_for(None) is None
