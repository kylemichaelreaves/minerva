"""The three paragraph-shape splitters: `section`, `paragraph`,
`chapter`.

These handle the generic English / German prose layouts that Hegel
and Kant translations come in (modulo the more specialized
`split_kant.kant_ab` for KrV and the `split_zeno.zeno_pages` for
zeno.org HTML dumps).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path

from ..corpus_works import CorpusWork
from ..heading_clean import (
    _clean_heading_label,
    _is_editorial_heading,
    _is_skipped_for_work,
    _is_title_page_artifact,
)
from ..tei import Chunk, _make_chunk_id, _norm_text
from .text_repair import _looks_like_bibliography, _repair_crossref_linebreaks

# Anchored to start-of-line so inline cross-references like "see §44"
# inside a section's body don't get parsed as fresh section heads.
_SECTION_RE = re.compile(r"(?m)^\s*§\s*(\d+)\b")
# Minimum body length (chars) for a §-match to be kept. Cross-references
# that get broken across lines by EPUB/PDF extraction — `(see\n§ 6\nabove)`
# — produce matches with very short bodies (often a single word or
# closing punctuation), while real Hegel sections start at 136+ chars
# across the works in the corpus. 50 is conservative.
_SECTION_MIN_BODY = 50

# Pinkard's per-paragraph numbering becomes lines like "  17. Some text..."
# after PyMuPDF extraction. The regex demands a line break before the
# number so we don't mistake an in-line ordinal for a paragraph head.
_PARAGRAPH_RE = re.compile(r"(?m)^\s*(\d+)\.\s")

# Heading-ish lines, in any of three shapes:
#   1. "CHAPTER ...", "PART ...", "BOOK ...", "SECTION ...", "LECTURE ..."
#   2. ALL-CAPS short lines (subsection heads in OUP and Cambridge editions)
#   3. Roman-numeral + period + Title-Case line (Inwood-style major chapters
#      like "I. Sensory Certainty: The This and Meaning")
_HEADING_RE = re.compile(
    r"(?m)^\s*("
    r"(?:CHAPTER|PART|BOOK|SECTION|LECTURE)\s+[IVXLC0-9]+[^\n]{0,80}"
    r"|[A-Z][A-Z \-—:,'.]{6,80}"
    r"|[IVX]+\.\s+[A-Z][^\n]{2,80}"
    r")\s*$"
)


def _has_letter(text: str) -> bool:
    """At least one Unicode letter anywhere in the text."""

    return any(unicodedata.category(ch).startswith("L") for ch in text)


def _emit(
    work: CorpusWork,
    path: Path,
    section: str,
    text: str,
    book_label: str | None = None,
) -> Chunk | None:
    text = _norm_text(text)
    if not text:
        return None
    if not _has_letter(text):
        # Letter-free paragraphs are never prose: standalone aphorism-
        # number lines from the zeno.org dumps ("1", "2."), bare section
        # markers ("§ 9"), typographic separators ("----"), and OCR
        # glyph soup ("■", "•") from the Gallica scans. The caller
        # assigns ¶ indices BEFORE this filter runs, so dropping a
        # paragraph here never renumbers — and never re-ids — the
        # surviving chunks around it.
        return None
    if _looks_like_bibliography(text):
        return None
    chunk_id = _make_chunk_id(
        path.name,
        work.title,
        work.lang,
        book_label or "",
        section,
        "",
        text[:120],
    )
    return Chunk(
        chunk_id=chunk_id,
        corpus=work.corpus,
        author=work.author,
        work=work.title,
        lang=work.lang,
        section=section,
        book=book_label,
        page=None,
        speaker=None,
        text=text,
        source_file=path.name,
        translator=work.translator,
        edition_year=work.edition_year,
        citation_system=work.citation_system,
        block_type=work.block_type,
    )


def _in_section_range(work: CorpusWork, n: int) -> bool:
    if work.max_section is not None and n > work.max_section:
        return False
    return not (work.min_section is not None and n < work.min_section)


def split_by_section(text: str, work: CorpusWork, path: Path) -> Iterator[Chunk]:
    """Split a text on §N markers. Front matter before the first marker is
    dropped (or routed through `work.front_matter_headings`, see below).
    Matches whose body is shorter than `_SECTION_MIN_BODY` are skipped as
    cross-reference artifacts — EPUB/PDF extraction wraps inline
    cross-refs like ``(see § 6 above)`` onto multiple lines, making
    `§ 6` look like a section head with body "above)"."""

    text = _repair_crossref_linebreaks(text)
    matches = list(_SECTION_RE.finditer(text))

    # Front-matter capture (e.g. Hegel's own Preface in §-numbered
    # editions). The default §-splitter drops everything before §1,
    # which loses canonical Hegel text like the Owl-of-Minerva passage
    # in PR's Vorrede. When the work names front-matter headings,
    # locate each as a standalone line in the prefix and emit one chunk
    # per blank-line-separated paragraph beneath it, labelled
    # `book="<heading>"`, `section="<heading>, ¶N"`. Headings are
    # processed in document order; each runs up to the next listed
    # heading or to the first §-marker. Editorial content above the
    # first named heading (publisher series matter, copyright page) is
    # implicitly skipped.
    if matches and work.front_matter_headings:
        prefix_end = matches[0].start()
        prefix = text[:prefix_end]
        positions: list[tuple[int, int, str]] = []
        for h in work.front_matter_headings:
            m_h = re.search(rf"(?m)^\s*{re.escape(h)}\s*$", prefix)
            if m_h is not None:
                positions.append((m_h.start(), m_h.end(), h))
        positions.sort()
        for i, (_, head_end, label) in enumerate(positions):
            body_end = positions[i + 1][0] if i + 1 < len(positions) else prefix_end
            body = prefix[head_end:body_end]
            if body.strip():
                yield from _split_chapter_block(work, path, label, body)

    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        n_str = m.group(1)
        if not _in_section_range(work, int(n_str)):
            continue
        body = text[m.end() : end]
        if len(body.strip()) < _SECTION_MIN_BODY:
            continue
        chunk = _emit(work, path, section=f"§{n_str}", text=body)
        if chunk is not None:
            yield chunk


def split_by_paragraph(text: str, work: CorpusWork, path: Path) -> Iterator[Chunk]:
    """Split on `\\nN. ` paragraph numbering. Drops front matter before ¶1."""

    matches = list(_PARAGRAPH_RE.finditer(text))
    if not matches:
        return
    seen: set[str] = set()
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        n_str = m.group(1)
        # Reject ordinals outside the work's known range and dedupe
        # repeats that come from mis-extraction.
        if not _in_section_range(work, int(n_str)):
            continue
        if n_str in seen:
            continue
        seen.add(n_str)
        body = text[m.end() : end]
        chunk = _emit(work, path, section=f"¶{n_str}", text=body)
        if chunk is not None:
            yield chunk


def split_by_chapter(text: str, work: CorpusWork, path: Path) -> Iterator[Chunk]:
    """Heading-based splitter: emit one chunk per paragraph within a heading.

    Imperfect by nature — depends on the translator's heading conventions.
    Adjust `_HEADING_RE` if a particular work's chapter heads slip through.
    """

    raw_headings = _merge_continuation_headings(text, list(_HEADING_RE.finditer(text)))
    # Two-stage heading sweep:
    #   * Editorial / front-matter labels ("Editorial Introduction",
    #     "Glossary", "Bibliography", "List of Abbreviations", indices) —
    #     drop BOTH the label AND the body so this material doesn't get
    #     attributed to Hegel downstream. The heading position is still
    #     used as a boundary so the next chapter starts at the right
    #     offset.
    #   * Title-page artifacts ("Robert F. Brown", "Volume II Greek
    #     Philosophy", single title words like "Lectures") — blank the
    #     label so it doesn't pollute the locator, but keep the body.
    headings: list[tuple[int, int, str, bool]] = []
    for s, e, label in raw_headings:
        if label and (
            _is_editorial_heading(label) or _is_skipped_for_work(label, work.skip_headings)
        ):
            headings.append((s, e, label, True))
            continue
        cleaned = "" if label and _is_title_page_artifact(label, work) else label
        headings.append((s, e, cleaned, False))
    if not headings:
        # Whole-document fallback: emit one chunk per paragraph.
        yield from _split_chapter_block(work, path, "", text)
        return
    # Pre-first-heading region: in some translations this is *most* of the
    # book (chapters whose heads don't match _HEADING_RE end up here), so
    # we emit it as unlabeled chunks rather than dropping it.
    first_heading_start = headings[0][0]
    if first_heading_start > 0:
        front = text[:first_heading_start]
        if front.strip():
            yield from _split_chapter_block(work, path, "", front)
    for i, (_h_start, h_end, label, skip) in enumerate(headings):
        if skip:
            continue
        start = h_end
        end = headings[i + 1][0] if i + 1 < len(headings) else len(text)
        body = text[start:end]
        yield from _split_chapter_block(work, path, label, body)


def _merge_continuation_headings(
    text: str, matches: list[re.Match[str]]
) -> list[tuple[int, int, str]]:
    """Merge consecutive heading matches separated only by whitespace.

    PDF extraction wraps long ALL-CAPS chapter heads onto multiple lines,
    so a single heading like "INDEPENDENCE AND DEPENDENCE OF
    SELF-CONSCIOUSNESS: LORDSHIP AND BONDAGE" arrives as two separate
    `_HEADING_RE` matches. Merge them so the chunker sees one heading.

    Two guards on the merge:
    * Skip when the next-match label equals the current one (zeno.org's
      pages sometimes print the chapter title twice — once as a breadcrumb,
      once as the heading — and we'd otherwise produce
      "Foo Foo" labels).
    * Cap at 4 continuation lines; runaway merges are diagnostic of
      something else having gone wrong with the extraction.
    """

    out: list[tuple[int, int, str]] = []
    i = 0
    while i < len(matches):
        cur = matches[i]
        start = cur.start()
        end = cur.end()
        label = cur.group(1).strip()
        j = i + 1
        seen_in_label = {label}
        while j < len(matches) and (j - i) <= 4:
            gap = text[end : matches[j].start()]
            if gap.strip():
                break
            next_label = matches[j].group(1).strip()
            # Drop the redundant duplicate but advance past it so we don't
            # restart the BFS at the same position next iteration.
            if next_label in seen_in_label:
                end = matches[j].end()
                j += 1
                continue
            label = f"{label} {next_label}"
            seen_in_label.add(next_label)
            end = matches[j].end()
            j += 1
        out.append((start, end, _clean_heading_label(label)))
        i = j
    return out


def _split_chapter_block(work: CorpusWork, path: Path, heading: str, body: str) -> Iterator[Chunk]:
    """Inside a chapter, emit one chunk per blank-line-separated paragraph."""

    paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    for idx, para in enumerate(paragraphs, 1):
        section = f"{heading}, ¶{idx}" if heading else f"¶{idx}"
        chunk = _emit(work, path, section=section, text=para, book_label=heading or None)
        if chunk is not None:
            yield chunk
