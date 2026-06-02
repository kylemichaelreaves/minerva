"""Orthographic canonicalization for normalized full-text search."""

from __future__ import annotations

from minerva import orthography


def test_german_th_fold():
    # The triggering case: historical -th- vs. modernized -t-.
    assert orthography.canonicalize("Mißrathenen", "deu") == "missratenen"
    assert orthography.canonicalize("Muth", "deu") == "mut"
    assert orthography.canonicalize("thun", "deu") == "tun"
    assert orthography.canonicalize("Werth", "deu") == "wert"


def test_german_is_symmetric():
    # The whole point: historical and modern spellings collapse to the
    # same canonical form, so either side of the index/query divide
    # matches the other.
    assert orthography.canonicalize("Muth", "deu") == orthography.canonicalize("Mut", "deu")
    assert orthography.canonicalize("Mißrathenen", "deu") == orthography.canonicalize(
        "Mißratenen", "deu"
    )


def test_german_eszett_ey_iren():
    assert orthography.canonicalize("Maß", "deu") == "mass"
    assert orthography.canonicalize("Seyn", "deu") == "sein"
    assert orthography.canonicalize("studiren", "deu") == "studieren"
    # bare "Iren" (the Irish) must NOT become "ieren"
    assert orthography.canonicalize("Iren", "deu") == "iren"


def test_canonicalize_preserves_a_full_sentence():
    src = "Was bedeutet der Muth zur Wahrheit?"
    assert orthography.canonicalize(src, "deu") == "was bedeutet der mut zur wahrheit?"


def test_language_scoped():
    # Must NOT fire for English/Latin or it mangles "with" -> "wit".
    assert orthography.canonicalize("with method", "eng") == "with method"
    assert orthography.canonicalize("with method", "lat") == "with method"
    assert orthography.canonicalize("with method", None) == "with method"
    assert not orthography.has_canonicalizer("eng")
    assert orthography.has_canonicalizer("deu")


def test_canonicalize_empty():
    assert orthography.canonicalize("", "deu") == ""
