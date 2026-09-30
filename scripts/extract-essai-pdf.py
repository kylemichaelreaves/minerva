#!/usr/bin/env python3
"""Extract Boulainvilliers's *Essai sur la noblesse de France* from
the Gallica PDF (the one with a text layer — replaces the broken
EPUB extraction).

The PDF is the user's second download attempt, a much smaller
17 MB file (vs. the original 164 MB image-only download). PyMuPDF
sees text on 495 of 507 pages — Gallica embedded the OCR text layer
this time. We pull page-by-page, read the page furniture off by its
*position*, and hand off to the standard Boulainvilliers cleanup
(long-s → s, ligatures, dictionary-guided f→s).

Run it in an environment that has both PyMuPDF and ``pyspellchecker``;
the cleanup's f→s pass needs the latter and it is not a project
dependency::

    uv run --no-project --with pymupdf --with pyspellchecker \\
        python scripts/extract-essai-pdf.py [OUT]

**Spaces (#561).** Gallica's text layer stores each OCR'd word as its
own span, and most spans carry no space glyph. Every PyMuPDF text mode
— ``text``, ``words`` *and* ``blocks``, which the first version of this
script used believing it kept them — concatenates adjacent spans
without one, so the file came out as ``DiffertationsurlaNobleffe``,
``Lestcertainquedansledroit``: 89 of the corpus's 159 run-together
tokens were this one file. The span boundaries are still there, so
`join_spans` puts the space back where one word's span ends and the
next begins.

**Furniture (#578).** Every page carries a running head (page number
and ``Dissertation sur la Noblesse`` / ``de France.``) in its top band,
and a signature mark (``A 3``, ``B``) and catchword (the next page's
first word) at its foot. The first version kept all three as text, and
because each OCR block became a blank-line paragraph they became chunks
of their own — or were glued to the body mid-sentence. They are
recognised here by where they sit on the page, which the text alone
cannot tell.

**Paragraphs (#578).** Each printed line is cleaned on its own, then the
lines are assembled into paragraphs by `corpus/ocr_reflow.assemble` — a
paragraph ends where a short last line or an indented first one shows it
does, or at a page break after a closed sentence — with the page's note
area, which only its position identifies, held aside while a paragraph
runs on across the break. The file holds one paragraph per line, so the
work is ingested without a second reflow.
"""

from __future__ import annotations

import re
import statistics
import sys
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from importlib import import_module
from itertools import pairwise
from pathlib import Path

PDF = Path.home() / "Downloads" / "Essais_sur_la_noblesse_de_France_contena.pdf"
OUT = Path(__file__).resolve().parent.parent / "data" / "boulainvilliers" / "essai_noblesse_fra.txt"

# Pages before this offset are Gallica cover / table-of-contents
# / library metadata, not the work itself. Sampled by hand:
# page 28-29 is the title page, body text starts around page 30.
BODY_START_PAGE = 28


@dataclass(frozen=True)
class Line:
    """One printed line, in page-relative coordinates (0–1)."""

    y: float
    x0: float
    x1: float
    size: float
    text: str


# ── Spaces ─────────────────────────────────────────────────────────

#: A span boundary is a word boundary unless one side is punctuation
#: that attaches: `Ceux` `-` `ci`, `(` `6` `)`, `maîtres` `.`,
#: `l'égalité` `'`. French typesetting spaces before `;:!?` and the
#: OCR keeps those as separate spans with their own leading space.
_ATTACH_LEFT = "-'’(["
_ATTACH_RIGHT = "-'’),.;:!?]"


def join_spans(spans: list[str]) -> str:
    """One line's text from its spans, with the lost word spaces back."""

    out = ""
    for span in spans:
        if not span:
            continue
        if out and _needs_space(out, span):
            out += " "
        out += span
    return re.sub(r"\s+", " ", out).strip()


def _needs_space(left: str, right: str) -> bool:
    if left[-1].isspace() or right[0].isspace():
        return False
    return left[-1] not in _ATTACH_LEFT and right[0] not in _ATTACH_RIGHT


# ── Page lines ─────────────────────────────────────────────────────


def page_lines(page) -> list[Line]:
    """The page's printed lines in reading order."""

    return merge_fragments(fragments(page_dict(page)))


def page_dict(page) -> dict:
    """The part of PyMuPDF's ``dict`` output this script reads: page size,
    and each text line's box and spans. Kept as plain data so the
    fixture under ``tests/fixtures/essai_pdf/`` can stand in for the PDF."""

    lines = [
        {
            "bbox": list(ln["bbox"]),
            "spans": [{"text": s["text"], "size": s["size"]} for s in ln["spans"]],
        }
        for block in page.get_text("dict")["blocks"]
        if block["type"] == 0
        for ln in block["lines"]
    ]
    return {"width": page.rect.width, "height": page.rect.height, "lines": lines}


def fragments(data: dict) -> list[Line]:
    """PyMuPDF's lines, which are OCR fragments: a single printed line can
    arrive as two (`du Roi` … `tenans de la Nation`); `merge_fragments`
    puts them back together."""

    width, height = data["width"], data["height"]
    out: list[Line] = []
    for ln in data["lines"]:
        text = join_spans([s["text"] for s in ln["spans"]])
        if not text or _is_stray_glyph(text):
            continue
        x0, y0, x1, y1 = ln["bbox"]
        size = max(s["size"] for s in ln["spans"])
        out.append(Line((y0 + y1) / 2 / height, x0 / width, x1 / width, size, text))
    return out


#: A fragment of one to three characters with no Latin letter or digit —
#: `،`, `د`, `ॐ` — is scan noise the OCR read as another script.
_STRAY_MAX_CHARS = 3


def _is_stray_glyph(text: str) -> bool:
    if len(text) > _STRAY_MAX_CHARS:
        return False
    return not any(c.isdigit() or ("LATIN" in unicodedata.name(c, "")) for c in text)


def merge_fragments(frags: list[Line]) -> list[Line]:
    """Merge fragments whose vertical centres fall within half a line of
    each other, left to right; return the lines top to bottom."""

    if not frags:
        return []
    tolerance = statistics.median(f.size for f in frags) / 2 / _PAGE_POINTS
    rows: list[list[Line]] = []
    for frag in sorted(frags, key=lambda f: f.y):
        if rows and abs(frag.y - rows[-1][0].y) <= tolerance:
            rows[-1].append(frag)
        else:
            rows.append([frag])
    out = []
    for row in rows:
        row.sort(key=lambda f: f.x0)
        out.append(
            Line(
                row[0].y,
                row[0].x0,
                max(f.x1 for f in row),
                max(f.size for f in row),
                " ".join(f.text for f in row),
            )
        )
    return out


#: Page height in points, for turning a font size into a page fraction.
#: The scans are all within a few points of 490.
_PAGE_POINTS = 490.0


# ── Furniture ──────────────────────────────────────────────────────

#: Top band: the running head lives above this fraction of the page.
_HEAD_BAND = 0.12
#: Foot band: signature marks and catchwords live below this.
_FOOT_BAND = 0.70
#: Printed running-head titles across the volume's dissertations.
_HEAD_TITLES = (
    "Dissertation sur la noblesse",
    "de France",
    "Dissertation sur l'origine",
    "des Francs",
    "Table",
)
#: A head in the top band that is only a page number, a glyph the OCR
#: made of one, or a dictionary guide word (`ARC`, `GEN`).
_HEAD_SHORT_MAX = 4
_TITLE_MATCH = 0.7
#: `A 3`, `B`, `* C 2`, `Aa ij`: gathering letter and leaf number.
#: Capitals only: the first version allowed `[A-Z][a-z]?` and dropped
#: `Le`, `La`, `Je` and `Roi` (`R` + `o` + roman `i`) from the foot of
#: pages where they were the last word of the page's text.
_SIGNATURE_RE = re.compile(r"^\*?\s?[A-Z]{1,2}\s?(?:\d{1,2}|[ij]{1,3})?$")
#: Signatures and catchwords are set right or centre; a short line at
#: the left margin is the tail of a paragraph (`ques.`).
_FOOT_MIN_X = 0.45
_CATCHWORD_MAX_CHARS = 15


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.replace("ſ", "s"))
    return "".join(c for c in decomposed if c.isalpha() and not unicodedata.combining(c)).lower()


def is_running_head(line: Line) -> bool:
    if line.y > _HEAD_BAND:
        return False
    compact = line.text.replace(" ", "")
    if len(compact) <= _HEAD_SHORT_MAX:
        return True
    tokens = line.text.split()
    if len(tokens) <= 3 and all(_is_head_token(t) for t in tokens):
        # `ARB 19`, `24 ARC`, `PAG ITI`: the glossary's guide word and folio.
        return True
    body = re.sub(r"^\S*\d\S*\s+|\s+\S*\d\S*$", "", line.text)
    folded = _fold(body)
    return any(
        SequenceMatcher(None, folded, _fold(t)).ratio() >= _TITLE_MATCH for t in _HEAD_TITLES
    )


def _is_head_token(token: str) -> bool:
    return (
        any(c.isdigit() for c in token) or len(token) <= 2 or (token.isupper() and len(token) <= 4)
    )


def is_signature(line: Line) -> bool:
    return line.y >= _FOOT_BAND and line.x0 >= _FOOT_MIN_X and bool(_SIGNATURE_RE.match(line.text))


def is_catchword(line: Line, next_page_first: str | None) -> bool:
    """A short right-set line that the next page's text begins with.

    Compared folded — letters only, and `f` read as the long `s` it so
    often is — because the OCR reads the two copies of the word
    independently: `caufe` for `cauſe`, `Ro-` for `Romains`, `remment ,`.
    A leading signature (`* A 4 valoir`) is ignored.
    """

    if line.y < _HEAD_BAND or line.x0 < _FOOT_MIN_X or len(line.text) > _CATCHWORD_MAX_CHARS:
        return False
    if not next_page_first:
        return False
    tokens = line.text.split()
    while len(tokens) > 1 and _is_signature_token(tokens[0]):
        tokens.pop(0)
    catch = _fold_catch(" ".join(tokens))
    return len(catch) >= 2 and _fold_catch(next_page_first).startswith(catch)


def _is_signature_token(token: str) -> bool:
    return token == "*" or bool(re.fullmatch(r"[A-Z]{1,2}|\d{1,2}|[A-Z]{1,2}-?\d{1,2}", token))


def _fold_catch(text: str) -> str:
    return _fold(text).replace("f", "s")


def strip_furniture(
    pages: list[list[Line]],
) -> tuple[list[list[Line]], list[int], list[tuple[int, str, str]]]:
    """Pages without running heads, signatures and catchwords; the index on
    each page where its note area begins; and ``(page index, kind, text)``
    for every line removed — the sweep."""

    dropped: list[tuple[int, str, str]] = []
    kept: list[list[Line]] = []
    for i, lines in enumerate(pages):
        body = []
        for line in lines:
            if is_running_head(line):
                dropped.append((i, "running head", line.text))
            elif is_signature(line):
                dropped.append((i, "signature", line.text))
            else:
                body.append(line)
        kept.append(body)
    notes_at: list[int] = []
    for i, body in enumerate(kept):
        nxt = kept[i + 1][0].text if i + 1 < len(kept) and kept[i + 1] else None
        # The catchword closes the page's *text*, which on a page with
        # footnotes is above them — so the last candidate, not the last
        # line — and where it stood is where the notes begin.
        hits = [j for j, line in enumerate(body) if is_catchword(line, nxt)]
        if hits:
            dropped.append((i, "catchword", body.pop(hits[-1]).text))
            notes_at.append(hits[-1])
        else:
            notes_at.append(note_area_start(body))
    return kept, notes_at, dropped


#: The note area is set tighter than the text: a gap this many times the
#: page's line pitch, below the middle of the page, followed by lines at
#: no more than `_NOTE_PITCH` of the text's pitch, starts it. A heading
#: also sits after a wide gap, but the lines under it are text-spaced —
#: and when a page has both, the notes are the *last* such gap: taking
#: the first put page 61's side-head `Distinction de la Noblesse
#: Françoise` and the paragraph under it into the notes.
_NOTE_GAP = 1.4
_NOTE_PITCH = 0.8
_NOTE_MIN_Y = 0.45


def note_area_start(lines: list[Line]) -> int:
    """Index of the first footnote line, or ``len(lines)`` if none."""

    if len(lines) < 4:
        return len(lines)
    gaps = [b.y - a.y for a, b in pairwise(lines)]
    pitch = statistics.median(gaps)
    for i in range(len(gaps) - 1, 0, -1):
        # gaps[i - 1] is the gap above lines[i]; gaps[i:] are those below it.
        if lines[i].y < _NOTE_MIN_Y or gaps[i - 1] < _NOTE_GAP * pitch:
            continue
        if statistics.median(gaps[i:]) <= _NOTE_PITCH * pitch:
            return i
    return len(lines)


# ── Paragraph ends within a page ──────────────────────────────────

#: A line this far short of the right margin ends its paragraph.
_SHORT_LINE = 0.08
#: A line this far in from the left margin starts one.
_INDENT = 0.025
_SENTENCE_END_RE = re.compile(r"[.?!:]\s*['\"’”»)]*\s*$")


def page_items(lines: list[Line], notes_at: int) -> list[tuple[str, str]]:
    """One page as ``(kind, text)`` for `ocr_reflow.assemble`: its text
    lines, a blank where a paragraph visibly ends or begins, then its note
    area from ``notes_at`` on, and a blank for the page break."""

    from minerva.corpus.ocr_reflow import BLANK, BODY, NOTE

    if not lines:
        return []
    left = statistics.median(ln.x0 for ln in lines)
    right = statistics.median(ln.x1 for ln in lines)
    out: list[tuple[str, str]] = []
    for i, line in enumerate(lines):
        if i >= notes_at:
            out.append((NOTE, line.text))
            continue
        if i and line.x0 - left >= _INDENT:
            out.append((BLANK, ""))
        out.append((BODY, line.text))
        if right - line.x1 >= _SHORT_LINE and _SENTENCE_END_RE.search(line.text):
            out.append((BLANK, ""))
    out.append((BLANK, ""))
    return out


def _extract() -> tuple[list[str], list[tuple[int, str, str]]]:
    import pymupdf  # type: ignore[import-untyped]

    from minerva.corpus.ocr_reflow import assemble
    from minerva.corpus.split_paragraphic import is_heading_line

    with pymupdf.open(PDF) as doc:
        pages = [page_lines(doc[i]) for i in range(BODY_START_PAGE, len(doc))]
    kept, notes_at, dropped = strip_furniture(pages)
    items = [item for page, at in zip(kept, notes_at, strict=True) for item in page_items(page, at)]
    paragraphs = assemble(items, is_heading_line)
    return paragraphs, [(i + BODY_START_PAGE, kind, t) for i, kind, t in dropped]


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    if not PDF.exists():
        print(f"PDF not found: {PDF}", file=sys.stderr)
        return 1
    here = Path(__file__).resolve().parent
    sys.path[:0] = [str(here), str(here.parent / "src")]
    clean_text = import_module("clean-boulainvilliers-texts").clean_text
    print(f"Reading {PDF.name} ...", file=sys.stderr)
    paragraphs, dropped = _extract()
    # The cleanup runs per *paragraph*, after assembly. Its filters are
    # line filters, and run on single printed lines they drop body text: a
    # trial run that cleaned line by line lost 146 lines, among them
    # ordinary French made of short words that `_is_column_edge_garbage`
    # takes for margin debris (`il y avoit , au commencement de la`).
    cleaned = []
    for para in paragraphs:
        text = clean_text(para).strip()
        if text:
            cleaned.append(text)
        else:
            dropped.append((-1, "emptied by cleanup", para))
    text = "\n\n".join(cleaned)
    print(f"  {len(text):,} chars; lines dropped: {len(dropped)}", file=sys.stderr)
    out.write_text(text + "\n", encoding="utf-8")
    sweep = out.with_suffix(".furniture.tsv")
    sweep.write_text("".join(f"{p}\t{k}\t{t}\n" for p, k, t in dropped), encoding="utf-8")
    print(f"Wrote {out} (+ every dropped line in {sweep.name})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
