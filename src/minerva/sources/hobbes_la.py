"""Parser for Hobbes's Latin works in Molesworth's 1839 *Opera Latina*.

Two source files, both sliced out of Internet Archive OCR of William
Molesworth's *Thomae Hobbes Malmesburiensis Opera philosophica quae
latine scripsit omnia* (London: Bohn, 1839) by
``perseus/download_hobbes_la.py``:

  * ``leviathan_lat.txt`` — vol. III, Caput I–XLVII of *Leviathan, sive
    de materia, forma, & potestate civitatis ecclesiasticae et civilis*.
  * ``de_cive_lat.txt`` — vol. II, Caput I–XVIII of *Elementa
    philosophica de cive*.

**This replaced a parser for a completely different kind of page.**
Until 2026-09 the sources were IA scans of the 17th-century printings,
set in long-s type, and the parser here was a tolerance machine: it
accepted ``C A F V T`` for CAPVT, ``CAPVT XXX L`` for chapter XXXI, and
reconstructed chapters whose headings had not survived OCR at all from
clusters of page running-heads. It produced one chunk per chapter —
up to 127,001 characters — because the OCR was too corrupt to split
finer. See #535.

Molesworth's 19th-century roman type does not have those problems, so
none of that machinery is here. What it does have is a **two-column
page**: body text with a marginal gloss column beside it, which the OCR
linearizes into the body lines. Everything below is about that.

Page anatomy, from ``leviathan_lat.txt`` (line numbers are that file's)::

    1009  vel  stultior  est  quam  vulgus.     Neque  sine  literis
    1010  (blank)
    1011  (blank)
    1012  Deserraone.                     ← marginal gloss, orphaned
    1013  (blank)
    1014  (blank)
    1015  28  DE  HOMINE.                 ← page running head
    1016  (blank)
    1017  cap.  iv.  fieri  solent  homines  insigniter  sapientes,  neque,  nisi
                ↑ marginal chapter marker, inline

The paragraph beginning above 1009 continues at 1017. Three things have
to happen for it to survive the page break intact:

1. **Running heads and page numbers are dropped**, not treated as text.
   The four Parts of the Latin Leviathan give four running heads (DE
   HOMINE, DE CIVITATE, DE CIVITATE CHRISTIANA, DE REGNO TENEBRARUM),
   each with OCR variants — ``DB HOMINE``, ``DE HOMTNE``, ``PE
   HOMINE`` — so they are matched by shape (all-caps, optional flanking
   page number), not by an enumerated list.

2. **Marginal fragments are dropped.** Two forms: the inline ``cap.
   <roman>.`` chapter marker, which is regular enough to strip
   anywhere; and orphaned gloss lines like ``Deserraone.``, which are
   short, isolated, and — crucially — always sit within a few lines of
   a page break. Isolation alone is not enough to identify them: a
   genuine body line can be short and isolated too (``momento fere
   temporis.``, L517), and it is 24 lines from the nearest running
   head. Proximity to a page break is what separates the two.

3. **A blank line does not always end a paragraph.** It ends one only
   when the last body line before it closed a sentence. L1009 ends
   ``Neque sine literis`` — no terminal punctuation — so the blank is a
   page-break artefact and the paragraph continues. L1023 ends
   ``humani.``, so the blank after it is a real paragraph break.

Chunking is per paragraph, not per chapter: ``book = "Cap 15"`` and
``section = "Cap 15, ¶3"``, matching the English Hobbes files, which
already use ``book`` for the chapter and ``¶N`` for the paragraph
within it.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from minerva.sources._roman import roman_to_int
from minerva.tei import Chunk, _make_chunk_id, _norm_text

# ──────────────────────────────────────────────────────────────────
# Line shapes
# ──────────────────────────────────────────────────────────────────

# "CAPUT XIV." on its own line. Molesworth sets these consistently;
# the OCR damage is confined to the numeral (see `_roman_to_int`) and
# to a stray period after the word — De Cive's chapter XIV heads
# "CAPUT. XIV.", and without the optional period here that one chapter
# is silently absorbed into XIII.
_CAPUT_HEADING_RE = re.compile(
    r"^\s*CAPUT\s*[.,]?\s+([IVXLC]{1,7})\s*[.,;:]?\s*$",
    re.IGNORECASE,
)

# Page running head: an all-caps line, optionally with the page number
# on either side — "28  DE  HOMINE.", "DE  HOMINE.  121", "DE
# CIVITATE  CHRISTIANA.  267". Matched by shape because the OCR
# mangles the words themselves (DB / DE / PE, HOMINE / HOMINB /
# HOMTNE) but never the all-caps-with-page-number geometry.
_RUNNING_HEAD_RE = re.compile(
    r"^\s*(?:\d{1,3}\s+)?[A-Z][A-Z\s.'’]{3,44}?\s*[.,]?(?:\s+\d{1,3})?\s*$",
)

# Printer's signature mark at the foot of a gathering: "VOL. III. D",
# "c  2". Always short, always isolated, never text.
_SIGNATURE_RE = re.compile(
    r"^\s*(?:VOL\.?\s*[IVXL]+\.?\s*[A-Za-z]?\d?|[A-Za-z]\s*\d{1,2})\s*$",
    re.IGNORECASE,
)

# Bare page number on its own line.
_PAGE_NUM_RE = re.compile(r"^\s*\d{1,3}\s*[.,]?\s*$")

# The marginal chapter marker where the OCR runs it into a body line:
# "cap.  iv.", "cap.iv.", "Cap.  iv.", and the variants "gap." / "cav."
#
# **Anchored to the line ends on purpose.** The same string occurs
# mid-line as ordinary body text, because Hobbes cites chapters
# constantly — "ostensum est (cap. xiv.) pactum de seipso", "Paulus ad
# Hebr. cap. vi. versu ultimo", "Propheta Joel, (cap. ii. 30, 31)". An
# unanchored strip deletes those citations, and in De Cive it would hit
# 16 body citations against only 4 real margin markers. Anchoring costs
# nothing: the margin column linearizes to one end of the line or the
# other, never into the middle. Measured on `leviathan_lat.txt`: 161 at
# line start, 150 at line end, 11 mid-line — and all 11 are citations.
_MARGIN_CAP_MARKER_RE = re.compile(
    r"^[cg][ab][pv]\.\s*[ivxlcn]{1,7}\.\s*"
    r"|"
    r"\s*[cg][ab][pv]\.\s*[ivxlcn]{1,7}\.$",
    re.IGNORECASE,
)

# The same marker, used only to *locate* a chapter whose CAPUT heading
# did not survive OCR — never to delete text, so it can be looser.
_MARGIN_CHAP_NUM_RE = re.compile(
    r"(?:^|\s)[cg][ab][pv]\.\s*([ivxlcn]{1,7})\.",
    re.IGNORECASE,
)

# A line closes a sentence — and therefore a paragraph — when it ends
# in one of these. A trailing hyphen is explicit word division and is
# the strongest possible continuation signal.
_SENTENCE_END_RE = re.compile(r"[.?!:]['\"’”)]?\s*$")

# Orphaned marginal gloss lines are short. Body lines that are this
# short and isolated exist, which is why length alone does not decide
# it — see `_drop_margin_orphans`.
_ORPHAN_MAX_CHARS = 30

# How close to a page break an isolated short line must be to count as
# marginal debris rather than body text. Measured on `leviathan_lat.txt`:
# real orphaned glosses sit 3–6 lines from their running head, while the
# nearest short isolated body line is 24 away.
_ORPHAN_PAGE_BREAK_WINDOW = 6

# Chapter counts per work. Used to reject an OCR-noise numeral that
# happens to match the heading shape.
_MAX_CHAPTER_BY_CODE: dict[str, int] = {
    "leviathan_lat": 47,
    "de_cive_lat": 18,
}

# First publication of each work. Must agree with `CorpusWork.edition_year`
# in `authors/hobbes_works.py`; the two feed the same editions row.
_EDITION_YEAR_BY_CODE: dict[str, str] = {
    "leviathan_lat": "1668",
    "de_cive_lat": "1642",
}

# Below this a "paragraph" is marginal debris or a stray heading
# fragment, not a retrieval unit.
_MIN_CHUNK_CHARS = 80


def _roman_to_int(roman: str) -> int | None:
    """Convert a Roman numeral to int, tolerating the two OCR
    substitutions Molesworth's numerals actually suffer.

    Far less permissive than the version this replaced, which had to
    cope with column-linearized 17th-century OCR (``X X V I I L``).
    Molesworth's headings are clean; only the final ``I`` of a numeral
    is ever misread, as ``L`` (``XLIL`` for XLII, ``XLVIL`` for XLVII),
    and ``T`` occasionally stands in for ``I``.

    Returns None for input that is not a numeral at all, rather than
    inventing a chapter number.
    """

    if not roman:
        return None
    upper = re.sub(r"\s+", "", roman).upper()
    if not upper:
        return None
    upper = upper.replace("T", "I")
    # Trailing L where the numeral's final I was misread. Only fire
    # when the rest already contains an I — that is what distinguishes
    # "XLIL" (=XLII) from the legitimate "XL" (=40) and "XLI".
    if len(upper) >= 3 and upper.endswith("L") and "I" in upper[:-1]:
        upper = upper[:-1] + "I"
    if upper.isdigit():
        return int(upper)
    return roman_to_int(upper)


@dataclass(frozen=True)
class _Line:
    """One classified source line.

    ``kind`` is one of ``caput`` (payload = chapter number), ``drop``
    (running head, page number, signature — never text), ``blank``, or
    ``body`` (payload = the text, margin already stripped).

    ``raw`` keeps the line as it arrived, margin marker included.
    `_find_margin_turnover` reads it: the marker is the only evidence
    left of a chapter whose heading the OCR lost, and `payload` has
    already had it removed.
    """

    kind: str
    payload: str | int | None = None
    raw: str = ""


def _strip_inline_margin(line: str) -> str:
    """Remove a run-in marginal ``cap. <roman>.`` marker from a body line.

    Only at the line's ends — see `_MARGIN_CAP_MARKER_RE` for why the
    middle of the line must be left alone.
    """

    return _MARGIN_CAP_MARKER_RE.sub("", line.strip())


def _classify(line: str, *, max_chap: int) -> _Line:
    """One raw line → its role. See the module docstring for why each
    shape exists."""

    if not line.strip():
        return _Line("blank")
    m = _CAPUT_HEADING_RE.match(line)
    if m is not None:
        n = _roman_to_int(m.group(1))
        if n is not None and 0 < n <= max_chap:
            return _Line("caput", n)
        # A numeral we cannot read, or one past the work's last
        # chapter, is OCR noise in the shape of a heading. Dropping it
        # rather than treating it as body keeps it out of the text.
        return _Line("drop")
    if _PAGE_NUM_RE.match(line) or _SIGNATURE_RE.match(line):
        return _Line("drop")
    if _RUNNING_HEAD_RE.match(line):
        return _Line("drop")
    stripped = _strip_inline_margin(line).strip()
    if not stripped:
        return _Line("blank")
    return _Line("body", stripped, raw=line.strip())


def _drop_margin_orphans(lines: list[_Line]) -> list[_Line]:
    """Blank out short isolated body lines that sit beside a page break.

    The marginal gloss column is sometimes OCR'd onto its own line
    rather than run into a body line, leaving fragments like
    ``Deserraone.`` or ``natfonum. . -*t`` stranded between blanks. Left
    in place they are spliced into the middle of a paragraph that spans
    the page break.

    Shortness and isolation do not identify them on their own — a real
    body line can be both. Their distinguishing property is *where*
    they occur: a gloss is stranded by the page break that produced it,
    so it is always within a handful of lines of the running head we
    dropped. ``momento fere temporis.`` is short and isolated too, and
    is 24 lines from the nearest one.
    """

    breaks = [i for i, ln in enumerate(lines) if ln.kind in ("drop", "caput")]
    if not breaks:
        return lines
    break_set = set(breaks)
    out = list(lines)
    for i, ln in enumerate(lines):
        if ln.kind != "body":
            continue
        text = str(ln.payload)
        if len(text) > _ORPHAN_MAX_CHARS:
            continue
        # Isolated means fenced by blank lines on both sides — the gloss
        # sits alone in the hole the page break left. Asking instead
        # what the nearest *non-blank* neighbours are gets this wrong:
        # the nearest one above is the last body line of the previous
        # page, so no real gloss would ever qualify.
        if not _blank_at(lines, i - 1) or not _blank_at(lines, i + 1):
            continue
        near = any(
            j in break_set
            for j in range(
                i - _ORPHAN_PAGE_BREAK_WINDOW, i + _ORPHAN_PAGE_BREAK_WINDOW + 1
            )
        )
        if near:
            out[i] = _Line("blank")
    return out


def _blank_at(lines: list[_Line], i: int) -> bool:
    """Whether position ``i`` is a blank line. Off either end counts as
    blank, so a fragment stranded at the very top or bottom of a file
    still reads as isolated."""

    if i < 0 or i >= len(lines):
        return True
    return lines[i].kind == "blank"


def _join_body(buf: list[str]) -> str:
    """Join body lines into one paragraph, honouring word division.

    A line ending in ``-`` is a word split across the line break: the
    hyphen goes, and no space is inserted.
    """

    out: list[str] = []
    for line in buf:
        if out and out[-1].endswith("-"):
            out[-1] = out[-1][:-1] + line
        else:
            out.append(line)
    return " ".join(out)


def _paragraphs(lines: list[_Line]) -> Iterator[str]:
    """Yield one string per paragraph.

    A blank run ends the paragraph only when the last body line closed
    a sentence. Otherwise the blank is the hole a page break left and
    the paragraph continues across it.
    """

    buf: list[str] = []
    for ln in lines:
        if ln.kind == "body":
            buf.append(str(ln.payload))
            continue
        if ln.kind == "blank":
            if buf and _SENTENCE_END_RE.search(buf[-1]):
                yield _join_body(buf)
                buf = []
            continue
        # `drop` lines are holes in the page, never paragraph ends —
        # falling through here is what lets a paragraph span one.
    if buf:
        yield _join_body(buf)


def parse_file(
    path: Path,
    *,
    work_title: str,
    work_code: str,
) -> Iterator[Chunk]:
    """Yield one Chunk per paragraph of a Molesworth Latin Hobbes file.

    The caller supplies the canonical work title (used as both
    ``Chunk.work`` and an input to the chunk-id hash) and the short
    work-code carried in ``CorpusWork.code``.
    """

    max_chap = _MAX_CHAPTER_BY_CODE.get(work_code, 99)
    # The year of the work's first publication, NOT of the Molesworth
    # reprint we read it from. That is the corpus convention for an
    # original-language edition — Spinoza's *Ethica* is 1677 though its
    # text comes from thelatinlibrary, and Descartes' *Principia* is
    # 1644 though its text comes from Adam-Tannery IX. Writing 1839
    # here would make Hobbes the only Latin original dated by its
    # modern printing.
    edition_year = _EDITION_YEAR_BY_CODE.get(work_code, "1839")

    raw = path.read_text(encoding="utf-8").split("\n")
    classified = [_classify(ln, max_chap=max_chap) for ln in raw]
    classified = _drop_margin_orphans(classified)

    # Split into per-chapter runs. Everything before the first CAPUT is
    # front matter (half-title, dedication) and is dropped with it.
    chapters: list[tuple[int, list[_Line]]] = []
    current: list[_Line] | None = None
    current_chap: int | None = None
    seen: set[int] = set()
    for ln in classified:
        if ln.kind == "caput":
            chap = int(ln.payload)  # type: ignore[arg-type]
            # A repeated or backwards chapter number is a cross-
            # reference the heading regex caught, not a new chapter.
            if chap in seen or (current_chap is not None and chap < current_chap):
                continue
            if current is not None and current_chap is not None:
                chapters.append((current_chap, current))
            current = []
            current_chap = chap
            seen.add(chap)
            continue
        if current is not None:
            current.append(ln)
    if current is not None and current_chap is not None:
        chapters.append((current_chap, current))

    chapters = _recover_missing_chapters(chapters, max_chap=max_chap)

    for chap, chap_lines in chapters:
        book = f"Cap {chap}"
        para_no = 0
        for para in _paragraphs(chap_lines):
            text = unicodedata.normalize("NFC", _norm_text(para))
            if len(text) < _MIN_CHUNK_CHARS:
                continue
            para_no += 1
            section = f"{book}, ¶{para_no}"
            yield Chunk(
                chunk_id=_make_chunk_id(
                    path.name,
                    work_title,
                    "lat",
                    "",
                    section,
                    "",
                    text[:120],
                ),
                corpus="hobbes",
                author="Hobbes",
                work=work_title,
                lang="lat",
                section=section,
                book=book,
                page=None,
                speaker=None,
                text=text,
                source_file=path.name,
                translator="(Original)",
                edition_year=edition_year,
                citation_system=None,
            )


def _recover_missing_chapters(
    chapters: list[tuple[int, list[_Line]]],
    *,
    max_chap: int,
) -> list[tuple[int, list[_Line]]]:
    """Split a chapter run in two where a CAPUT heading was lost to OCR.

    One chapter of the Latin Leviathan — XXXV, *De significatione in
    scripturis regni Dei, sancti, sacri, et sacramenti* — has neither a
    heading nor a title line surviving in the scan. Without this its
    ~90 paragraphs are absorbed into XXXIV and carry that chapter
    number, which is worse than the chapter simply being absent: a
    missing chapter is visibly missing, whereas a mislabelled one reads
    as correct.

    The marginal chapter marker is the recovery anchor. It runs down
    the outer edge of every page and changes at the chapter boundary
    even when the heading is gone, so the chapter turned over on the
    page whose running head immediately precedes the first marker
    reading ``N``. Splitting there is accurate to one page.

    Two occurrences are required before acting, because a single one is
    as likely to be a stray match as a margin.
    """

    by_chap = dict(chapters)
    if not by_chap:
        return chapters
    recovered: list[tuple[int, list[_Line]]] = []
    for missing in range(1, max_chap + 1):
        if missing in by_chap:
            continue
        if (missing - 1) not in by_chap or (missing + 1) not in by_chap:
            # Without both neighbours there is nothing to bound the
            # split against, and a guess would be unfalsifiable.
            continue
        donor = by_chap[missing - 1]
        split = _find_margin_turnover(donor, target_chap=missing)
        if split is None:
            continue
        by_chap[missing - 1] = donor[:split]
        recovered.append((missing, donor[split:]))
    out = list(by_chap.items())
    out.extend(recovered)
    out.sort(key=lambda pair: pair[0])
    return out


def _find_margin_turnover(lines: list[_Line], *, target_chap: int) -> int | None:
    """Index in ``lines`` where the marginal chapter marker turns over
    to ``target_chap``, or None when it never does (or does so only
    once, which is not enough signal to act on).

    Returns the page break preceding the first such marker rather than
    the marker's own line: the marker sits a line or two into the page,
    while the chapter began at its head.
    """

    hits: list[int] = []
    for i, ln in enumerate(lines):
        if ln.kind != "body":
            continue
        m = _MARGIN_CHAP_NUM_RE.search(ln.raw)
        if m is None:
            continue
        if _roman_to_int(m.group(1)) == target_chap:
            hits.append(i)
    if len(hits) < 2:
        return None
    first = hits[0]
    for j in range(first, -1, -1):
        if lines[j].kind == "drop":
            return j
    return first


def parse_dir(directory: Path) -> Iterator[Chunk]:
    """Walk ``data/hobbes/raw_lat/`` and parse each Latin Hobbes file.
    Maps filename → (work title, work code) via ``hobbes_works.find_work``."""

    from minerva.authors.hobbes_works import find_work

    for entry in sorted(directory.iterdir()):
        if not entry.is_file() or not entry.name.endswith(".txt"):
            continue
        cw = find_work(entry.name)
        if cw is None:
            print(f"hobbes_la: skipping unknown file {entry.name!r}")
            continue
        if cw.lang != "lat":
            # The find_work table contains the English works too; only
            # parse the Latin ones here.
            continue
        yield from parse_file(entry, work_title=cw.title, work_code=cw.code)
