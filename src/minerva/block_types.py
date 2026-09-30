"""Shared meanings for ``chunks.block_type`` values.

Most block types say *how* the author's text is organised (``remark``,
``addition``, ``objection``). The apparatus types say *whose* text it is:
a translator's or editor's footnote (``note``), editorial matter an
ingest separated from the body (``editorial``), a dramatis-personae
list (``cast``), or a fragment a source attributes to the author that
the editor judges doubtful, false or forged (``spurious``, Diels's
ZWEIFELHAFTE / UNECHTE / GEFÄLSCHTE sections, #683). None of them is the
author's words, so every consumer that attributes text to an author must
treat them alike — retrieval reattributes them away from the author and
caps them, and the lemmatizer does not lemmatize them at all, so the
concordance never counts them (#674).
"""

from __future__ import annotations

APPARATUS_TYPES: tuple[str, ...] = ("note", "cast", "editorial", "spurious")
APPARATUS_LABEL: dict[str, str] = {
    "note": "editorial note",
    "cast": "cast list",
    "editorial": "editorial apparatus",
    "spurious": "doubtful or spurious fragment",
}
