"""Shared meanings for ``chunks.block_type`` values.

Most block types say *how* the author's text is organised (``remark``,
``addition``, ``objection``). The apparatus types say *whose* text it is:
a translator's or editor's footnote (``note``), editorial matter an
ingest separated from the body (``editorial``), or a dramatis-personae
list (``cast``). None of them is the author's words, so every consumer
that attributes text to an author must treat them alike — retrieval
reattributes them to the translator/editor, and the lemmatizer does not
lemmatize them at all, so the concordance never counts them (#674).
"""

from __future__ import annotations

APPARATUS_TYPES: tuple[str, ...] = ("note", "cast", "editorial")
APPARATUS_LABEL: dict[str, str] = {
    "note": "editorial note",
    "cast": "cast list",
    "editorial": "editorial apparatus",
}
