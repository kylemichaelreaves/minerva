"""Smoke tests for the early-modern author work tables + chapter splitter."""

from __future__ import annotations

from pathlib import Path

from minerva.authors import hobbes_works, hume_works, locke_works, pascal_works, rousseau_works
from minerva.corpus.split_paragraphic import split_by_chapter


def test_find_work_resolves_filenames() -> None:
    assert hobbes_works.find_work("leviathan.txt") is not None
    assert pascal_works.find_work("pensees.txt") is not None
    assert hume_works.find_work("enquiry.txt") is not None
    assert hume_works.find_work("treatise.txt") is not None
    assert locke_works.find_work("essay.txt") is not None
    assert locke_works.find_work("second_treatise.txt") is not None
    assert rousseau_works.find_work("contrat_social.txt") is not None


def test_chapter_splitter_emits_chunks_on_sample_prose() -> None:
    work = hobbes_works.find_work("leviathan.txt")
    assert work is not None
    text = (
        "CHAPTER I\n"
        "Of Sense\n"
        "Concerning the thoughts of man, I will consider them following.\n\n"
        "CHAPTER II\n"
        "Of Imagination\n"
        "After the object is removed, we retain an image.\n"
    )
    chunks = list(split_by_chapter(text, work, Path("leviathan.txt")))
    assert len(chunks) >= 2
    assert all(c.author == "Hobbes" for c in chunks)
    assert all(c.corpus == "hobbes" for c in chunks)
