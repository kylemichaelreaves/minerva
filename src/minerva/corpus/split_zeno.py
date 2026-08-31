"""zeno.org HTML dumps from `perseus/download_hegel_de.py` carry
ZENO_PAGE markers — we use those for clean chapter boundaries rather
than guessing headings from extracted plain text. Each `<!-- ZENO_PAGE
-->` marker introduces one subpage; its URL path gives us a perfectly
clean chapter label without depending on regex heuristics applied to
extracted plain text.
"""

from __future__ import annotations

import dataclasses
import re
import urllib.parse
from collections.abc import Iterable, Iterator
from pathlib import Path

from ..corpus_extract import IngestDepsMissing
from ..corpus_works import CorpusWork
from ..heading_clean import _is_editorial_heading
from ..tei import Chunk
from .split_paragraphic import _split_chapter_block, _type_signature_lines

# zeno.org HTML dumps from `perseus/download_hegel_de.py` are
# concatenations of subpages, each preceded by a marker comment like
#     <!-- ZENO_PAGE: /Philosophie/M/Hegel,...../A.+Bewu%C3%9Ftsein/I.+... -->
# We use those markers as the chunk-boundary signal directly.
_ZENO_MARKER = re.compile(r"<!--\s*ZENO_PAGE:\s*([^\s][^\n]*?)\s*-->")


def _derive_zeno_heading(page_path: str, root_path: str) -> str:
    """Path → readable chapter label, e.g.
    `/.../Phänomenologie+des+Geistes/A.+Bewußtsein/I.+...` →
    `A. Bewußtsein › I. Die sinnliche Gewißheit ...`
    """

    if page_path == root_path:
        return ""  # work-root landing page; no specific chapter
    rel = page_path[len(root_path) + 1 :] if page_path.startswith(root_path + "/") else page_path
    rel = urllib.parse.unquote(rel.replace("+", " "))
    return rel.replace("/", " › ")


# ── Kant Anmerkungen ─────────────────────────────────────────────
# Kant sets his Anmerkungen (remarks) apart with a standalone
# "Anmerkung" / "Anmerkung I" head line; zeno's paragraph stream turns
# that head into its own tiny chunk and leaves the remark body
# indistinguishable from the main argument (Mode 2 of the
# block-structure remediation). Type the head AND the following
# paragraphs block_type='remark' until the next structural head
# (Beweis / Folgerung / Lehrsatz / § …) or the page ends. Typing only —
# text is untouched, so chunk_ids (and embeddings) stay stable.
# "Anmerkung" / "Anmerkung I" / "Anmerkung 2", plus MAN's long-form
# "Allgemeine Anmerkung zur Dynamik/Mechanik/Phänomenologie" heads.
_REMARK_HEAD_RE = re.compile(
    r"^Anmerkung(\s+(?:[IVX]+|\d+))?\s*\.?$|^Allgemeine Anmerkung\b[^.]{0,60}\.?$"
)

# Structural heads that close a remark. Kant's section-internal heads
# are short standalone lines built from a small vocabulary — plus
# enumerated sub-heads ("II. Vom Geize", "A. Der Hochmut") in the
# Tugendlehre. The length cap keeps ordinary short sentences from
# matching.
_STRUCT_HEAD_RE = re.compile(
    r"^[§\s0-9IVX.]*"
    r"(Lehrsatz|Erklärung|Beweis|Folgerung|Zusatz|Aufgabe|Grundgesetz|Grundsatz|"
    r"Postulat|Definition|Scholie|Scholium|Corollarium|Kasuistische Fragen)\b"
    r"|^(?:[IVX]+|[A-Z]|\d+)\.\s+\S"
)
_STRUCT_HEAD_MAX_CHARS = 40


def _type_kant_remarks(chunks: Iterable[Chunk]) -> Iterator[Chunk]:
    """Post-pass over one zeno page's chunks: type Anmerkung blocks."""

    in_remark = False
    for chunk in chunks:
        text = chunk.text.strip()
        if _REMARK_HEAD_RE.match(text):
            in_remark = True
        elif in_remark and len(text) <= _STRUCT_HEAD_MAX_CHARS and _STRUCT_HEAD_RE.match(text):
            in_remark = False
        if in_remark:
            yield dataclasses.replace(chunk, block_type="remark")
        else:
            yield chunk


def split_zeno_pages(html: str, work: CorpusWork, path: Path) -> Iterator[Chunk]:
    """Split a zeno.org-format HTML dump into chunks keyed on `<!-- ZENO_PAGE
    -->` markers. Each page becomes one (heading, body) pair; bodies are
    further split into paragraphs by `_split_chapter_block`."""

    try:
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]
    except ImportError as exc:
        raise IngestDepsMissing(
            "HTML ingest requires `beautifulsoup4`. Install with `pip install -e '.[hegel]'`."
        ) from exc

    markers = list(_ZENO_MARKER.finditer(html))
    if not markers:
        return
    # First marker is the work-root landing page; everything else is a
    # subpage extending its path.
    root_path = markers[0].group(1)

    for i, m in enumerate(markers):
        page_path = m.group(1)
        start = m.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(html)
        page_html = html[start:end]

        soup = BeautifulSoup(page_html, "html.parser")
        # Drop site chrome before extracting body text.
        for sel in (
            "script",
            "style",
            ".zenoSF",
            ".zenoCOHeader",
            ".zenoCOHeadline",
            ".zenoCOHeadlineSub",
            ".zenoCOHeadlineLibName",
            ".zenoCOBackForth",
            ".zenoCOFooterLine",
            ".zenoCOFooterLineLeft",
            ".zenoCOFooterLineRight",
            ".adsbygoogle",
            ".zenoLSInnerProductTableRightAmazon",
            ".zenoLSInnerProductTableRightLesesaal",
            ".zenoLRBox",
            "#socialBookmarks",
            "#socialshareprivacy",
        ):
            for tag in soup.select(sel):
                tag.decompose()
        body = soup.select_one("#zenoCOText") or soup
        # Iterate paragraph-level elements explicitly so each `<p>` becomes
        # its own chunk downstream; `get_text("\n")` collapses adjacent
        # paragraphs to a single newline, which the chapter splitter
        # interprets as one giant paragraph.
        paragraph_elems = body.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"])
        if paragraph_elems:
            page_text = "\n\n".join(
                p.get_text(" ", strip=True) for p in paragraph_elems if p.get_text(strip=True)
            )
        else:
            page_text = body.get_text("\n", strip=True)
        if not page_text.strip():
            continue
        heading = _derive_zeno_heading(page_path, root_path)
        # Defensive: if a future HTML source carries an editorial /
        # front-matter section (current zeno.org dumps don't), drop it
        # rather than attributing it to the work's author.
        if _is_editorial_heading(heading):
            continue
        page_chunks = _split_chapter_block(work, path, heading, page_text)
        if work.author == "Kant":
            # Remark-mode state is per page — a new ZENO_PAGE always
            # starts back in the main voice.
            yield from _type_kant_remarks(page_chunks)
        elif work.code == "briefe":
            # Letter closings ending "... Friedrich Nietzsche" are his own
            # words but paratextual, not discursive (#291) — gated on the
            # work rather than the phrase alone, since this splitter is
            # shared across authors.
            yield from _type_signature_lines(page_chunks)
        else:
            yield from page_chunks
