"""Tests for `minerva.corpus_extract` — focused on the EPUB-spine
editorial filter, which is the only piece of the extractor with
non-trivial logic worth covering directly. The PDF / HTML extractors
are exercised through `tests/test_corpus_parse.py` and manual ingest;
they're thin wrappers over PyMuPDF / BeautifulSoup respectively."""

from __future__ import annotations

import pytest

bs4 = pytest.importorskip("bs4")
# importorskip must run before the bs4 / corpus_extract imports so the
# whole module gets skipped on systems without the [hegel] extras —
# hence E402 is unavoidable here.
from bs4 import BeautifulSoup  # noqa: E402

from minerva import corpus_extract  # noqa: E402


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------- _epub_item_is_editorial ----------


def test_epub_item_editorial_detects_back_matter_h2():
    # Real PR EPUB: spine[31] starts with `<h2>Editorial notes</h2>`.
    assert (
        corpus_extract._epub_item_is_editorial(
            _soup("<html><body><h2>Editorial notes</h2><p>...</p></body></html>")
        )
        is True
    )


def test_epub_item_editorial_detects_glossary_bibliography_index():
    # The PR EPUB's other back-matter items: spine[33-36].
    for heading in (
        "Glossary",
        "Selected bibliography",
        "Index of subjects",
        "Index of names",
    ):
        assert (
            corpus_extract._epub_item_is_editorial(
                _soup(f"<html><body><h2>{heading}</h2></body></html>")
            )
            is True
        ), heading


def test_epub_item_editorial_detects_front_matter():
    # Spine[6-12] of the PR EPUB: editor / translator front matter.
    for heading in (
        "Editor's introduction",
        "Translator's preface",
        "Key to abbreviations",
        "Table of Contents",
        "Contents",
    ):
        assert (
            corpus_extract._epub_item_is_editorial(
                _soup(f"<html><body><h2>{heading}</h2></body></html>")
            )
            is True
        ), heading


def test_epub_item_editorial_keeps_hegel_chapter_heads():
    # Spine items whose first heading is Hegel's own — must NOT be
    # filtered, or we'd lose the Preface / Introduction / Parts.
    for heading in (
        "Preface",
        "Introduction",
        "Civil Society",
        "The State",
        "The Family",
        "Ethical Life",
        "§ 34",
        "P ART O NE",
    ):
        assert (
            corpus_extract._epub_item_is_editorial(
                _soup(f"<html><body><h2>{heading}</h2></body></html>")
            )
            is False
        ), heading


def test_epub_item_editorial_falls_back_to_title_tag():
    # When the body has no h1-h6, the <title> element is the next-best signal.
    assert (
        corpus_extract._epub_item_is_editorial(
            _soup("<html><head><title>Glossary</title></head><body><p>...</p></body></html>")
        )
        is True
    )


def test_epub_item_editorial_returns_false_when_no_headings():
    # No h-tag and no title: can't classify — default to keep.
    assert (
        corpus_extract._epub_item_is_editorial(
            _soup("<html><body><p>Some body text</p></body></html>")
        )
        is False
    )
