"""Where `perseus/download_boulainvilliers.py` cuts the archive.org OCR (#779).

The ingested Histoire began inside the 1727 edition's subscriber list and
ran through the publisher's Avertissement, OCR of the fold-out map and
Louis XIV's 1697 *Mémoire* to the intendants — 160 chunks, none of them by
Boulainvilliers — and ended mid-sentence 312 lines before the work does.
The Lettres began inside Google Books' usage notice. The bounds now sit on
the work's own first and last lines, and each cut is fingerprinted *on*
those lines, so a regenerated OCR raises instead of slicing elsewhere.

The fixtures under ``tests/fixtures/boulainvilliers/cut_*.tsv`` are the
real raw djvu.txt lines around each bound, keyed by their 1-based line
number; the tests rebuild a dump of the real length with those lines in
place. Network is never touched.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PERSEUS = ROOT / "perseus"
FIXTURES = ROOT / "tests" / "fixtures" / "boulainvilliers"

# Line counts of the two archive.org djvu.txt files the fixtures come from.
HISTOIRE_LINES = 41046
LETTRES_LINES = 25979


@pytest.fixture
def dl():
    sys.path.insert(0, str(PERSEUS))
    try:
        yield importlib.import_module("download_boulainvilliers")
    finally:
        sys.path.remove(str(PERSEUS))
        for name in ("_download", "download_boulainvilliers"):
            sys.modules.pop(name, None)


def _dump(tsv: str, total: int) -> list[str]:
    """The real lines of *tsv* at their real line numbers."""

    lines = [f"filler {i}" for i in range(total)]
    for row in (FIXTURES / tsv).read_text(encoding="utf-8").splitlines():
        number, text = row.split("\t", 1)
        lines[int(number) - 1] = text
    return lines


def _shifted(lines: list[str], shift: int) -> list[str]:
    """*lines* with *shift* lines inserted (> 0) or removed (< 0) at the top,
    as a regenerated OCR that gained or lost a line of front matter."""

    return ["inserted"] * shift + lines if shift > 0 else lines[-shift:]


def _fold(line: str) -> str:
    return " ".join(line.split())


def _nonblank(lines: list[str]) -> list[str]:
    return [_fold(x) for x in lines if x.strip()]


class TestHistoireBounds:
    def test_starts_at_the_auteur_line_of_the_preface_heading(self, dl):
        body = _nonblank(
            dl._slice(_dump("cut_etatdelafranceda01boul.tsv", HISTOIRE_LINES), dl.HISTOIRE)
        )
        assert body[0] == "L'AUTEUR.'"
        assert body[1].startswith("' A I ramafle avec foin les Mémoires")

    def test_ends_on_the_works_last_sentence_not_mid_sentence(self, dl):
        body = _nonblank(
            dl._slice(_dump("cut_etatdelafranceda01boul.tsv", HISTOIRE_LINES), dl.HISTOIRE)
        )
        assert body[-1].endswith("du bien de l'Etat en général.")
        # The `Fin des Mémoires` colophon is furniture and stays out.
        assert not any(line.startswith("Fin des Mémoires") for line in body)

    @pytest.mark.parametrize("shift", [-1, 1])
    def test_a_shifted_ocr_raises(self, dl, shift):
        lines = _shifted(_dump("cut_etatdelafranceda01boul.tsv", HISTOIRE_LINES), shift)
        with pytest.raises(RuntimeError, match="regenerated"):
            dl._slice(lines, dl.HISTOIRE)


class TestLettresBounds:
    def test_starts_at_the_first_letter(self, dl):
        body = _nonblank(
            dl._slice(_dump("cut_lettressurlesan00boulgoog.tsv", LETTRES_LINES), dl.LETTRES)
        )
        assert body[0] == "PREMIERE LETTRE."
        assert not any("Google" in line for line in body)

    def test_runs_to_the_end_of_the_file(self, dl):
        body = _nonblank(
            dl._slice(_dump("cut_lettressurlesan00boulgoog.tsv", LETTRES_LINES), dl.LETTRES)
        )
        assert body[-1] == "FIN."

    @pytest.mark.parametrize("shift", [-1, 1])
    def test_a_shifted_ocr_raises(self, dl, shift):
        lines = _shifted(_dump("cut_lettressurlesan00boulgoog.tsv", LETTRES_LINES), shift)
        with pytest.raises(RuntimeError, match="regenerated"):
            dl._slice(lines, dl.LETTRES)


@pytest.mark.parametrize("name", ["HISTOIRE", "LETTRES"])
def test_every_bound_is_fingerprinted_on_its_own_line(dl, name):
    """A fingerprint pins the line the slice starts on and the line it ends
    on — not a line some distance away, which a local edit could move
    independently of the cut."""

    cut = getattr(dl, name)
    pinned = {index for index, _ in cut.fingerprints}
    assert cut.start in pinned
    if cut.end is not None:
        assert cut.end - 1 in pinned


def test_main_reads_a_local_raw_dump_and_writes_both_files(dl, tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    for item, tsv, total in (
        ("etatdelafranceda01boul", "cut_etatdelafranceda01boul.tsv", HISTOIRE_LINES),
        ("lettressurlesan00boulgoog", "cut_lettressurlesan00boulgoog.tsv", LETTRES_LINES),
    ):
        (raw_dir / f"{item}_djvu.txt").write_text("\n".join(_dump(tsv, total)), encoding="utf-8")
    out = tmp_path / "out"

    assert dl.main(["--raw-dir", str(raw_dir), "--out-dir", str(out)]) == 0

    histoire = (out / "histoire_anc_gouv_fra.txt").read_text(encoding="utf-8")
    lettres = (out / "lettres_parlemens_fra.txt").read_text(encoding="utf-8")
    assert histoire.lstrip().startswith("L'AUTEUR.'")
    assert histoire.rstrip().endswith("du bien de l'Etat en général.")
    assert lettres.lstrip().startswith("PREMIERE LETTRE.")
