"""Split a flattened facing-page edition into translation and apparatus (#675).

Miller's Loeb *De Officiis* (Project Gutenberg 47001) prints Cicero's
Latin on the left page and the English on the right. The transcription
flattens each spread into alternating blocks, as its transcriber's note
says: every Roman-numeral chapter gives its Latin, then its English.
Around them sit the critical apparatus (``[1]``), the translator's
footnotes (``[A]``), the marginal sidenotes (``#…#``), and the
introduction, bibliography and index. All of it was ingested as
Cicero's English — 27% of the chunks were Latin.

The source's own markup carries the structure, so no language guess is
involved:

* The body runs from the first ``LIBER … / BOOK …`` line to ``INDEX``;
  everything outside it is front or back matter.
* A footnote is indented four spaces and opens with a bracketed marker,
  or continues the footnote before it at the same indent. Verse
  quotations are indented too, but never open with a marker and never
  follow a footnote.
* A paragraph that is one ``#…#`` sidenote is the editor's marginalia.
* Each chapter numeral opens a paragraph twice per book: the first is
  the Latin, the second the English. Two chapters that share a
  paragraph in the source advance the count by two, so a numeral is
  only honoured at the current chapter or one or two past it — which is
  also what keeps a praenomen (``L. Minuci``, ``C. Marius``) from
  reading as chapter 50 or 100. A chapter the spread breaks in two
  resumes under its numeral in parentheses (``*44* (XIII.)``), and that
  pair opens a second Latin-then-English round of the same chapter.

The pass runs after the splitter, on its chunks, so ids are already
fixed: the Latin chunks are dropped, the apparatus is re-typed, and no
kept chunk's ``chunk_id`` or text changes. Embeddings, lemmas and
cross-references on the English survive the re-ingest.

Any mismatch raises. A chunk that cannot be found in the source, or a
chapter whose English never arrives, means the source drifted — and
guessing then would either drop English or index Latin as English.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable

from ..tei import Chunk, _norm_text

#: The body opens at each book's ``LIBER PRIMUS / BOOK I`` line.
_BOOK_RE = re.compile(r"^LIBER \w+ / BOOK [IVXL]+$")
#: The back matter opens at the index.
_BACK_MATTER = "INDEX"
#: A chapter opener: optional marginal section number, then the numeral.
_CHAPTER_RE = re.compile(r"^(?:\*\d+\*\s+)?(\()?([IVXLC]+)\.(?(1)\))\s")
_SIDENOTE_RE = re.compile(r"^#[^#]*#$")
_FOOTNOTE_INDENT = "    "
_NUMERALS = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}

ORIGINAL = "original"
TRANSLATION = "translation"
NOTE = "note"
EDITORIAL = "editorial"


def _roman(numeral: str) -> int:
    total = 0
    for here, after in zip(numeral, [*numeral[1:], None], strict=True):
        value = _NUMERALS[here]
        total += -value if after is not None and _NUMERALS[after] > value else value
    return total


def _is_footnote(para: str, previous_role: str | None) -> bool:
    if not para.startswith(_FOOTNOTE_INDENT) or para[len(_FOOTNOTE_INDENT)].isspace():
        return False
    return para.lstrip().startswith("[") or previous_role == NOTE


class _Chapters:
    """The Latin-then-English state for one book."""

    def __init__(self, book: int) -> None:
        self.book = book
        self.current = 0
        self.role: str | None = None
        self.untranslated: list[int] = []

    def see(self, text: str) -> str | None:
        match = _CHAPTER_RE.match(text)
        if match:
            self._advance(_roman(match.group(2)), resumed=match.group(1) is not None)
        return self.role

    def _advance(self, number: int, *, resumed: bool) -> None:
        if number == self.current and self.role == ORIGINAL:
            self.role = TRANSLATION
            self.untranslated.remove(number)
        elif resumed and number == self.current and self.role == TRANSLATION:
            self.role = ORIGINAL
            self.untranslated.append(number)
        elif self.current < number <= self.current + 2 and self.role != ORIGINAL:
            self.current = number
            self.role = ORIGINAL
            self.untranslated.append(number)

    def close(self, work: str) -> None:
        if self.untranslated:
            raise ValueError(
                f"{work!r}: chapter(s) {self.untranslated} of book {self.book} have no translation"
            )


def classify_paragraphs(text: str, work: str) -> list[tuple[str, str]]:
    """Return ``(normalised text, role)`` for each blank-line paragraph."""

    out: list[tuple[str, str]] = []
    books: list[_Chapters] = []
    in_back_matter = False
    previous: str | None = None
    for para in (p.lstrip("\n") for p in re.split(r"\n\s*\n", text) if p.strip()):
        norm = _norm_text(para)
        if _BOOK_RE.match(norm):
            books.append(_Chapters(len(books) + 1))
            role = EDITORIAL
        elif norm == _BACK_MATTER:
            in_back_matter = True
            role = EDITORIAL
        else:
            chapters = books[-1] if books and not in_back_matter else None
            role = _body_role(para, norm, previous, chapters)
        out.append((norm, role))
        previous = role
    if not books:
        raise ValueError(f"{work!r}: no facing-text book heading found")
    for book in books:
        book.close(work)
    return out


def _body_role(para: str, norm: str, previous: str | None, chapters: _Chapters | None) -> str:
    if chapters is None:
        return EDITORIAL
    if _is_footnote(para, previous):
        return NOTE
    if _SIDENOTE_RE.match(norm):
        return EDITORIAL
    return chapters.see(norm) or EDITORIAL


def _roles_for(chunks: Iterable[Chunk], paragraphs: list[tuple[str, str]], work: str) -> list[str]:
    """Align each chunk, in order, to the source paragraph that holds it.

    The splitter consumes a heading-shaped first line, so a chunk is a
    substring of its paragraph rather than equal to it, and two chunks
    can share one. Matching moves strictly forward.
    """

    roles: list[str] = []
    index, offset = 0, 0
    for chunk in chunks:
        while index < len(paragraphs):
            found = paragraphs[index][0].find(chunk.text, offset)
            if found >= 0:
                offset = found + len(chunk.text)
                break
            index, offset = index + 1, 0
        else:
            raise ValueError(f"{work!r}: chunk {chunk.text[:60]!r} not found in the source")
        roles.append(paragraphs[index][1])
    return roles


def split_facing_text(chunks: list[Chunk], text: str, work: str) -> list[Chunk]:
    """Drop the original-language chunks and type the apparatus."""

    roles = _roles_for(chunks, classify_paragraphs(text, work), work)
    out: list[Chunk] = []
    for chunk, role in zip(chunks, roles, strict=True):
        if role == ORIGINAL:
            continue
        if role in (NOTE, EDITORIAL):
            chunk = dataclasses.replace(chunk, block_type=role)
        out.append(chunk)
    return out
