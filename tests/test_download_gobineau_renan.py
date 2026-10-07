"""The Gobineau/Renan downloader: which scan is which tome, and the cut (#742).

The four Gobineau files were labelled ``vol1``..``vol4`` from the ``01``..``04``
in archive.org's ``essaisurlingali0Ngobigoog`` ids — Google disambiguators,
not volume numbers. The corpus held Tome IV twice, Tome II from a corrupt
scan, and no Tome III. Each tome is now pinned to a scan whose title page
says which tome it is, and the cleaner checks the title page before it
writes anything.

Fixtures under ``tests/fixtures/gobineau/`` are the first lines of each
archive.org ``_djvu.txt`` verbatim, so these run where ``data/`` does not
exist. Network is never touched.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

PERSEUS = Path(__file__).resolve().parents[1] / "perseus"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gobineau"


@pytest.fixture(autouse=True)
def _perseus_on_path():
    sys.path.insert(0, str(PERSEUS))
    try:
        yield
    finally:
        sys.path.remove(str(PERSEUS))
        for name in list(sys.modules):
            if name in {"_download", "download_gobineau_renan"}:
                del sys.modules[name]


def _mod():
    return importlib.import_module("download_gobineau_renan")


def _tome(n: int):
    (tome,) = [t for t in _mod().GOBINEAU_TOMES if t.number == n]
    return tome


def _head(n: int) -> str:
    (path,) = FIXTURES.glob(f"tome{n}_*_head.txt")
    return path.read_text(encoding="utf-8")


# --- Which scan is which tome ---------------------------------------------------


def test_each_tome_is_its_own_first_edition_scan():
    tomes = {t.number: (t.item, t.out) for t in _mod().GOBINEAU_TOMES}
    assert tomes == {
        1: ("essaisurlingali02gobigoog", "essai_inegalite_tome1_fra.txt"),
        2: ("bub_gb_kMd-BHlp-M8C", "essai_inegalite_tome2_fra.txt"),
        3: ("bub_gb_Qk-jzgOI3KQC", "essai_inegalite_tome3_fra.txt"),
        4: ("essaisurlingali01gobigoog", "essai_inegalite_tome4_fra.txt"),
    }


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_each_fixture_is_the_tome_it_claims(n):
    """The title page in the fixture is the one the tome's guard expects."""

    _mod().clean_tome(_head(n), _tome(n))


@pytest.mark.parametrize(("scan", "claimed"), [(4, 1), (1, 4), (2, 3), (3, 2)])
def test_a_scan_of_another_tome_is_refused(scan, claimed):
    """The original defect: Tome IV filed as vol. 1 went through silently."""

    with pytest.raises(RuntimeError, match="title page"):
        _mod().clean_tome(_head(scan), _tome(claimed))


# --- Where the body starts -------------------------------------------------------


def test_a_scan_without_googles_preamble_keeps_its_first_chapter():
    """`bub_gb_kMd-BHlp-M8C` has no licence preamble, so the old fixed
    60-line drop cut ``LIVRE SECOND.`` (line 53) and ``CHAPITRE V.`` (60)."""

    text = _mod().clean_tome(_head(2), _tome(2))
    lines = text.splitlines()
    assert lines[0] == "ESSAI"
    assert "TOME SECOND." in lines
    assert "LIVRE SECOND." in lines
    assert "CHAPITRE V." in lines


@pytest.mark.parametrize("n", [1, 4])
def test_googles_usage_notice_is_cut(n):
    text = _mod().clean_tome(_head(n), _tome(n))
    assert text.splitlines()[0] == "ESSAI"
    assert "Google" not in text
    assert "books" not in text


def test_a_notice_that_survives_the_cut_raises():
    raw = _head(2).replace("Les  Égyptiens", "Google  Book  Search  Les  Égyptiens")
    with pytest.raises(RuntimeError, match="usage notice"):
        _mod().clean_tome(raw, _tome(2))


def test_a_scan_with_no_half_title_raises():
    raw = _head(2).replace("ESSAI", "ESSAY")
    with pytest.raises(RuntimeError, match="half-title"):
        _mod().clean_tome(raw, _tome(2))


# --- Text normalisation ----------------------------------------------------------


def test_curly_apostrophes_become_straight():
    """Tomes II and III come from a newer OCR that prints ’; I and IV have
    none. `split_by_chapter`'s capitals heading class takes ' but not ’, so
    ``CIVILISATION ANTIQUE RAYONNANT DE L’ASIE CENTRALE`` would not split."""

    text = _mod().clean_tome(_head(2), _tome(2))
    assert "’" not in text
    assert "‘" not in text
    assert "SUR L'INÉGALITÉ" in text
    assert "CIVILISATION ANTIQUE RAYONNANT DE L'ASIE CENTRALE" in text


def test_digitized_by_google_footers_are_dropped():
    assert "Digitized by Google" in " ".join(_head(2).split())
    assert "Digitized" not in _mod().clean_tome(_head(2), _tome(2))


@pytest.mark.parametrize(
    "footer",
    # As Tomes II and III's OCR reads them (73 survived the exact-match strip).
    ["■ . * ■'Oigitized by Google", "Digitizçd by Google 1", "■ Digifaeâtiy Google", "J by Google"],
)
def test_misread_footers_are_dropped_too(footer):
    raw = _head(2).replace("Digitized  by  Google", footer)
    text = _mod().clean_tome(raw, _tome(2))
    assert "Google" not in text
    assert "Les Égyptiens, les Éthiopiens" in text


# --- Renan is unchanged ------------------------------------------------------------


def test_renan_sources_are_pinned():
    assert _mod().RENAN_SOURCES == [
        ("viedejsus00renauoft", "vie_de_jesus_fra.txt"),
        ("histoiredesorigi04renauoft", "antechrist_fra.txt"),
        ("histoiredupeuple01rena", "peuple_israel_vol1_fra.txt"),
        ("histoiredupeuple02rena", "peuple_israel_vol2_fra.txt"),
        ("histoiredupeuple03rena", "peuple_israel_vol3_fra.txt"),
        ("histoiredupeuple04rena", "peuple_israel_vol4_fra.txt"),
        ("histoiredupeuple05rena", "peuple_israel_vol5_fra.txt"),
    ]


def test_renan_cleaning_still_drops_sixty_lines():
    raw = "\n".join(f"head {i}" for i in range(60)) + (
        "\nCHAPITRE  I.\n\n\n\n Texte  Digitized by Google  ici, l’apôtre.\n"
    )
    assert _mod()._clean(raw) == "CHAPITRE I.\n\nTexte ici, l’apôtre."
