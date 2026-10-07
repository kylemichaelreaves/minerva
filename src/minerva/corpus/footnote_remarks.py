"""Type an author's own OCR'd footnotes ``block_type='remark'`` in place (#732).

`ocr_reflow` keeps a scan's footnotes as text and emits each as a
paragraph of its own, so every one becomes a chunk the splitter types as
body. In Renan that is 6,049 of 12,067 chunks. They are his own notes —
the works are untranslated — so the type is ``remark``, the precedent
being Marx's footnotes in *Kapital* (`split_kapital_mew`). ``note`` would
be wrong: it is an apparatus type (`block_types.APPARATUS_TYPES`), which
retrieval reattributes away from the author and the lemmatizer skips.

This runs after the chunk ids exist and changes nothing but the type, so
no id moves and embeddings, lemmas and cross-references survive the
re-ingest. Typing at emit time instead would bypass the splitter's
bibliography filter, which notes would then reach.

The rule is the one `ocr_reflow` uses to hold notes aside, plus the
markers the OCR mangled (`i. `, `1 . `, `S. `). Reflow's own regex is
left alone: a change to it changes which lines it holds aside, so it
would change text and ids.
"""

from __future__ import annotations

import dataclasses
import re

from ..corpus_works import CorpusWork
from ..tei import Chunk
from .ocr_reflow import _NOTE_OPEN_RE

#: Note markers as the Renan OCR misreads them: `1` read as `i`
#: (`i. `, `i . `, `(i. `), a stray space before the full stop (`1 . `),
#: `5`/`4` read as `S`/`A` — the last only before a capital, since a
#: note opens on its first word. Swept over all seven volumes: of the
#: ~190 notes `_NOTE_OPEN_RE` misses, this finds 170.
_MANGLED_NOTE_OPEN_RE = re.compile(r"^(?:\(?i ?\. |\d ?\. |[SA]\. (?=[A-ZÉ«]))")

#: A `*`-marked line in capitals is a heading the OCR gave a stray
#: asterisk (`* IMMORTALITE DE L AME CHEZ LES JUIFS.`), not a note.
_HEADING_MIN_UPPER = 0.9


def _is_capital_heading(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) >= _HEADING_MIN_UPPER


def opens_footnote(text: str) -> bool:
    """Whether a reflowed paragraph is a footnote, by its opening marker."""

    stripped = text.strip()
    if _NOTE_OPEN_RE.match(stripped):
        return not (stripped.startswith("*") and _is_capital_heading(stripped))
    return bool(_MANGLED_NOTE_OPEN_RE.match(stripped))


def apply_footnote_remarks(chunks: list[Chunk], work: CorpusWork) -> list[Chunk]:
    """Return ``chunks`` with each untyped footnote typed ``remark``, for a
    work that sets ``footnote_remarks``. A chunk already typed keeps its
    type: an editorial run is still editorial."""

    if not work.footnote_remarks:
        return chunks
    return [
        dataclasses.replace(c, block_type="remark")
        if c.block_type is None and opens_footnote(c.text)
        else c
        for c in chunks
    ]
