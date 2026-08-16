"""Perry-reference detection in `perseus/download_babrius.py` (#399).

Davies 1860 prints a Perry-index reference under every fable's title,
and the extractor uses those lines as its fable boundaries. The scan's
OCR damages roughly half of them, and every damaged one is a fable the
corpus silently loses — 92 recovered out of ~142 present.

The variants below are verbatim from the archive.org scan
(`bib_fict_4103078`), not invented.
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
            if name.startswith("download_") or name in {"_download", "_gutenberg"}:
                del sys.modules[name]


# Verbatim from the scan. The first four already matched; the rest are
# the shapes that were being dropped.
_REAL_PERRY_LINES = [
    "(P. F. 403.)",
    "(P. F. 26.)",
    "(P. F, 278.)",
    "(P. F..403.}",
    "(P..F. 26.)",
    "(Pp. F. 28.)",
    "(Pp. F. 68.)",
    "(Pp. ‘F. 10.)",
    "(Pp. F. 69.)",
    "(P. F, 82.)",
    "(vp. F. 83.)",
    "(p. F. 237+)",
    "(p. F. 89.)",
    "(Pp. F. 84.)",
    "(P.. F174.)",
    "(Pp. F. 265.)",
]

# Lines that must NOT be read as a fable boundary. Verse, prose and the
# page furniture that sits in the same column.
_NOT_PERRY_LINES = [
    "TRENCHING his vineyard once a husbandman",
    "The Fables of Babrius.",
    "FABLES OF BABRIUS.",
    "(See Plat. Phaedr. p. 203.)",
    "(P. 63.)",
    "and Plat. Phzedr. p. 203, and the notes of Ast and others. It",
    "12",
    "(F. 403.)",
]


@pytest.mark.parametrize("line", _REAL_PERRY_LINES)
def test_ocr_damaged_perry_refs_are_still_fable_boundaries(line: str):
    mod = importlib.import_module("download_babrius")
    assert mod._PERRY_REF.match(line), f"missed a real fable boundary: {line!r}"


@pytest.mark.parametrize("line", _NOT_PERRY_LINES)
def test_verse_and_page_furniture_are_not_fable_boundaries(line: str):
    mod = importlib.import_module("download_babrius")
    assert not mod._PERRY_REF.match(line), f"false boundary on: {line!r}"


def test_the_perry_number_is_captured_not_just_matched():
    """The number is Davies's own cross-reference to the Perry index —
    the canonical cross-walk between the Aesopic collections, per
    `aesop_works`. Matching without capturing is what left the extractor
    synthesising its own sequential numbering instead."""

    mod = importlib.import_module("download_babrius")
    assert mod._PERRY_REF.match("(P. F. 403.)").group("perry") == "403"
    assert mod._PERRY_REF.match("(Pp. ‘F. 10.)").group("perry") == "10"
    assert mod._PERRY_REF.match("(p. F. 237+)").group("perry") == "237"


def _raw_document(body: str) -> str:
    """Minimal stand-in for the scan. `_extract_english` looks for a
    `FABLE I` header past line 1000 (the preface's length in the real
    volume), so the filler is load-bearing, not padding."""

    return "\n".join(["preface line"] * 1001 + ["FABLE I.", *body.splitlines()])


def test_extraction_stops_at_the_notes_section():
    """Davies prints `NOTES TO BABRIUS.` after the last fable, then an
    editorial commentary. The end-detection looked for `INDEX TO`,
    `FINIS` and `PRINTED BY` — none of which occur anywhere in this
    scan — so the notes were swallowed into the final fable, 14,891
    characters of them (#399, same class as #385)."""

    mod = importlib.import_module("download_babrius")
    raw = _raw_document(
        "THE ASS'S SHADOW\n"
        "(P. F. 339.)\n"
        "A MAN of Athens on a summer's day,\n"
        "To Megara was fain to make his way.\n"
        "\n"
        "NOTES TO BABRIUS.\n"
        "PRoEM II. 5.-—Cybisas, or Cybissus. Theon and Apthonius,\n"
        "later teachers of rhetoric, mention Cybissus the Libyan.\n"
    )
    out = mod._extract_english(raw)
    assert "A MAN of Athens" in out
    assert "NOTES TO" not in out
    assert "Cybisas" not in out
