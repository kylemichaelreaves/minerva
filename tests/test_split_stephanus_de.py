"""Tests for the MDZ-hOCR Stephanus splitter (Schleiermacher Der Staat)."""

from __future__ import annotations

from pathlib import Path

from minerva.corpus.split_stephanus_de import _book_for, split_stephanus_de
from minerva.corpus_works import CorpusWork

_W = 1000  # page width; right margin = x0/width > 0.82, i.e. x0 > 820


def _word(text: str, x0: int, y0: int) -> str:
    return f"<span class='ocrx_word' title='bbox {x0} {y0} {x0 + 50} {y0 + 30}'>{text}</span>"


def _line(words: list[tuple[str, int]], y: int) -> str:
    return " ".join(_word(t, x0, y) for t, x0 in words)


def _page(n: int, body_lines: list[str]) -> str:
    return f"<!-- MDZ_PAGE: {n} -->\n" + "\n".join(body_lines)


def _work() -> CorpusWork:
    return CorpusWork(
        code="republic_de",
        title="Republic",
        translator="Schleiermacher",
        edition_year="1855",
        filenames=("x.hocr",),
        fmt="hocr",
        locator="stephanus_de",
        lang="deu",
        corpus="plato",
        author="Plato",
    )


def test_book_for_canonical_boundaries():
    assert _book_for(327) == 1
    assert _book_for(354) == 1
    assert _book_for(357) == 2
    assert _book_for(514) == 7  # cave
    assert _book_for(621) == 10


def test_splitter_extracts_stephanus_and_drops_outlier(tmp_path: Path):
    # Page 1 is a TOC with a spurious right-margin "529" (before Book I).
    # Pages 2-4 are the real body with monotonic Stephanus 327, 330, 357.
    hocr = "\n".join(
        [
            _page(
                1,
                [
                    _line([("INHALT", 100)], 40),
                    _line([("Zehntes", 100), ("Buch", 300), ("529", 900)], 200),
                ],
            ),
            _page(
                2,
                [
                    _line([("DER", 100), ("STAAT", 250)], 40),  # header (dropped)
                    _line([("Gerechtigkeit", 100), ("ist", 400), ("327", 900)], 200),
                    _line([("eine", 100), ("Tugend", 300)], 260),
                ],
            ),
            _page(
                3,
                [
                    _line([("DER", 100), ("STAAT", 250)], 40),
                    _line([("der", 100), ("Seele", 300), ("330", 900)], 200),
                ],
            ),
            _page(
                4,
                [
                    _line([("DER", 100), ("STAAT", 250)], 40),
                    _line([("zweites", 100), ("Buch", 300), ("357", 900)], 200),
                    _line([("Reichtum", 100), ("und", 300), ("Armut", 450)], 260),
                ],
            ),
        ]
    )
    chunks = list(split_stephanus_de(hocr, _work(), tmp_path / "x.hocr"))
    sections = [c.section for c in chunks]
    # 529 outlier dropped; 327/330 emit (357 has no following marker to flush
    # but is flushed at end).
    assert sections == ["327", "330", "357"]
    assert all(c.author == "Plato" and c.work == "Republic" and c.lang == "deu" for c in chunks)
    assert chunks[0].book == "Buch 1"
    assert chunks[2].book == "Buch 2"  # 357 → Book II
    # 327's body is the prose between the 327 and 330 markers.
    assert "Tugend" in chunks[0].text


def test_splitter_repairs_hyphenation(tmp_path: Path):
    hocr = "\n".join(
        [
            _page(
                1,
                [
                    _line([("DER", 100), ("STAAT", 250)], 40),
                    _line([("Anfang", 100), ("327", 900)], 200),  # marker on its own-ish line
                    _line([("Bil-", 100)], 260),  # hyphenated, inside 327's segment
                    _line([("dung", 100), ("ist", 300)], 320),
                    _line([("gut", 100), ("330", 900)], 380),
                ],
            ),
        ]
    )
    chunks = list(split_stephanus_de(hocr, _work(), tmp_path / "x.hocr"))
    # "Bil-" + "dung" rejoined to "Bildung" within Stephanus 327's segment.
    assert chunks[0].section == "327"
    assert "Bildung" in chunks[0].text
