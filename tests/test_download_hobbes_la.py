"""Tests for `perseus/download_hobbes_la.py`'s tail patch (#733).

The Google scan the Latin Leviathan is sliced from has no leaves for
pp. 510–512, so the slice ended mid-sentence at "Itaque atramentum". The
UofT scan of the same volume, which the Appendix ad Leviathan is already
read from, has p. 510. The patch appends it, and refuses to guess.
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
            if name in {"_download", "download_hobbes_la"}:
                del sys.modules[name]


def _mod():
    return importlib.import_module("download_hobbes_la")


_PRIMARY = "CAPUT  XLVII.\n\nribus  infecti  paulatim  fiierant.    Itaque  atramentum \n\n"

_DONOR = (
    "front matter\n"
    "ribus  infecti  paulatim  fuerant.    Itaque  atramentum \n"
    "\n\n"
    "510  DE  REGNO  TENEBRARUM. \n"
    "\n"
    "CAP.  XLVii.  illud  democraticum,  prsedicando,  scribendo,  dispu- \n"
    "intestinas  nos  opprimi  ab  externo  hoste  patiamur \n"
    "universos. \n"
    "\n\n"
    "APPENDIX  AD  LEVIATHAN. \n"
    "\n"
    "CAPUT  I. \n"
)


def test_the_missing_page_is_appended() -> None:
    m = _mod()
    out = m.patch_tail(_PRIMARY, _DONOR, m.LEVIATHAN_TAIL, label="t")
    assert out.startswith(_PRIMARY.rstrip("\n"))
    assert "illud  democraticum" in out
    assert out.rstrip().endswith("universos.")
    assert "APPENDIX" not in out


def test_the_patch_carries_the_running_head_for_the_parser_to_drop() -> None:
    """The donor page is appended as OCR'd, so the parser's own page rules
    apply to it exactly as to every other page."""

    m = _mod()
    out = m.patch_tail(_PRIMARY, _DONOR, m.LEVIATHAN_TAIL, label="t")
    assert "510  DE  REGNO  TENEBRARUM." in out


def test_a_slice_that_no_longer_ends_at_the_gap_is_refused() -> None:
    """If the primary scan is ever repaired, or the slice moves, patching
    would duplicate p. 510 — so it fails instead."""

    m = _mod()
    with pytest.raises(m.SliceError, match="does not end"):
        m.patch_tail(_PRIMARY + "universos.\n", _DONOR, m.LEVIATHAN_TAIL, label="t")


def test_a_donor_without_the_anchor_is_refused() -> None:
    m = _mod()
    with pytest.raises(m.SliceError, match="anchor"):
        m.patch_tail(_PRIMARY, "nothing here\n", m.LEVIATHAN_TAIL, label="t")


def test_a_donor_without_the_end_marker_is_refused() -> None:
    m = _mod()
    donor = _DONOR.split("APPENDIX")[0]
    with pytest.raises(m.SliceError, match="end marker"):
        m.patch_tail(_PRIMARY, donor, m.LEVIATHAN_TAIL, label="t")


def test_an_oversized_patch_is_refused() -> None:
    """A page is ~40 lines; hundreds means the end marker moved."""

    m = _mod()
    donor = _DONOR.replace("universos. \n", "universos. \n" + "x\n" * 500)
    with pytest.raises(m.SliceError, match="lines"):
        m.patch_tail(_PRIMARY, donor, m.LEVIATHAN_TAIL, label="t")
