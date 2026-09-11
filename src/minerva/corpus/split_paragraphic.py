"""The three paragraph-shape splitters: `section`, `paragraph`,
`chapter`.

These handle the generic English / German prose layouts that Hegel
and Kant translations come in (modulo the more specialized
`split_kant.kant_ab` for KrV and the `split_zeno.zeno_pages` for
zeno.org HTML dumps).
"""

from __future__ import annotations

import dataclasses
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
from . import page_furniture
from .text_repair import (
    _looks_like_bibliography,
    _repair_crossref_linebreaks,
    strip_source_chrome,
)

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


# A Nachlass title-page draft or Briefe valediction ending in the author's
# own name — "Der Spiegel. Versuch einer Selbstabschätzung. Von Friedrich
# Nietzsche." / "Mit den herzlichsten Wünschen allezeit der Ihrige Friedrich
# Nietzsche". Real text (he wrote it), but paratextual rather than
# discursive, and it outranks his actual philosophy on any query containing
# his name unless typed (#291). Anchored to end-of-string so a chunk that
# merely MENTIONS the name mid-text (a real excerpt from Ecce homo, say) is
# untouched.
_SIGNATURE_LINE_RE = re.compile(r"(?:von\s+)?friedrich nietzsche\.?\s*$", re.I)


def _is_signature_line(text: str) -> bool:
    return bool(_SIGNATURE_LINE_RE.search(text.strip()))


def _type_signature_lines(chunks: Iterator[Chunk]) -> Iterator[Chunk]:
    """Post-pass: type paragraphs matching `_is_signature_line` as
    block_type='signature'. Typing-only — `dataclasses.replace` runs after
    `chunk_id` is already computed from the text, so ids don't move and
    embeddings/lemmas/xrefs survive a re-ingest byte-identical, same as
    `split_zeno._type_kant_remarks`."""

    for chunk in chunks:
        if _is_signature_line(chunk.text):
            yield dataclasses.replace(chunk, block_type="signature")
        else:
            yield chunk


def _emit(
    work: CorpusWork,
    path: Path,
    section: str,
    text: str,
    book_label: str | None = None,
    block_type: str | None = None,
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
    # Scraped page furniture (#383, #298). Same position as the filters
    # above and for the same reason: the caller has already assigned this
    # paragraph's ¶ index, so dropping it here costs no chunk_id but its own.
    text = strip_source_chrome(text)
    if not text:
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
        # The heading sweep's per-chunk type (e.g. "editorial") wins over
        # the work-level default ("note" for a whole endnotes work); when
        # the caller passes nothing, the work-level default still applies.
        block_type=block_type or work.block_type,
    )


def _in_section_range(work: CorpusWork, n: int) -> bool:
    if work.max_section is not None and n > work.max_section:
        return False
    return not (work.min_section is not None and n < work.min_section)


# Standalone heading lines that begin a volume's back matter. Only the
# final section's body is scanned for these (see `split_by_section`), so
# the pattern does not have to survive the whole book — it has to be
# right once, at the point where the work stops and the apparatus starts.
#
# Measured against both `.pdf` Hegel volumes: the *Encyclopaedia* cuts at
# `Bibliography` and the *Philosophy of Mind* at `Index to Translation and
# Commentary`. Both recur later as running page headers, which is why the
# first match is the one taken (#385).
_BACK_MATTER_RE = re.compile(
    r"(?m)^[ \t]*(?:"
    r"(?:Select(?:ed)?\s+)?Bibliography"
    r"|Index(?:\s+to\s+[A-Za-z][^\n]{0,60})?"
    r"|Works\s+Cited"
    r")[ \t]*$"
)

# PyMuPDF returns the ligature glyphs the typesetter used, so a heading
# configured as "Preface to the first edition" never matches the extracted
# "Preface to the ﬁrst edition". Substituting an alternation (rather than
# expanding the ligature in the text) keeps every offset in the prefix
# where it was, which the front-matter capture indexes into.
_LIGATURES = (("ffi", "ﬃ"), ("ffl", "ﬄ"), ("ff", "ﬀ"), ("fi", "ﬁ"), ("fl", "ﬂ"))


def _ligature_tolerant(heading: str) -> str:
    """`re.escape` a heading, then let each `fi`/`fl`/… also match its
    single-glyph ligature."""

    pattern = re.escape(heading)
    for ascii_form, ligature in _LIGATURES:
        pattern = pattern.replace(ascii_form, f"(?:{ascii_form}|{ligature})")
    return pattern


def _body_start_index(work: CorpusWork, matches: list[re.Match[str]]) -> int:
    """Index of the first match that is the work's own opening section.

    Editorial front matter cites the body it introduces, and those
    citations sit at line starts after PDF extraction, so `_SECTION_RE`
    reads them as section heads: the *Encyclopaedia* opens `§24, §82, §1,
    §2, …`, giving 85,286 characters of editors' introduction, translators'
    note and Hegel's three prefaces a locator taken from a footnote.

    The work's own numbering ascends from `min_section` (or 1), so
    everything before the first match of that number is prefix. Returns 0
    when that number never appears — an extraction that lost `§1` must
    lose one marker, not the whole work.
    """

    start_n = work.min_section if work.min_section is not None else 1
    for i, m in enumerate(matches):
        if int(m.group(1)) == start_n:
            return i
    return 0


def split_by_section(text: str, work: CorpusWork, path: Path) -> Iterator[Chunk]:
    """Split a text on §N markers. Front matter before the first marker is
    dropped (or routed through `work.front_matter_headings`, see below).
    Matches whose body is shorter than `_SECTION_MIN_BODY` are skipped as
    cross-reference artifacts — EPUB/PDF extraction wraps inline
    cross-refs like ``(see § 6 above)`` onto multiple lines, making
    `§ 6` look like a section head with body "above)"."""

    text = _repair_crossref_linebreaks(text)
    matches = list(_SECTION_RE.finditer(text))
    # Markers the editors' apparatus cites, not sections of the work. See
    # `_body_start_index`; dropping them here rather than in the loop below
    # is what widens the front-matter prefix to include them, so the
    # prefaces buried among them can be captured instead of relabelled.
    matches = matches[_body_start_index(work, matches) :]

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
            # The LAST occurrence, not the first: a volume that prints a
            # table of contents lists every preface heading there before
            # the preface itself appears, and the first match captures the
            # contents listing — a body of one line, with Hegel's actual
            # preface left in whatever region follows it.
            found = list(re.finditer(rf"(?m)^\s*{_ligature_tolerant(h)}\s*$", prefix))
            if found:
                positions.append((found[-1].start(), found[-1].end(), h))
        positions.sort()
        for i, (_, head_end, label) in enumerate(positions):
            body_end = positions[i + 1][0] if i + 1 < len(positions) else prefix_end
            body = prefix[head_end:body_end]
            if body.strip():
                yield from _split_chapter_block(work, path, label, body)

    for i, m in enumerate(matches):
        is_last = i + 1 == len(matches)
        end = matches[i + 1].start() if not is_last else len(text)
        n_str = m.group(1)
        if not _in_section_range(work, int(n_str)):
            continue
        body = text[m.end() : end]
        if is_last:
            # Only the final section runs to end-of-file, so the volume's
            # bibliography, editor's notes and index accrete onto it and
            # inherit its citation label. Cut at the heading that starts
            # them: a size threshold cannot do this job, because the
            # *Philosophy of Mind* ends §577 with Hegel's own quotation of
            # *Metaphysics* XII.7 and its two largest body sections (§406,
            # §408) are 119,857 characters of genuine text (#385).
            cut = _BACK_MATTER_RE.search(body)
            if cut is not None:
                body = body[: cut.start()]
        if len(body.strip()) < _SECTION_MIN_BODY:
            continue
        chunk = _emit(work, path, section=f"§{n_str}", text=body)
        if chunk is not None:
            yield chunk


# `[Fable N]` / `[Fable N: TITLE]`, written by
# `perseus/download_babrius.py` at each Perry-index reference in the
# Davies scan. The title is optional: 11 of the 131 fables have an
# all-caps title the OCR mangled past recovery.
_FABLE_RE = re.compile(r"(?m)^\s*\[Fable\s+(\d+)(?::\s*([^\]]*))?\]\s*$")


def split_by_fable(text: str, work: CorpusWork, path: Path) -> Iterator[Chunk]:
    """One chunk per fable, for the verse collections whose extractor
    marks fable boundaries explicitly.

    The generic paragraph splitter cannot be used here: the Davies scan
    carries OCR-inserted blank lines through the verse — 2,307 breaks in
    6,171 lines — so `\\n\\s*\\n` finds a "paragraph" every line or two and
    the work came out as 2,139 chunks at a 44-character median (#399).
    The fable is the citable unit, and it is already delimited.

    The title is prepended to the body rather than put in `book`: it is
    Davies's text, not a container, and one distinct `book` per fable
    would be 131 of them.
    """

    matches = list(_FABLE_RE.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title = (m.group(2) or "").strip()
        body = text[m.end() : end]
        # Everything before the first marker is the extractor's own
        # provenance header, not Babrius.
        chunk = _emit(
            work,
            path,
            section=f"Fable {m.group(1)}",
            text=f"{title}\n{body}" if title else body,
        )
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
    #     keep the body but tag it `block_type='editorial'`, so retrieval
    #     can cap it and the Reader can collapse it. This replaced an
    #     outright drop in #534. The heading position is still used as a
    #     boundary so the next chapter starts at the right offset.
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
    for i, (_h_start, h_end, label, editorial) in enumerate(headings):
        start = h_end
        end = headings[i + 1][0] if i + 1 < len(headings) else len(text)
        body = text[start:end]
        # Apparatus is TAGGED, not dropped (#534). Dropping it lost real
        # scholarship silently and left no way to tell a missing editorial
        # introduction from one that was never in the source.
        yield from _split_chapter_block(
            work, path, label, body, block_type="editorial" if editorial else None
        )


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


def _packed_paragraphs(paragraphs: list[str], floor: int | None) -> list[str]:
    """Join consecutive paragraphs until each run reaches `floor` chars.

    Called per heading, so a run never spans two of them — the tail of one
    dithyramb cannot merge into the head of the next. The final run is
    emitted short rather than folded backwards: it is the end of the
    poem, and folding would make the last chunk the largest.
    """

    if floor is None:
        return paragraphs
    out: list[str] = []
    run: list[str] = []
    size = 0
    for para in paragraphs:
        run.append(para)
        size += len(para) + 1
        if size >= floor:
            out.append("\n\n".join(run))
            run, size = [], 0
    if run:
        out.append("\n\n".join(run))
    return out


def _split_chapter_block(
    work: CorpusWork,
    path: Path,
    heading: str,
    body: str,
    block_type: str | None = None,
) -> Iterator[Chunk]:
    """Inside a chapter, emit one chunk per blank-line-separated paragraph
    — or per packed run of them, when the work sets a floor (#417)."""

    paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    paragraphs = _packed_paragraphs(paragraphs, work.min_paragraph_chars)
    for idx, para in enumerate(paragraphs, 1):
        for label, piece in _paragraph_pieces(work, idx, para):
            section = f"{heading}, {label}" if heading else label
            if work.page_furniture:
                piece = page_furniture.strip_running_head(
                    piece, page_furniture.RUNNING_HEADS_LWH
                )
                piece, note_text = page_furniture.split_trailing_notes(piece)
                piece = page_furniture.strip_trailing_page_number(piece)
                # The page number sits AFTER the note block on the printed
                # page, so it lands in `note_text`, not in the body. Measured:
                # 235 of 279 split note blocks (84%) end in one. Strip both
                # sides or every note chunk ships with a stray number.
                if note_text:
                    note_text = page_furniture.strip_trailing_page_number(note_text)
            else:
                note_text = None
            chunk = _emit(
                work,
                path,
                section=section,
                text=piece,
                book_label=heading or None,
                block_type=block_type,
            )
            if chunk is not None:
                yield chunk
            if note_text:
                note = _emit(
                    work,
                    path,
                    section=f"{section}.note",
                    text=note_text,
                    book_label=heading or None,
                    block_type="note",
                )
                if note is not None:
                    yield note


#: A speech turn ends `…"--` and the next begins `"`. Zero-width, so the
#: `--` stays with the turn that ends and nothing is consumed but the
#: whitespace `_norm_text` would collapse anyway.
_TURN_RE = re.compile(r'(?<="--)\s*(?=")')
#: Fallback for a run with no turns in it — sentence end followed by a
#: capital, an opening quote, or the `_italic_` markup Gutenberg uses.
_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"_])')


def _paragraph_pieces(work: CorpusWork, idx: int, para: str) -> list[tuple[str, str]]:
    """`(locator, text)` for one blank-line paragraph.

    Under the work's cap — or with no cap at all — that is the paragraph
    itself under `¶N`, byte for byte, so its `chunk_id` does not move.
    Over the cap it is several pieces under `¶N.1`, `¶N.2`, … The
    sub-numbering matters: numbering the pieces `¶N`, `¶N+1` instead would
    renumber every paragraph after them, and `section` is an input to
    `_make_chunk_id` — 17 dropped paragraphs once churned 745 chunks that
    way. Every piece gets a sub-locator, including the first, so no piece
    inherits the whole paragraph's id and with it an embedding computed
    over text four times longer.
    """

    cap = work.max_paragraph_chars
    if cap is None or len(para) <= cap:
        return [(f"¶{idx}", para)]
    return [(f"¶{idx}.{k}", piece) for k, piece in enumerate(_packed(para, cap), 1)]


def _packed(para: str, cap: int) -> list[str]:
    """Greedily pack the paragraph's segments into runs under `cap`.

    A segment that is itself over the cap is emitted alone rather than
    cut mid-sentence — the cap is a target, and a sentence longer than it
    is still one sentence.
    """

    out: list[str] = []
    current = ""
    for seg in _segments(para, cap):
        if current and len(current) + len(seg) + 1 > cap:
            out.append(current)
            current = seg
        else:
            current = f"{current} {seg}".strip() if current else seg
    if current:
        out.append(current)
    return out


def _segments(para: str, cap: int) -> list[str]:
    """The units an oversized paragraph may be split between.

    Speech turns when the paragraph has them — Brutus is a dialogue, and
    the turn is the unit a reader would cite. A turn that is *itself* over
    the cap splits again at its sentence ends: Cicero's longest
    uninterrupted answer in the Brutus is 9,070 characters, so turns alone
    leave one piece over the ceiling.
    """

    turns = [t for t in _TURN_RE.split(para) if t.strip()]
    if len(turns) == 1:
        return [s for s in _SENTENCE_RE.split(para) if s.strip()]
    out: list[str] = []
    for turn in turns:
        if len(turn) > cap:
            out.extend(s for s in _SENTENCE_RE.split(turn) if s.strip())
        else:
            out.append(turn)
    return out
