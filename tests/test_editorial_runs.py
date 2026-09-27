"""Tests for per-work editorial runs (#705).

Project Gutenberg apparatus — transcriber's notes, a corrections list,
the PG header — was indexed as the author's own text in four works,
because it arrives as ordinary body paragraphs the editorial-heading
predicate cannot see. `CorpusWork.editorial_runs` names each run by the
paragraph that opens it and the one that follows it, and the pass
re-types those chunks `block_type='editorial'` in place: no text
changes, so no `chunk_id` does.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from minerva.corpus.editorial_runs import apply_editorial_runs
from minerva.corpus.pipeline import parse_file
from minerva.corpus_works import CorpusWork
from minerva.tei import Chunk


def _work(runs: tuple[tuple[str, str | None], ...] = ()) -> CorpusWork:
    return CorpusWork(
        code="t",
        title="De Cive",
        translator="Thomas Hobbes",
        edition_year="1651",
        filenames=("t.txt",),
        fmt="txt",
        locator="chapter",
        corpus="hobbes",
        author="Hobbes",
        editorial_runs=runs,
    )


def _chunk(i: int, text: str, block_type: str | None = None) -> Chunk:
    return Chunk(
        chunk_id=f"id{i}",
        corpus="hobbes",
        author="Hobbes",
        work="De Cive",
        lang="eng",
        section=f"¶{i}",
        book=None,
        page=None,
        speaker=None,
        text=text,
        source_file="t.txt",
        translator=None,
        edition_year=None,
        block_type=block_type,
    )


_DE_CIVE = [
    "Transcriber’s Note:",
    "This version of the text cannot represent certain typographical effects.",
    "Minor errors, attributable to the printer, have been corrected.",
    "THE",
    "ENGLISH WORKS",
    "1. The faculties of human nature may be reduced unto four kinds.",
    "2. But some men perhaps will wonder.",
    "Transcriber’s Note",
    "In the summary of Chapter XIII, the last article is misnumbered.",
    "56.14 Prov. xxii. 10[)]: Removed.",
    "316.31 the rule over Christ[ai/ia]ns Transposed.",
]
_DE_CIVE_RUNS = (("Transcriber’s Note:", "THE"), ("Transcriber’s Note", None))


def _types(chunks: list[Chunk]) -> list[str | None]:
    return [c.block_type for c in chunks]


class TestApply:
    def test_head_and_tail_runs_are_typed_and_the_body_is_not(self) -> None:
        chunks = [_chunk(i, t) for i, t in enumerate(_DE_CIVE)]
        out = apply_editorial_runs(chunks, _work(_DE_CIVE_RUNS))
        e = "editorial"
        assert _types(out) == [e, e, e, None, None, None, None, e, e, e, e]

    def test_typing_changes_nothing_else(self) -> None:
        """The whole point: ids, text and sections survive, so embeddings,
        lemmas and cross-references survive a re-ingest."""

        chunks = [_chunk(i, t) for i, t in enumerate(_DE_CIVE)]
        out = apply_editorial_runs(chunks, _work(_DE_CIVE_RUNS))
        strip = [dataclasses.replace(c, block_type=None) for c in out]
        assert strip == chunks

    def test_a_byte_order_mark_does_not_hide_the_opener(self) -> None:
        """Meditations' first chunk starts with U+FEFF."""

        chunks = [
            _chunk(0, "﻿The Project Gutenberg eBook of Meditations"),
            _chunk(1, "*** START OF THE PROJECT GUTENBERG EBOOK MEDITATIONS ***"),
            _chunk(2, "By Marcus Aurelius"),
        ]
        runs = (("The Project Gutenberg eBook of", "By Marcus Aurelius"),)
        assert _types(apply_editorial_runs(chunks, _work(runs))) == ["editorial", "editorial", None]

    def test_existing_types_outside_a_run_are_kept(self) -> None:
        chunks = [_chunk(0, "Transcriber’s Note"), _chunk(1, "body"), _chunk(2, "a note", "note")]
        out = apply_editorial_runs(chunks, _work((("Transcriber’s Note", "body"),)))
        assert _types(out) == ["editorial", None, "note"]

    def test_no_runs_is_the_identity(self) -> None:
        chunks = [_chunk(i, t) for i, t in enumerate(_DE_CIVE)]
        assert apply_editorial_runs(chunks, _work()) is chunks


class TestSourceDrift:
    """A configured run that no longer matches must fail the ingest, not
    silently type nothing — or everything to the end of the work."""

    def test_a_missing_opener_raises(self) -> None:
        chunks = [_chunk(0, "body")]
        with pytest.raises(ValueError, match=r"De Cive.*opener 'Transcriber"):
            apply_editorial_runs(chunks, _work((("Transcriber’s Note", None),)))

    def test_a_missing_closer_raises(self) -> None:
        chunks = [_chunk(0, "Transcriber’s Note"), _chunk(1, "body")]
        with pytest.raises(ValueError, match="closer 'THE'"):
            apply_editorial_runs(chunks, _work((("Transcriber’s Note", "THE"),)))

    def test_runs_are_matched_in_order(self) -> None:
        """The second run's opener is searched for after the first run
        closes, so one opener line cannot satisfy both."""

        chunks = [_chunk(0, "Transcriber’s Note:"), _chunk(1, "THE"), _chunk(2, "body")]
        with pytest.raises(ValueError, match="opener"):
            apply_editorial_runs(chunks, _work(_DE_CIVE_RUNS))


def test_parse_file_applies_the_runs(tmp_path: Path) -> None:
    path = tmp_path / "t.txt"
    path.write_text("\n\n".join(_DE_CIVE) + "\n", encoding="utf-8")
    chunks = list(parse_file(path, _work(_DE_CIVE_RUNS)))
    typed = [c.text for c in chunks if c.block_type == "editorial"]
    assert typed[0] == "Transcriber’s Note:"
    assert "56.14 Prov. xxii. 10[)]: Removed." in typed
    assert not any(c.text.startswith("1. The faculties") for c in chunks if c.block_type)


@pytest.mark.parametrize(
    "module,code",
    [
        ("hobbes_works", "de_cive_eng"),
        ("hobbes_works", "leviathan_eng"),
        ("cicero_works", "de_re_publica_en"),
        ("marcus_aurelius_works", "meditations_en"),
    ],
)
def test_the_four_works_declare_their_runs(module: str, code: str) -> None:
    import importlib

    works = importlib.import_module(f"minerva.authors.{module}").WORKS
    (work,) = [w for w in works if w.code == code]
    assert work.editorial_runs
