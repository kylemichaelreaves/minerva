"""Type per-work editorial runs in place (#705).

Project Gutenberg apparatus — a transcriber's note, a corrections list,
the PG header — reaches the splitters as ordinary body paragraphs, so
the editorial-heading predicate (#534) never sees it and it is indexed
as the author's own text. Promoting those paragraphs to headings would
change their ``section``, which feeds ``chunk_id``, and would re-home
whatever body follows a head note.

So each run is named per work instead, by the paragraph that opens it
and the one after it ends (``CorpusWork.editorial_runs``), and its
chunks are re-typed ``block_type='editorial'`` after their ids exist.
No text changes, so no id does: embeddings, lemmas and cross-references
survive the re-ingest.

A configured run that no longer matches raises. Source drift must fail
the ingest rather than type nothing — or, with an unmatched closer,
everything to the end of the work.
"""

from __future__ import annotations

import dataclasses

from ..corpus_works import CorpusWork
from ..tei import Chunk


def _starts(chunk: Chunk, prefix: str) -> bool:
    # Meditations' first chunk carries a byte-order mark.
    return chunk.text.lstrip("﻿").lstrip().startswith(prefix)


def _find(chunks: list[Chunk], prefix: str, start: int) -> int | None:
    return next((i for i in range(start, len(chunks)) if _starts(chunks[i], prefix)), None)


def apply_editorial_runs(chunks: list[Chunk], work: CorpusWork) -> list[Chunk]:
    """Return ``chunks`` with every configured run typed ``editorial``.

    Runs are matched in order: each opener is searched for after the
    previous run ends, and each closer after its own opener. A closer of
    ``None`` runs to the end of the work.
    """

    if not work.editorial_runs:
        return chunks
    out = list(chunks)
    pos = 0
    for opener, closer in work.editorial_runs:
        begin = _find(out, opener, pos)
        if begin is None:
            raise ValueError(f"{work.title!r}: editorial run opener {opener!r} not found")
        end = len(out) if closer is None else _find(out, closer, begin + 1)
        if end is None:
            raise ValueError(f"{work.title!r}: editorial run closer {closer!r} not found")
        for i in range(begin, end):
            out[i] = dataclasses.replace(out[i], block_type="editorial")
        pos = end
    return out
