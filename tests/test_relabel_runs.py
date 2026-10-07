"""Tests for per-work relabel runs (#735).

The English Leviathan's front matter reached the index under section
labels the heading detector made from wrapped title lines: the title
page, transcriber's notes and dedication under ``Ecclesiastical and
CIVILL`` (the title's second line), and the table of contents under
``Defects``, ``And Misery``, ``To the Soveraign Power``, … — the tails of
chapter titles too long for one line. Two contents headings both read
``BOOKS OF HOLY SCRIPTURE``, so ``Books of Holy Scripture, ¶1`` was
minted twice.

`CorpusWork.relabel_runs` names each run by the paragraph that opens it
and the one after it, and gives the whole run one label, numbered
``¶1…¶N`` across it. ``section`` feeds ``chunk_id``, so a relabelled
chunk is re-minted — and nothing outside a run may move.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from minerva.corpus.pipeline import parse_file
from minerva.corpus.relabel_runs import apply_relabel_runs
from minerva.corpus_works import CorpusWork
from minerva.tei import Chunk, _make_chunk_id


def _work(runs: tuple[tuple[str, str | None, str], ...] = ()) -> CorpusWork:
    return CorpusWork(
        code="t",
        title="Leviathan",
        translator="Thomas Hobbes",
        edition_year="1651",
        filenames=("t.txt",),
        fmt="txt",
        locator="chapter",
        corpus="hobbes",
        author="Hobbes",
        relabel_runs=runs,
    )


def _chunk(i: int, text: str, section: str) -> Chunk:
    return Chunk(
        chunk_id=f"id{i}",
        corpus="hobbes",
        author="Hobbes",
        work="Leviathan",
        lang="eng",
        section=section,
        book=section.split(", ¶")[0] or None,
        page=None,
        speaker=None,
        text=text,
        source_file="t.txt",
        translator=None,
        edition_year=None,
    )


_CHUNKS = [
    ("Dedication text.", "Ecclesiastical and CIVILL, ¶1"),
    ("OF MAN", "Contents of the Chapters the First Part, ¶1"),
    ("1. OF SENSE", "Introduction, ¶1"),
    ("9. OF THE SEVERALL SUBJECTS OF KNOWLEDGE", "Defects, ¶1"),
    ("34. OF THE SIGNIFICATION, OF SPIRIT", "Books of Holy Scripture, ¶1"),
    ("35. OF THE SIGNIFICATION IN SCRIPTURE", "Books of Holy Scripture, ¶1"),
    ("Nature (the art whereby God hath made", "The Introduction, ¶1"),
]
_RUNS = (("OF MAN", "Nature (the art", "Contents"),)


def _chunks() -> list[Chunk]:
    return [_chunk(i, t, s) for i, (t, s) in enumerate(_CHUNKS)]


class TestApply:
    def test_the_run_is_relabelled_and_numbered_across_its_length(self) -> None:
        out = apply_relabel_runs(_chunks(), _work(_RUNS))
        assert [c.section for c in out] == [
            "Ecclesiastical and CIVILL, ¶1",
            "Contents, ¶1",
            "Contents, ¶2",
            "Contents, ¶3",
            "Contents, ¶4",
            "Contents, ¶5",
            "The Introduction, ¶1",
        ]
        assert {c.book for c in out[1:6]} == {"Contents"}

    def test_a_relabelled_chunk_is_re_minted_the_way_the_splitter_mints(self) -> None:
        """Same inputs as `split_paragraphic._emit`, so a relabelled id is
        the id the splitter would have produced had it read this label."""

        out = apply_relabel_runs(_chunks(), _work(_RUNS))
        c = out[2]
        assert c.chunk_id == _make_chunk_id(
            "t.txt", "Leviathan", "eng", "Contents", "Contents, ¶2", "", c.text[:120]
        )

    def test_nothing_outside_a_run_moves(self) -> None:
        before = _chunks()
        out = apply_relabel_runs(before, _work(_RUNS))
        assert out[0] == before[0]
        assert out[-1] == before[-1]

    def test_only_section_book_and_id_change_inside_a_run(self) -> None:
        before = _chunks()
        out = apply_relabel_runs(before, _work(_RUNS))
        for a, b in zip(out[1:6], before[1:6], strict=True):
            assert dataclasses.replace(a, chunk_id="", section="", book="") == (
                dataclasses.replace(b, chunk_id="", section="", book="")
            )

    def test_no_runs_is_the_identity(self) -> None:
        chunks = _chunks()
        assert apply_relabel_runs(chunks, _work()) is chunks

    def test_a_run_to_the_end_of_the_work(self) -> None:
        out = apply_relabel_runs(_chunks(), _work((("Nature (the art", None, "Body"),)))
        assert out[-1].section == "Body, ¶1"


class TestSourceDrift:
    """A configured run that stops matching fails the ingest."""

    def test_a_missing_opener_raises(self) -> None:
        with pytest.raises(ValueError, match=r"Leviathan.*opener 'NOPE'"):
            apply_relabel_runs(_chunks(), _work((("NOPE", None, "X"),)))

    def test_a_missing_closer_raises(self) -> None:
        with pytest.raises(ValueError, match="closer 'NOPE'"):
            apply_relabel_runs(_chunks(), _work((("OF MAN", "NOPE", "X"),)))


_LEVIATHAN_FRONT = Path(__file__).parent / "fixtures" / "hobbes_eng" / "leviathan_contents.txt"


class TestLeviathanFrontMatter:
    """The committed excerpt of the real file: title page through the
    start of the Introduction."""

    @staticmethod
    def _work() -> CorpusWork:
        from minerva.authors.hobbes_works import WORKS

        (work,) = [w for w in WORKS if w.code == "leviathan_eng"]
        return work

    def test_no_label_is_made_from_a_wrapped_title_line(self) -> None:
        chunks = list(parse_file(_LEVIATHAN_FRONT, self._work()))
        books = {c.book for c in chunks}
        for wrapped in ("Ecclesiastical and CIVILL", "Defects", "And Misery", "Introduction"):
            assert wrapped not in books

    def test_every_front_matter_locator_is_unique(self) -> None:
        chunks = list(parse_file(_LEVIATHAN_FRONT, self._work()))
        sections = [c.section for c in chunks]
        assert len(sections) == len(set(sections))

    def test_the_front_matter_reads_as_four_runs(self) -> None:
        chunks = list(parse_file(_LEVIATHAN_FRONT, self._work()))
        by_text = {c.text: c.section for c in chunks}
        assert by_text["By Thomas Hobbes"] == "Title Page, ¶1"
        assert by_text["TRANSCRIBER’S NOTES ON THE E-TEXT:"] == "Transcriber’s Notes, ¶1"
        assert by_text["Sir,"].startswith("Dedication, ¶")
        assert by_text["OF MAN"] == "Contents, ¶1"
        assert by_text["48. A REVIEW AND CONCLUSION"] == "Contents, ¶49"

    def test_the_introduction_keeps_its_ids(self) -> None:
        """Only the front matter is re-minted: the body's ids — and the
        embeddings, lemmas and cross-references keyed on them — stay."""

        work = self._work()
        before = list(parse_file(_LEVIATHAN_FRONT, dataclasses.replace(work, relabel_runs=())))
        after = list(parse_file(_LEVIATHAN_FRONT, work))
        intro = next(i for i, c in enumerate(after) if c.text.startswith("Nature (the art"))
        assert len(after) == len(before)
        assert [c.chunk_id for c in after[intro:]] == [c.chunk_id for c in before[intro:]]

    def test_typing_still_applies(self) -> None:
        chunks = list(parse_file(_LEVIATHAN_FRONT, self._work()))
        contents = [c for c in chunks if c.book == "Contents"]
        assert len(contents) == 49
        assert {c.block_type for c in contents} == {"editorial"}
