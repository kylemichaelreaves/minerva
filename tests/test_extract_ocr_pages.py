"""#540: the 2011 OUP scan of *Lectures on the Philosophy of World
History* carries a bad embedded OCR layer — the corruption is in the
PDF's own text, before any extraction, so no extractor change can help.

Re-OCR'd from the 300 dpi page images with macOS Vision, measured over
all 575 pages:

    signature               embedded   vision   change
    tilde in word                411        5   -99%
    digit in word                280        3   -99%
    capital mid-word             788        8   -99%
    TOTAL                       2027       72   -96%

    embedded   201,726 word tokens, 12,451 unknown = 6.17%
    vision     202,431 word tokens,  7,815 unknown = 3.86%

The re-OCR is stored as per-page line lists — the same shape
`extract_pdf` builds before cleaning — so page-chrome detection and the
running-head passes apply unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from minerva.corpus_extract import extract_ocr_pages


def _write(tmp_path: Path, pages: list[list[str]]) -> Path:
    p = tmp_path / "x.ocr.json"
    p.write_text(json.dumps({"pages": pages}), encoding="utf-8")
    return p


def test_pages_are_joined_with_a_blank_line_between_them(tmp_path: Path):
    """The same page-break convention `extract_pdf` uses, so paragraph
    boundaries survive into the splitter."""

    path = _write(tmp_path, [["first page line"], ["second page line"]])
    assert extract_ocr_pages(path) == "first page line\n\nsecond page line\n"


def test_repeated_page_chrome_is_dropped(tmp_path: Path):
    """A running head repeated across pages is furniture, and
    `_detect_page_chrome` already knows how to find it — this path must
    reuse it rather than re-implement it."""

    pages = [["THE LECTURES OF 1822-3", f"body {i}"] for i in range(10)]
    out = extract_ocr_pages(_write(tmp_path, pages))
    assert "THE LECTURES OF 1822-3" not in out
    assert "body 4" in out


def test_a_missing_pages_key_is_an_error_not_an_empty_book(tmp_path: Path):
    """Silence is this pipeline's failure mode. A malformed OCR file
    must not read as a work with no text."""

    p = tmp_path / "bad.ocr.json"
    p.write_text(json.dumps({"oops": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="pages"):
        extract_ocr_pages(p)


def test_the_real_lwh_ocr_file_parses_if_present(tmp_path: Path):
    """Against the actual artefact when it is on disk. `data/` is
    gitignored, so this skips in CI rather than failing."""

    real = Path(__file__).resolve().parents[1] / "data" / "hegel" / "lwh_vision.ocr.json"
    if not real.exists():
        pytest.skip("OCR artefact not present (data/ is gitignored)")
    text = extract_ocr_pages(real)
    assert len(text) > 500_000
    assert "representational" in text
