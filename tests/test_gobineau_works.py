"""Gobineau's *Essai* is four works, one per tome of the 1853–55 edition (#742).

Runs on a committed fixture: the head of Tome II's archive.org OCR, cleaned
by the downloader and parsed by the pipeline as ingest would.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from minerva.authors import gobineau_works
from minerva.corpus.pipeline import parse_file

PERSEUS = Path(__file__).resolve().parents[1] / "perseus"
FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "gobineau" / "tome2_bub_gb_kMd-BHlp-M8C_head.txt"
)


def test_one_work_per_tome_named_by_tome():
    got = [(w.code, w.title, w.filenames) for w in gobineau_works.WORKS]
    assert got == [
        (
            f"essai_inegalite_tome{n}_fra",
            f"Essai sur l'inégalité des races humaines, tome {roman}",
            (f"essai_inegalite_tome{n}_fra.txt",),
        )
        for n, roman in ((1, "I"), (2, "II"), (3, "III"), (4, "IV"))
    ]


def test_edition_years_follow_the_title_pages():
    years = [w.edition_year for w in gobineau_works.WORKS]
    assert years == [
        "1853 (Paris, Firmin Didot)",
        "1853 (Paris, Firmin Didot)",
        "1855 (Paris, Firmin Didot)",
        "1855 (Paris, Firmin Didot)",
    ]


@pytest.mark.parametrize("name", [f"essai_inegalite_vol{n}_fra.txt" for n in (1, 2, 3, 4)])
def test_the_mislabelled_vol_files_are_no_longer_claimed(name):
    assert gobineau_works.find_work(name) is None


def _cleaned_tome2(tmp_path: Path) -> Path:
    sys.path.insert(0, str(PERSEUS))
    try:
        mod = importlib.import_module("download_gobineau_renan")
        (tome,) = [t for t in mod.GOBINEAU_TOMES if t.number == 2]
        text = mod.clean_tome(FIXTURE.read_text(encoding="utf-8"), tome)
    finally:
        sys.path.remove(str(PERSEUS))
        for name in ("_download", "download_gobineau_renan"):
            sys.modules.pop(name, None)
    out = tmp_path / "essai_inegalite_tome2_fra.txt"
    out.write_text(text, encoding="utf-8")
    return out


def test_book_holds_the_chapter_heading_and_the_tome_is_the_work(tmp_path):
    path = _cleaned_tome2(tmp_path)
    work = gobineau_works.find_work(path.name)
    assert work is not None
    chunks = list(parse_file(path, work))
    assert chunks
    assert {c.work for c in chunks} == {"Essai sur l'inégalité des races humaines, tome II"}
    books = {c.book for c in chunks}
    # The splitter's label: title-cased, with the livre's subtitle merged in
    # because it sits on the lines just above the chapter heading.
    chapter = "Civilisation Antique Rayonnant De L'asie Centrale Au Sud-ouest. Chapitre V"
    assert chapter in books
    assert not any("Tome" in (b or "") for b in books)
    body = next(c for c in chunks if c.book == chapter)
    assert "Jusqu'à présent il n'a encore été question" in body.text
