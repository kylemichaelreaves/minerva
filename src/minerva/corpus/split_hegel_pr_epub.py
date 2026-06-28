"""Structure-aware parser for Hegel's *Elements of the Philosophy of Right*
(Cambridge / Wood-Nisbet EPUB).

The generic ``locator="section"`` splitter flattens the EPUB to plain text
and emits one merged chunk per § — main paragraph, Remark (*Anmerkung*),
and Addition (*Zusatz*) all fused, and inline "see § N" cross-references
mis-read as new section heads. This parser instead walks the EPUB markup
and emits **separate, typed** chunks per §, carrying ``block_type`` so the
reader can set Remarks/Additions apart. See
``docs/block-structure-remediation-plan.md`` (Phase 1.1).

Markup contract (Cambridge EPUB):

* ``<h4>§ N</h4>``                — section heading.
* ``<p class="noindent…">``      — main section prose.
* ``<p class="blockquote…">``    — Remark (Hegel's *Anmerkung*).
* ``<p>Addition (H/G). …</p>``   — Addition (*Zusatz*), text-prefixed.
* ``<p class="footnote">``       — editor footnote: skipped here (the
                                   endnotes already ship as the separate
                                   ``pr_notes`` work; notes typing is a
                                   later phase).

Per § we track a *mode* (main → remark → addition) that flips on the
trigger paragraphs above and otherwise carries forward, so multi-paragraph
Remarks/Additions classify correctly rather than only their first line.
Consecutive same-mode paragraphs are merged into one chunk (paragraph
breaks preserved), so each § yields at most one main + one remark + one
addition chunk.

Front matter named in ``work.front_matter_headings`` (Hegel's own Preface,
home of the Owl-of-Minerva passage) is captured as ``book="<heading>"``
chunks so it isn't dropped — matching the generic §-splitter's behavior.

File ordering relies on the Cambridge EPUB's zero-padded ``part00NN``
filenames sorting into reading order; this parser is wired only to that
work (``locator="pr_structured"``).
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator
from pathlib import Path

from ..corpus_works import CorpusWork
from ..tei import Chunk, _make_chunk_id, _norm_text

# NB: `bs4` is imported lazily inside split_hegel_pr_epub (see there). It's an
# `[hegel]`-extra dependency; a module-top import would make `minerva serve`
# (which imports the whole corpus pipeline) crash anywhere the extra isn't
# installed, e.g. the CI base venv.

_SECTION_RE = re.compile(r"§\s*(\d{1,3})")
_CONTENT_FILE_RE = re.compile(r"\.x?html?$", re.I)

# Headings that mark the start of back matter. Everything from here on
# (editor's endnotes, glossary, bibliography, indexes) is apparatus, not
# Hegel's text — and the endnotes re-reference §§, which would otherwise
# pollute the body chunks. The editor's endnotes already ship separately
# as the ``pr_notes`` work.
_STOP_HEADINGS = frozenset(
    {
        "editorial notes",
        "glossary",
        "selected bibliography",
        "bibliography",
        "index of subjects",
        "index of names",
    }
)

# block_type stored per mode. "main" → None (≡ body in the schema).
_BLOCK_TYPE = {"main": None, "remark": "remark", "addition": "addition"}
# Human-readable section-locator suffix per mode.
_SECTION_SUFFIX = {"main": "", "remark": " Remark", "addition": " Addition"}


def _classify(mode: str, text: str, css: str) -> str:
    """Return the block mode for a paragraph given the current mode.

    Mode flips on a trigger paragraph and otherwise carries forward, so a
    multi-paragraph Remark/Addition keeps its type past the first line."""
    if text.startswith("Addition"):
        return "addition"
    if "blockquote" in css:
        return "remark"
    if "noindent" in css:
        return "main"
    # Unclassed continuation (list items, etc.) inherit the current mode.
    return mode


def _make_chunk(
    work: CorpusWork,
    path: Path,
    *,
    section: str,
    book: str | None,
    block_type: str | None,
    paragraphs: list[str],
) -> Chunk | None:
    text = "\n\n".join(p for p in (_norm_text(t) for t in paragraphs) if p)
    if not text:
        return None
    chunk_id = _make_chunk_id(
        path.name, work.title, work.lang, book or "", section, "", text[:120]
    )
    return Chunk(
        chunk_id=chunk_id,
        corpus=work.corpus,
        author=work.author,
        work=work.title,
        lang=work.lang,
        section=section,
        book=book,
        page=None,
        speaker=None,
        text=text,
        source_file=path.name,
        translator=work.translator,
        edition_year=work.edition_year,
        citation_system=work.citation_system,
        block_type=block_type,
    )


def _flush_section(
    work: CorpusWork,
    path: Path,
    n: int,
    blocks: list[tuple[str, str]],
) -> Iterator[Chunk]:
    """Emit chunks for one § by merging consecutive same-mode paragraphs.

    ``blocks`` is ``[(mode, paragraph_text), …]`` in document order."""
    if not blocks:
        return
    seen_suffix: dict[str, int] = {}
    i = 0
    while i < len(blocks):
        mode = blocks[i][0]
        run = []
        while i < len(blocks) and blocks[i][0] == mode:
            run.append(blocks[i][1])
            i += 1
        suffix = _SECTION_SUFFIX[mode]
        # Disambiguate the rare case of two same-mode runs in one § (e.g.
        # main … remark … main) so section locators stay unique.
        key = f"§{n}{suffix}"
        seen_suffix[key] = seen_suffix.get(key, 0) + 1
        section = key if seen_suffix[key] == 1 else f"{key} ({seen_suffix[key]})"
        chunk = _make_chunk(
            work, path, section=section, book=None,
            block_type=_BLOCK_TYPE[mode], paragraphs=run,
        )
        if chunk is not None:
            yield chunk


def split_hegel_pr_epub(path: Path, work: CorpusWork) -> Iterator[Chunk]:
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]
    except ImportError as exc:
        from ..corpus_extract import IngestDepsMissing

        raise IngestDepsMissing(
            "EPUB ingest requires `beautifulsoup4`. Install with `pip install -e '.[hegel]'`."
        ) from exc

    front_headings = {h.lower() for h in work.front_matter_headings}
    cur_section: int | None = None
    cur_front: str | None = None
    front_idx = 0
    blocks: list[tuple[str, str]] = []  # (mode, text) for the current §
    mode = "main"

    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if _CONTENT_FILE_RE.search(n))
        for name in names:
            soup = BeautifulSoup(z.read(name), "html.parser")
            for el in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p"]):
                txt = el.get_text(" ", strip=True)
                if el.name != "p":
                    # Heading: back-matter boundary stops the parse; a §
                    # head (strictly increasing — backward "§ N" refs are
                    # spurious cross-references) opens a new section; a
                    # named front-matter head opens front-matter capture;
                    # any other pre-§ head ends front-matter capture.
                    low = txt.lower()
                    if low in _STOP_HEADINGS:
                        if cur_section is not None:
                            yield from _flush_section(work, path, cur_section, blocks)
                        return
                    m = _SECTION_RE.search(txt)
                    if m and txt.strip().startswith("§"):
                        n = int(m.group(1))
                        if cur_section is None or n > cur_section:
                            if cur_section is not None:
                                yield from _flush_section(work, path, cur_section, blocks)
                            cur_section = n
                            cur_front = None
                            blocks = []
                            mode = "main"
                        # else: spurious backward §-reference — ignore.
                    elif cur_section is None and low in front_headings:
                        cur_front = txt
                        front_idx = 0
                    elif cur_section is None:
                        cur_front = None
                    continue
                # Paragraph.
                if not txt:
                    continue
                css = " ".join(el.get("class", []))
                if "footnote" in css:
                    continue  # deferred — see module docstring
                if cur_section is not None:
                    mode = _classify(mode, txt, css)
                    blocks.append((mode, txt))
                elif cur_front is not None:
                    front_idx += 1
                    chunk = _make_chunk(
                        work, path,
                        section=f"{cur_front}, ¶{front_idx}",
                        book=cur_front, block_type=None, paragraphs=[txt],
                    )
                    if chunk is not None:
                        yield chunk
    if cur_section is not None:
        yield from _flush_section(work, path, cur_section, blocks)
