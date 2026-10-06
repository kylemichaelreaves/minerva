"""Source-drift guards that used to pass when the source drifted (#499).

`verify_language` no-opped on a download with no `Language:` header, and two
scripts sliced live archive.org OCR at absolute line numbers, so a regenerated
OCR moved the cut with no error. Each guard now asserts something about the
content, and raises when the content is not what it expects.

Network is never touched: every test feeds text in directly.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

PERSEUS = Path(__file__).resolve().parents[1] / "perseus"


@pytest.fixture(autouse=True)
def _perseus_on_path():
    sys.path.insert(0, str(PERSEUS))
    try:
        yield
    finally:
        sys.path.remove(str(PERSEUS))
        for name in list(sys.modules):
            if name in {"_gutenberg", "_download", "download_boulainvilliers"}:
                del sys.modules[name]


# --- verify_language ---------------------------------------------------------


def test_verify_language_raises_when_the_header_is_missing():
    gutenberg = importlib.import_module("_gutenberg")
    with pytest.raises(RuntimeError, match="no Language: header"):
        gutenberg.verify_language("Title: Something\n\nbody text\n", "Latin")


def test_verify_language_raises_on_a_mismatch():
    gutenberg = importlib.import_module("_gutenberg")
    with pytest.raises(RuntimeError, match="Wrong PG ID"):
        gutenberg.verify_language("Title: X\nLanguage: English\n", "French")


def test_verify_language_accepts_a_match_case_insensitively():
    gutenberg = importlib.import_module("_gutenberg")
    gutenberg.verify_language("Title: X\nLanguage: latin\r\n", "Latin")


# --- Descartes Principes: anchored on headings --------------------------------


def _descartes():
    # The module loads the Boulainvilliers clean script at import time; only
    # the slice is under test here.
    return importlib.import_module("extract_descartes_principes")


def _principes_ocr(prefix_lines: int) -> str:
    pad = ["front matter"] * prefix_lines
    return "\n".join(
        [
            *pad,
            "SECONDE  PARTIE. ",
            "Des  Principes  des  chofes  matérielles. ",
            "QUATRIESME  PARTIE.",
            "fin du corps",
            "",
            "TABLE    DES    PRINCIPES ",
            "1. table entry",
            "SECONDE  PARTIE ",  # the table repeats the heading
        ]
    )


@pytest.mark.parametrize("prefix_lines", [0, 7, 15776])
def test_principes_slice_follows_the_headings_not_the_line_numbers(prefix_lines):
    body = _descartes()._slice_parts(_principes_ocr(prefix_lines))
    assert body.startswith("SECONDE  PARTIE. ")
    assert body.rstrip().endswith("fin du corps")
    assert "TABLE" not in body
    assert "front matter" not in body


def test_principes_slice_raises_when_an_anchor_is_missing():
    raw = _principes_ocr(3).replace("TABLE    DES    PRINCIPES", "INDEX")
    with pytest.raises(RuntimeError, match="TABLE DES PRINCIPES"):
        _descartes()._slice_parts(raw)
    raw = _principes_ocr(3).replace("SECONDE  PARTIE", "SECUNDA PARS")
    with pytest.raises(RuntimeError, match="SECONDE PARTIE"):
        _descartes()._slice_parts(raw)


# --- Boulainvilliers: the cut lines must carry the expected text ---------------


def _boul():
    return importlib.import_module("download_boulainvilliers")


def _ocr_with(cut: object, offset: int = 0) -> str:
    """A synthetic OCR dump carrying the cut's fingerprints, shifted by *offset*."""

    n = max(i for i, _ in cut.fingerprints) + 20
    lines = [f"filler {i}" for i in range(n + offset)]
    for i, text in cut.fingerprints:
        lines[i + offset] = f"  {text}  "
    return "\n".join(lines)


@pytest.mark.parametrize("name", ["HISTOIRE", "LETTRES"])
def test_boulainvilliers_cut_accepts_the_ocr_it_was_written_against(name):
    cut = getattr(_boul(), name)
    _boul()._check_cut(_ocr_with(cut).splitlines(), cut)


@pytest.mark.parametrize("name", ["HISTOIRE", "LETTRES"])
def test_boulainvilliers_cut_raises_when_the_ocr_shifts(name):
    cut = getattr(_boul(), name)
    with pytest.raises(RuntimeError, match="regenerated"):
        _boul()._check_cut(_ocr_with(cut, offset=1).splitlines(), cut)
