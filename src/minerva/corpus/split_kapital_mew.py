"""Splitter for Das Kapital I–III from the mlwerke.de MEW pages.

Source: per-chapter HTML files fetched by
``perseus/download_kapital_mew.py`` into ``data/marx/raw_mew/``
(Wayback snapshot of mlwerke.de; MEW = Marx-Engels-Werke, Dietz,
Berlin/DDR — the edition scholarship cites).

Emitted structure:

* one chunk per body paragraph; ``section`` =
  ``"<chapter label>, ¶ <n>"`` (¶ numbered continuously through the
  chapter page), ``book`` = the chapter label from the page
  ``<TITLE>`` ("1. Die Ware", "Vorwort zur ersten Auflage", …);
* ``page`` = the **MEW page number** from the inline ``<A NAME="Sxx">``
  anchors — the locator scholarly citations use ("MEW 23, S. 49");
* **Marx's own footnotes** (the ``<HR>``-separated "Fußnoten" block,
  ``<A NAME="Mn">`` bodies) become their own chunks, ``section`` =
  ``"<chapter label>, Fn. (n)"``, typed ``block_type='remark'`` —
  authorial set-apart matter, NOT 'note' (which the retrieval layer
  attributes to a translator/editor; these notes are Marx's voice and
  often carry the argument — the polemics against Senior, the
  technology-history note, etc.).

The previous source was a Google-Books OCR of the 1867 first edition:
55 mega-chunks of 85–582 KB with heavy scan noise and the six-chapter
1867 structure nobody cites. This replaces it wholesale.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..corpus_works import CorpusWork
from ..tei import Chunk, _make_chunk_id, _norm_text

# Inline MEW page marker as it appears in extracted text ("<49>").
_PAGE_MARK_RE = re.compile(r"<(\d{1,4})>")
# Footnote backlink arrow in note bodies ("<=").
_BACKLINK_RE = re.compile(r"<=\s*$")
# get_text(" ") leaves a space before punctuation whenever an inline
# element (<I>, <A>) ends right at it ("Karl Marx , \"Zur Kritik…").
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?)])")

# A chunk must contain at least one letter — Kapital's numeric tables
# (the Band II reproduction schemas, the wage/price tables) linearize
# into hundreds of bare-number cell fragments otherwise.
_HAS_LETTER_RE = re.compile(r"[A-Za-zÄÖÜäöüß]")

# In-page chapter heading, printed centered in ordinal small caps:
# "ERSTES KAPITEL Die Ware", "SIEBENTES KAPITEL Umschlagszeit und
# Umschlagszahl". Band II's <TITLE> carries only the Abschnitt (part)
# label — all chapter files of one Abschnitt share it — so the
# in-page head is the authoritative chapter label everywhere.
_KAPITEL_HEAD_RE = re.compile(r"^([A-ZÄÖÜ]+)\s+KAPITEL\b\.?\s*(.*)$")
# Preface heads ("Vorwort", "[Vorwort zur zweiten Auflage]") — the two
# Band II preface files share the <TITLE> "Vorworte".
_VORWORT_HEAD_RE = re.compile(r"^\[?(Vorwort[^\]]*)\]?$")


def _kapitel_label(head: str) -> str | None:
    """Chapter label from one centered heading, or None."""

    m = _KAPITEL_HEAD_RE.match(head)
    if m:
        ordinal = m.group(1).capitalize()
        # A chapter heading can itself carry a footnote call —
        # "Achtzehntes Kapitel (34) Einleitung"; the marker belongs to
        # the note apparatus, not the label.
        title = re.sub(r"\(\d+\)", " ", m.group(2)).strip()
        title = re.sub(r"\s{2,}", " ", title)
        return f"{ordinal} Kapitel: {title}" if title else f"{ordinal} Kapitel"
    m = _VORWORT_HEAD_RE.match(head)
    if m:
        return m.group(1).strip()
    return None


_VOLUME_BY_PREFIX = {
    "me23": ("Das Kapital, Band I", "1867"),
    "me24": ("Das Kapital, Band II", "1885"),
    "me25": ("Das Kapital, Band III", "1894"),
}


def _volume_for_path(path: Path) -> tuple[str, str] | None:
    return _VOLUME_BY_PREFIX.get(path.name.split("_")[0])


def split_kapital_mew(path: Path, work: CorpusWork) -> Iterator[Chunk]:
    """Parse one MEW chapter page into paragraph + footnote Chunks."""

    try:
        from bs4 import BeautifulSoup
    except ImportError as e:  # pragma: no cover - env-dependent
        from ..corpus_extract import IngestDepsMissing

        raise IngestDepsMissing(
            "Kapital MEW ingest needs beautifulsoup4 + lxml (pip install 'minerva[hegel]')"
        ) from e

    if path.name.endswith("_000.htm"):
        # Volume table of contents — no body text.
        return
    vol = _volume_for_path(path)
    if vol is None:
        return

    # lxml, not html.parser: the mlwerke markup nests bold tags across
    # paragraph boundaries (`<B><P><A NAME="S49">…</A></B> text</P>`),
    # which html.parser resolves by dropping the paragraph's text out
    # of the <p>. lxml normalizes it. (Same class of problem as the
    # thelatinlibrary Spinoza pages.)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")

    # Chapter label from the <TITLE>: "Ware und Geld - 1. Die Ware" →
    # "1. Die Ware"; single-part titles (prefaces) stay whole.
    title_el = soup.find("title")
    title = _norm_text(title_el.get_text()) if title_el else path.stem
    book_label = title.rsplit(" - ", 1)[-1] if " - " in title else title

    # Strip the header chrome: the prev/Inhalt/next nav line and the
    # "Seitenzahlen verweisen auf: …" source note.
    for small in soup.find_all("small"):
        small.decompose()
    for p in soup.find_all("p", align=True):
        if p.find("a", href=True) and "Inhalt" in p.get_text():
            p.decompose()

    para_no = 0
    cur_page: str | None = None
    in_footnotes = False

    for p in soup.find_all("p"):
        if p.find("hr") is not None:
            continue
        # Table cells: Kapital's schemas and wage tables are 2-D
        # layouts that don't survive linearization ("60 + 60 = 120",
        # "Pfd.St.", bare digits, one cell per chunk). The surrounding
        # prose narrates every table; skip the cells.
        if p.find_parent("table") is not None:
            continue

        # Track the MEW page: the first S-anchor in this paragraph
        # dates the paragraph's start.
        s_anchors = [
            a.get("name")[1:] for a in p.find_all("a", attrs={"name": re.compile(r"^S\d+$")})
        ]

        raw = _norm_text(p.get_text(" "))
        if s_anchors:
            cur_page = s_anchors[0]
        text = _norm_text(_PAGE_MARK_RE.sub(" ", raw))
        text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
        if not text or not _HAS_LETTER_RE.search(text):
            continue
        if text == "Fußnoten":
            in_footnotes = True
            continue
        # Centered lines are headings/separators, never chunk text; a
        # KAPITEL/Vorwort head updates the book label (¶ numbering
        # continues through the file — labels differ, so sections
        # stay unique).
        if (p.get("align") or "").lower() == "center":
            label = _kapitel_label(text)
            if label:
                book_label = label
            continue

        if in_footnotes:
            m_anchor = p.find("a", attrs={"name": re.compile(r"^M\d+$")})
            if m_anchor is None:
                continue
            n = m_anchor.get("name")[1:]
            text = _norm_text(_BACKLINK_RE.sub("", text))
            section = f"{book_label}, Fn. ({n})"
            block_type: str | None = "remark"
        else:
            para_no += 1
            section = f"{book_label}, ¶ {para_no}"
            block_type = None

        work_title, _year = vol
        chunk_id = _make_chunk_id(
            path.name,
            work_title,
            work.lang,
            book_label,
            section,
            "",
            text[:120],
        )
        yield Chunk(
            chunk_id=chunk_id,
            corpus=work.corpus,
            author=work.author,
            work=work_title,
            lang=work.lang,
            section=section,
            book=book_label,
            page=cur_page,
            speaker=None,
            text=text,
            source_file=path.name,
            translator=work.translator,
            edition_year=work.edition_year,
            citation_system=work.citation_system,
            block_type=block_type,
        )
