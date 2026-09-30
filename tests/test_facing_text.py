"""Tests for the facing-text split (#675).

Miller's Loeb *De Officiis* (PG 47001) prints Cicero's Latin on the left
page and the English on the right; the Gutenberg transcription flattens
the spread into alternating blocks, each Roman-numeral chapter giving
its Latin and then its English, with the critical apparatus, the
translator's footnotes, the marginal sidenotes and the introduction all
interleaved. It was ingested whole as English. The split keeps the
English, drops the Latin (the corpus has its own Latin edition), and
types the rest as apparatus — after the ids exist, so no kept chunk's
``chunk_id`` moves.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from minerva.authors import cicero_works
from minerva.corpus.facing_text import split_facing_text
from minerva.corpus.pipeline import parse_file
from minerva.corpus_works import CorpusWork
from minerva.tei import Chunk

_FIXTURE = Path(__file__).parent / "fixtures" / "cicero_de_officiis_facing_excerpt.txt"


def _miller() -> CorpusWork:
    work = cicero_works.find_work("de_officiis_en.txt")
    assert work is not None
    return work


def _parse(work: CorpusWork) -> list[Chunk]:
    return list(parse_file(_FIXTURE, work))


def _by_prefix(chunks: list[Chunk], prefix: str) -> Chunk:
    hits = [c for c in chunks if c.text.startswith(prefix)]
    assert len(hits) == 1, (prefix, [c.text[:40] for c in hits])
    return hits[0]


class TestMillerDeOfficiis:
    def test_the_work_opts_in(self) -> None:
        assert _miller().facing_text is True

    def test_no_latin_survives(self) -> None:
        texts = " ".join(c.text for c in _parse(_miller()))
        for latin in (
            "Quamquam te, Marce fili",
            "Quam ob rem disces",
            "ab eo ordiri maxime volui",
            "L. Minuci Basili",
            "Néc fides regni",
            "Quem ad modum officia",
            "Maximis igitur in malis",
            "Tecta vero, quibus",
            "Sed ut facillime",
        ):
            assert latin not in texts, latin

    def test_the_english_is_body_text(self) -> None:
        chunks = _parse(_miller())
        for english in (
            "*1* I. My dear son Marcus",
            "*2* You will, therefore",
            "by and by), I wish",
            '"There is no fellowship inviolate',
            "*1* I. I believe, Marcus",
            "*5* II. Therefore, amid all",
            "*9* IV. And how could houses",
            "*44* (IV.) But although",
        ):
            chunk = _by_prefix(chunks, english)
            assert chunk.block_type is None, english
            assert chunk.lang == "eng"

    def test_footnotes_are_notes_including_their_continuations(self) -> None:
        chunks = _parse(_miller())
        for note in ("[1] _dicendum_", "[A] Cicero's technical", "_rectum_ is 'right,'"):
            assert _by_prefix(chunks, note).block_type == "note", note

    def test_sidenotes_front_and_back_matter_are_editorial(self) -> None:
        chunks = _parse(_miller())
        for editorial in (
            "Italic text has been marked",
            "In the _de Officiis_ we have",
            "#Introduction: the importance",
            "#Statement of subject.#",
            "#de Fin. II, 12 ff.",
            "LIBER PRIMUS / BOOK I",
            "INDEX",
            "References are to Book",
            "Academicians.",
        ):
            assert _by_prefix(chunks, editorial).block_type == "editorial", editorial

    def test_every_kept_chunk_keeps_its_id(self) -> None:
        before = _parse(dataclasses.replace(_miller(), facing_text=False))
        after = _parse(_miller())
        before_ids = {c.chunk_id: c for c in before}
        assert after
        for chunk in after:
            assert chunk.chunk_id in before_ids
            assert chunk.text == before_ids[chunk.chunk_id].text
        dropped = [c for c in before if c.chunk_id not in {a.chunk_id for a in after}]
        assert len(dropped) == 9
        assert all(c.block_type is None for c in dropped)


def _chunk(text: str) -> Chunk:
    return Chunk(
        chunk_id=text[:8],
        corpus="cicero",
        author="Cicero",
        work="De Officiis",
        lang="eng",
        section="¶1",
        book=None,
        page=None,
        speaker=None,
        text=text,
        source_file="t.txt",
        translator=None,
        edition_year=None,
    )


_SOURCE = "LIBER PRIMUS / BOOK I\n\nI. Quamquam te.\n\nI. My dear son.\n"


class TestFailsLoudly:
    def test_a_chunk_missing_from_the_source_raises(self) -> None:
        with pytest.raises(ValueError, match="not found in the source"):
            split_facing_text([_chunk("I. Something else entirely.")], _SOURCE, "De Officiis")

    def test_a_chapter_with_no_translation_raises(self) -> None:
        source = _SOURCE + "\nII. Sed cum statuissem.\n"
        chunks = [
            _chunk(t) for t in ("I. Quamquam te.", "I. My dear son.", "II. Sed cum statuissem.")
        ]
        with pytest.raises(ValueError, match=r"chapter\(s\) \[2\] of book 1 have no translation"):
            split_facing_text(chunks, source, "De Officiis")

    def test_no_book_heading_raises(self) -> None:
        with pytest.raises(ValueError, match="no facing-text book heading"):
            split_facing_text([_chunk("I. My dear son.")], "I. My dear son.\n", "De Officiis")

    def test_the_minimal_source_splits(self) -> None:
        chunks = [_chunk(t) for t in ("I. Quamquam te.", "I. My dear son.")]
        kept = split_facing_text(chunks, _SOURCE, "De Officiis")
        assert [c.text for c in kept] == ["I. My dear son."]
