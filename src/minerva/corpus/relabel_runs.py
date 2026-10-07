"""Give a per-work run of chunks one section label (#735).

The heading detector in `split_paragraphic` takes any short ALL-CAPS line
for a heading. In the English Leviathan's front matter that line is often
the wrapped tail of a longer title — ``ECCLESIASTICAL AND CIVILL`` under
the book's title, ``DEFECTS`` under ``8. OF THE VERTUES, … AND THEIR
CONTRARY`` — while the title's first line, which opens with a chapter
number, is not one. So the title page, transcriber's notes and dedication
were filed under ``Ecclesiastical and CIVILL``, and the table of contents
under thirteen labels made from chapter-title tails, one of which
(``Books of Holy Scripture``) occurs twice and minted ``¶1`` twice.

Fixing the detector is a corpus-wide change (#735's measurement: 7,157
duplicated locators across 70 files). So each run is named per work, as
`editorial_runs` names its runs, and relabelled after the splitter has
run: ``section = "<label>, ¶N"`` numbered across the whole run, and
``book = <label>``.

Unlike `editorial_runs` this changes ``chunk_id``, which hashes the
section. The id is re-minted from exactly the inputs
`split_paragraphic._emit` hashes, so it is the id the splitter would have
produced under this label. Chunks outside a run are returned untouched.
"""

from __future__ import annotations

import dataclasses

from ..corpus_works import CorpusWork
from ..tei import Chunk, _make_chunk_id
from .editorial_runs import run_spans


def apply_relabel_runs(chunks: list[Chunk], work: CorpusWork) -> list[Chunk]:
    """Return ``chunks`` with every configured run relabelled and re-minted."""

    if not work.relabel_runs:
        return chunks
    out = list(chunks)
    bounds = [(opener, closer) for opener, closer, _ in work.relabel_runs]
    spans = run_spans(out, bounds, f"{work.title!r}: relabel run")
    for (begin, end), (_, _, label) in zip(spans, work.relabel_runs, strict=True):
        for n, i in enumerate(range(begin, end), 1):
            out[i] = _relabelled(out[i], work, label, f"{label}, ¶{n}")
    return out


def _relabelled(chunk: Chunk, work: CorpusWork, label: str, section: str) -> Chunk:
    chunk_id = _make_chunk_id(
        chunk.source_file, work.title, work.lang, label, section, "", chunk.text[:120]
    )
    return dataclasses.replace(chunk, chunk_id=chunk_id, section=section, book=label)
