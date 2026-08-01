#!/usr/bin/env python3
"""Extract Hegel's *Elements of the Philosophy of Right* editor's
endnotes from the EPUB and emit them as a stand-alone HTML file
that the standard corpus-label pipeline can chunk.

The Cambridge edition (Nisbet trans., Wood ed.) ships 442 editor's
endnotes split across two EPUB endnote pages (``part0029.html`` for
§§ 1-179 + the Preface, ``part0030.html`` for §§ 180+). Each note
spans one or more ``<p class="note*">`` paragraphs (the bare
``note`` class for single-digit notes, ``note1`` for double-digit,
plus ``note-block``, ``note-numbert``, ``note-poem`` etc. for
continuations).

Output: ``data/hegel/elements_phil_of_right_eng_editors_notes.html``,
structured as::

    <h2>Preface notes</h2>
    <p>1. Hegel lectured on the topics in the Philosophy of Right...</p>
    <p>2. ...</p>
    ...
    <h2>§ 180 notes</h2>
    <p>1. This seems to be a reference to Fichte's actual doctrine...</p>
    ...

The ``locator="chapter"`` splitter on the ``pr_notes`` CorpusWork
catches the ALL-CAPS-style chapter heads (CHAPTER N pattern) — the
section headers here use the ``[A-Z][A-Z \\-—:,'.]{6,80}`` ALL-CAPS
branch, so each ``§ N NOTES`` heading becomes its own chunk.

The body of Phil of Right (the ``pr`` CorpusWork) remains unmodified
— it keeps bare-number markers exactly where the Cambridge typesetter
placed them, so the printed-page reading experience is preserved.
"""

from __future__ import annotations

import html
import re
import sys
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parent.parent
EPUB = (
    REPO_ROOT
    / "data" / "hegel"
    / "Elements of the Philosophy of Right (Cam - Georg Wilhelm Friedrich Hegel.epub"
)
OUT = (
    REPO_ROOT / "data" / "hegel"
    / "elements_phil_of_right_eng_editors_notes.html"
)

ENDNOTE_FILES = ["text/part0029.html", "text/part0030.html"]


def _collect_sections(zf: zipfile.ZipFile) -> list[tuple[str, list[tuple[int, str]]]]:
    """Walk the endnote pages in spine order; return a list of
    ``(section_label, [(note_num, note_text), ...])`` tuples in
    document order.

    Section labels come from the ``<h6>`` headings the EPUB uses
    above each section's notes — ``Preface``, ``§ 1``, ``§ 2``, etc.
    Note paragraphs immediately following a heading belong to that
    section; the next heading closes the previous group.

    Multi-paragraph notes are stitched: any ``<p>`` whose class
    contains ``note`` and doesn't host a ``sec``/``preen`` anchor
    gets appended to the current note's text.
    """

    sections: list[tuple[str, list[tuple[int, str]]]] = []
    current_label: str | None = None
    current_notes: list[tuple[int, str]] = []

    def _flush() -> None:
        if current_label is not None and current_notes:
            sections.append((current_label, current_notes.copy()))

    for path in ENDNOTE_FILES:
        try:
            html_text = zf.read(path).decode("utf-8", errors="replace")
        except KeyError:
            print(f"  (endnote file {path} not in EPUB — skipping)", file=sys.stderr)
            continue
        soup = BeautifulSoup(html_text, "html.parser")
        body = soup.find("body") or soup

        last_note_num: int | None = None

        for el in body.find_all(["h6", "h2", "h3", "p"]):
            if el.name in ("h6", "h2", "h3"):
                # New section. Flush the previous group, start fresh.
                _flush()
                current_label = el.get_text(" ", strip=True)
                current_notes = []
                last_note_num = None
                continue
            # <p> branch.
            classes = el.get("class") or []
            if not any("note" in c for c in classes):
                continue
            # Anchor present? Then this <p> begins a NEW note.
            anchor = el.find(
                "a",
                id=lambda x: x and x.startswith(("sec", "preen")),
            )
            text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
            if anchor is not None:
                # New note. Pull the note number from the leading
                # "1 " / "12 " prefix the EPUB renders before the
                # actual note text.
                m = re.match(r"^(\d+)\s*(.*)$", text)
                if m:
                    note_num = int(m.group(1))
                    note_text = m.group(2).strip()
                else:
                    note_num = (last_note_num or 0) + 1
                    note_text = text
                current_notes.append((note_num, note_text))
                last_note_num = note_num
            else:
                # Continuation paragraph for the most recent note.
                if current_notes:
                    n, t = current_notes[-1]
                    current_notes[-1] = (n, (t + " " + text).strip())
    _flush()
    return sections


def _emit_html(sections: list[tuple[str, list[tuple[int, str]]]]) -> str:
    """Render the collected notes as a simple HTML doc.

    Each section header becomes ``<h2>SECTION_LABEL NOTES</h2>``
    (uppercased to hit the chapter-splitter's ALL-CAPS branch);
    each note becomes one ``<p>`` with the number and content.
    """

    parts: list[str] = [
        "<!doctype html>\n<html lang=\"en\"><head>"
        "<meta charset=\"utf-8\">"
        "<title>Elements of the Philosophy of Right "
        "— Editor's Notes</title>"
        "</head><body>\n"
    ]
    # Headings must match the chapter-splitter's first regex branch
    # — ``(CHAPTER|PART|BOOK|SECTION|LECTURE)\s+[IVXLC0-9]+...`` —
    # so each notes section becomes its own chunk with
    # ``book="<heading>"``. Prefix every group with literal
    # ``SECTION`` to satisfy the keyword constraint; use index 0
    # for the Preface so it sorts first.
    for label, notes in sections:
        m = re.match(r"^\s*§\s*(\d+)\b", label)
        if m:
            heading = f"SECTION {m.group(1)} NOTES"
        elif "preface" in label.lower():
            heading = "SECTION 0 PREFACE NOTES"
        else:
            # Other ad-hoc labels (e.g. "The Braggart" from the
            # Aesop fable in PR Preface footnotes). Tag them as
            # section "X" so the regex matches; the actual text
            # tells the reader which note grouping it is.
            heading = f"SECTION X NOTES — {label.upper()}"
        parts.append(f"<h2>{html.escape(heading)}</h2>\n")
        for num, text in notes:
            parts.append(
                f"<p>{num}. {html.escape(text)}</p>\n"
            )
    parts.append("</body></html>\n")
    return "".join(parts)


def main() -> int:
    if not EPUB.exists():
        print(f"EPUB not found: {EPUB}", file=sys.stderr)
        return 1
    print(f"Reading {EPUB.name}", file=sys.stderr)
    with zipfile.ZipFile(EPUB) as zf:
        sections = _collect_sections(zf)
    print(f"  collected {len(sections)} note sections", file=sys.stderr)
    note_count = sum(len(n) for _, n in sections)
    print(f"  total individual notes: {note_count}", file=sys.stderr)

    html_doc = _emit_html(sections)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {OUT}  ({len(html_doc):,} chars)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
