"""Splitter for eKGWB (nietzschesource.org) saved-HTML pages of the
Nachlass — the digital Colli/Montinari *Nachgelassene Fragmente*.

These are hand-saved single notebook-group pages (e.g. group 25 = W I 1,
Frühjahr 1884), obtained one at a time for personal research and kept
local (gitignored), not bulk-scraped. The markup is regular: each
fragment is a `<div class="div1">` carrying a `<… class="head">` with the
intra-group number (`25[1]`) and a `<… class="txt_block">` with the
reading text. Editorial apparatus (`footnotes`, correction tooltips, UI
chrome) is the copyrighted critical layer and is dropped — we keep only
Nietzsche's public-domain fragment text.

Each fragment becomes one chunk whose `section` is the canonical eKGWB
siglum `NF-<year>,<group>[<n>]` (e.g. `NF-1884,25[1]`), so it cites and
cross-references at fragment granularity.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterator
from pathlib import Path

from ..corpus_extract import IngestDepsMissing
from ..corpus_works import CorpusWork
from ..tei import Chunk
from .split_paragraphic import _emit, _is_signature_line

# The page-level group header, e.g. "[25 = W I 1. Frühjahr 1884]" or
# "[25 = W I 1. Frühjahr 1884 — Herbst 1885]". We pull the group number
# and a 4-digit year to build canonical NF- sigla.
_GROUP_HEADER = re.compile(r"\[\s*(\d+)\s*=\s*[^.\]]*?\.?\s*[^\]]*?(\d{4})[^\]]*\]")
# A per-fragment head like "25[1]" / "25[247]".
_FRAG_HEAD = re.compile(r"^\s*(\d+)\s*\[\s*(\d+)\s*\]")

# Classes that carry editorial apparatus / UI chrome rather than
# Nietzsche's text — stripped before reading-text extraction.
_DROP_SELECTORS = (
    "script",
    "style",
    ".footnotes",
    ".no_print",
    ".tooltip",
    ".tooltip_corrige",
    ".close",
    ".stem",
    ".nlink",
    ".textlink",
    ".header_text",
)


def split_ekgwb(html: str, work: CorpusWork, path: Path) -> Iterator[Chunk]:
    """Split a saved eKGWB Nachlass page into one chunk per fragment.

    The parsed group header supplies a "Nachgelassene Fragmente 1884
    (Gruppe 25)"-style `book` label on each chunk.
    """

    try:
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]
    except ImportError as exc:
        raise IngestDepsMissing(
            "eKGWB ingest requires `beautifulsoup4`. Install with `pip install -e '.[hegel]'`."
        ) from exc

    soup = BeautifulSoup(html, "html.parser")

    # Year + group from the page header, used to build NF- sigla. Fall
    # back to the work's edition_year if the header isn't present.
    header_text = soup.get_text(" ", strip=True)
    hm = _GROUP_HEADER.search(header_text)
    group = hm.group(1) if hm else None
    year = (hm.group(2) if hm else None) or (work.edition_year or "").strip()[:4]
    book_label = f"Nachgelassene Fragmente {year}" + (f" (Gruppe {group})" if group else "")

    # Each fragment is a `.head` (the `25[1]` siglum) inside a `.div1`
    # block. Class-only selectors: the eKGWB elements carry xmlns
    # attributes that throw off bs4's tag-qualified CSS matching. We
    # iterate heads (one per fragment) rather than div1s, since the first
    # div1 is a non-fragment wrapper.
    for head_el in soup.select(".head"):
        head_txt = head_el.get_text(" ", strip=True)
        fm = _FRAG_HEAD.match(head_txt)
        if not fm:
            continue
        grp, num = fm.group(1), fm.group(2)
        siglum = f"NF-{year},{grp}[{num}]" if year else f"{grp}[{num}]"

        block = head_el.find_parent(class_="div1") or head_el.parent
        if block is None:
            continue
        # Strip the siglum label, editorial apparatus, and UI chrome so
        # only Nietzsche's reading text remains. Safe to mutate: each
        # head's block is visited once.
        for sel in (".head", *_DROP_SELECTORS):
            for tag in block.select(sel):
                tag.decompose()
        text = block.get_text(" ", strip=True)
        if not text:
            continue

        chunk = _emit(work, path, siglum, text, book_label=book_label)
        if chunk is None:
            continue
        # Some notebook fragments ARE Nietzsche drafting a book title —
        # "Der Spiegel. Versuch einer Selbstabschätzung. Von Friedrich
        # Nietzsche." — real text, but paratextual rather than
        # discursive, and it outranks his actual philosophy on any query
        # containing his name (#291).
        if _is_signature_line(chunk.text):
            chunk = dataclasses.replace(chunk, block_type="signature")
        yield chunk
