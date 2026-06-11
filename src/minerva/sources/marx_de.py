"""Parser for the OCR'd German Marx corpus.

Three source files, all from Internet Archive scans:

  * ``kapital_bd1.txt`` — IA ``daskapitalkritik67marx``, the 1867
    Fraktur first edition of *Das Kapital, Band I* (Marx's own
    publication, 6 chapters in 1 Buch).
  * ``kapital_bd2.txt`` — IA ``ldpd_13046079_002``, Engels's 1885
    edition of *Das Kapital, Band II*.
  * ``kapital_bd3.txt`` — IA ``ldpd_13046079_003``, Engels's 1894
    edition of *Das Kapital, Band III*.

OCR noise patterns (1867 Fraktur sample):

  * ``k ↔ t`` confusion ("Katfee" for "Kaffee", common in Fraktur
    OCR where the ligature is misread).
  * Long-s confusion ("Hegt" for "liegt").
  * Lost or extra inter-word spaces.
  * Page running heads + page numbers interleaved with body.

Chapter detection challenges:

  1. **TOC at start of book**. The Fraktur scan lists Erstes through
     Sechstes Kapitel in lines 59-212 as a table-of-contents block
     BEFORE the body begins at line ~500. We filter this by
     identifying the dense front-matter cluster and skipping it.

  2. **Body-text cross-references**. Sentences like "sieh drittes
     Kapitel" appear inside body paragraphs. These NEVER start with
     the chapter wordform at line-start, so our ``^\\s*<wordform>``
     regex anchor naturally filters them out.

  3. **Late-edition chapter numbering**. The 1867 Bd 1 uses 6
     chapter divisions (Erstes through Sechstes); later editions
     have 25. We cap per-work via ``_MAX_CHAPTER_BY_CODE`` so the
     parser doesn't get tricked by spurious matches into thinking
     there are 25 chapters in the 6-chapter scan.

Each detected chapter becomes one Chunk. Chunk granularity at the
chapter level is what FTS / embedding retrieval needs; finer-grained
splitting on OCR noise would be unreliable.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path

from minerva.sources._roman import roman_to_int
from minerva.tei import Chunk, _make_chunk_id, _norm_text

# ──────────────────────────────────────────────────────────────────
# Wordform → integer
# ──────────────────────────────────────────────────────────────────

# German ordinal-adjective wordforms for "the Nth chapter":
#     Erstes Kapitel, Zweites Kapitel, ..., Fünfundzwanzigstes Kapitel.
# We accept all forms up to 30 since later Engels editions can hit
# 25-33 chapters depending on volume.
_WORDFORM_TO_INT: dict[str, int] = {
    "Erstes": 1,
    "Zweites": 2,
    "Drittes": 3,
    "Viertes": 4,
    "Fünftes": 5,
    "Sechstes": 6,
    "Siebentes": 7,
    "Siebtes": 7,
    "Achtes": 8,
    "Neuntes": 9,
    "Zehntes": 10,
    "Elftes": 11,
    "Zwölftes": 12,
    "Dreizehntes": 13,
    "Vierzehntes": 14,
    "Fünfzehntes": 15,
    "Sechzehntes": 16,
    # OCR variant in the ldpd Bd 2 scan: "Sechszehntes" (extra `s`,
    # an older spelling of Sechzehntes). Without this entry the Bd 2
    # chapter 16 heading at L16998 silently fails to match.
    "Sechszehntes": 16,
    "Siebzehntes": 17,
    "Achtzehntes": 18,
    "Neunzehntes": 19,
    "Zwanzigstes": 20,
    "Einundzwanzigstes": 21,
    "Zweiundzwanzigstes": 22,
    "Dreiundzwanzigstes": 23,
    "Vierundzwanzigstes": 24,
    "Fünfundzwanzigstes": 25,
    "Sechsundzwanzigstes": 26,
    "Siebenundzwanzigstes": 27,
    "Achtundzwanzigstes": 28,
    "Neunundzwanzigstes": 29,
    "Dreissigstes": 30,
    "Dreißigstes": 30,
}

_WORDFORM_PATTERN = "|".join(_WORDFORM_TO_INT.keys())


# ──────────────────────────────────────────────────────────────────
# Chapter heading regex
# ──────────────────────────────────────────────────────────────────

# Line-start chapter heading in any of three shapes:
#   1. German wordform: "Erstes Kapitel."  (most common; the 1867
#      Fraktur edition uses this consistently)
#   2. Arabic numeral: "Kapitel 1." / "Kapitel 7"
#   3. Roman numeral: "Kapitel I." / "Kapitel XXVII"
# The dot/comma after the numeral is optional (OCR-flexible). Allow
# trailing title text (up to 80 chars) for "Kapitel III. Die Form
# des Werths." style.
_CHAPTER_HEADING_RE = re.compile(
    r"^\s*("
    # `\s*` (not `\s+`) between wordform and `Kapitel` so OCR-merged
    # forms like "AchtzehntesKapitel." (Bd 2 L21198) still match.
    rf"(?:{_WORDFORM_PATTERN})\s*Kapitel"
    # Numeric / Roman fallback only via the full word "Kapitel".
    # We deliberately don't match `Kap. <N>` — that abbreviation is
    # almost always an in-text cross-reference (e.g., "Kap. XVI, 1. —
    # F.E]" appearing in Engels's editorial footnotes in Kapital Bd 3),
    # not a real chapter heading.
    r"|Kapitel\s+(?:[IVXLC]+|\d{1,2})"
    r")"
    # Trailing punctuation cluster — OCR junk after a real heading
    # routinely includes closing parens, curly quotes, superscript-
    # ish markers (`AchtzehntesKapitel.”“)` and `Neunzehntes Kapitel.)`).
    # We allow up to 6 non-alphanumeric chars from the standard
    # punctuation + curly-quote / French-quote set before the
    # optional title.
    r"[.,;:\)\]\}\"\'“”„«»]{0,6}"
    r"(?:\s+.{0,80})?\s*$",
    re.IGNORECASE,
)

# Bare page number line (1-4 digits). Used to filter chunk text.
_PAGE_NUM_RE = re.compile(r"^\s*\d{1,4}\s*$")


# ──────────────────────────────────────────────────────────────────
# Per-work caps + TOC-detection thresholds
# ──────────────────────────────────────────────────────────────────

# Canonical chapter count per work (used as the noise cap — anything
# beyond is OCR-noise or stray text). 1867 Bd 1 has 6 chapters;
# Engels's Bd 2 + Bd 3 are larger.
_MAX_CHAPTER_BY_CODE: dict[str, int] = {
    "kapital_bd1": 6,  # 1867 first ed., 6-chapter structure
    "kapital_bd2": 21,  # Engels 1885, 21 chapters across 3 Abschnitte
    "kapital_bd3": 52,  # Engels 1894, 52 chapters across 7 Abschnitte
}

# TOC cluster threshold: if two consecutive chapter-heading
# candidates are within this many lines, they're considered part of
# the front-matter TOC. A real chapter has many KB of body content
# between it and the next chapter, so the line gap is large (~1000+
# for Bd 1's 6 chapters across 30k OCR lines).
_TOC_CLUSTER_MAX_GAP = 200

# Where _MAX_CHAPTER_BY_CODE doesn't have an entry, this generous
# default is used. Set high so we don't accidentally cap a long work.
_DEFAULT_MAX_CHAPTER = 60


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────


def _heading_to_int(match_text: str) -> int | None:
    """Parse the matched chapter-heading group (e.g., "Erstes Kapitel",
    "Kapitel III", "Kap. 7") into the chapter integer it represents.
    Returns None if the parse fails."""

    stripped = match_text.strip()
    # German wordform?
    for word, n in _WORDFORM_TO_INT.items():
        if stripped.lower().startswith(word.lower()):
            return n
    # "Kapitel <numeral>" or "Kap. <numeral>"
    m = re.match(r"^(?:Kapitel|Kap\.)\s+([IVXLC]+|\d{1,2})", stripped, re.IGNORECASE)
    if m is None:
        return None
    token = m.group(1)
    if token.isdigit():
        return int(token)
    return roman_to_int(token)


def _find_chapter_candidates(lines: list[str]) -> list[tuple[int, int]]:
    """Walk every line and return [(line_index, chapter_int), ...]
    for every line that matches the chapter-heading regex."""

    out: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        m = _CHAPTER_HEADING_RE.match(line)
        if m is None:
            continue
        n = _heading_to_int(m.group(1))
        if n is None:
            continue
        out.append((i, n))
    return out


def _filter_toc_cluster(
    candidates: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Skip front-matter TOC by detecting the chapter-number drop.

    The TOC lists chapter numbers in monotonically-increasing order
    (Cap 1, 2, 3, ...). When the body begins, the count restarts at
    1 (or close to 1). The transition from "TOC's high-water Cap N"
    to "body's Cap 1" is a structural drop in chapter number — far
    more reliable than line-gap heuristics, which were brittle on
    works where TOC entries were close to body entries (Kapital Bd 3
    has only 84 lines between last TOC entry and first body chapter).

    Returns everything from the drop onward. If no drop is observed,
    returns the input unchanged (no TOC present — body candidates
    only, monotonically increasing).

    The `max_so_far - 2` slack accommodates OCR misreads where two
    consecutive TOC entries might slip backward by 1 chapter; a drop
    of ≥3 is the unambiguous body-restart signal.
    """

    if len(candidates) < 2:
        return candidates
    max_so_far = candidates[0][1]
    for i in range(1, len(candidates)):
        chap = candidates[i][1]
        if chap < max_so_far - 2:
            return candidates[i:]
        if chap > max_so_far:
            max_so_far = chap
    return candidates


def _filter_chapter_cap(
    candidates: list[tuple[int, int]],
    *,
    max_chap: int,
) -> list[tuple[int, int]]:
    """Drop candidates with chap > max_chap (OCR noise) or chap < 1."""
    return [(i, c) for (i, c) in candidates if 0 < c <= max_chap]


def _filter_monotonic(
    candidates: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Keep only the first occurrence of each chapter number, in
    document order. Drops body-text cross-references that happen to
    match the line-start heading shape (rare but possible) and
    end-of-book TOC re-listings (Hobbes-Latin pattern, but inverse:
    we keep the FIRST, not the last)."""

    seen: set[int] = set()
    out: list[tuple[int, int]] = []
    for i, c in candidates:
        if c in seen:
            continue
        out.append((i, c))
        seen.add(c)
    return out


def _is_chrome(line: str) -> bool:
    """Lines we drop from chunk text: blank, bare page number,
    or running-head-style 'Kapitel III. Die Sektion.' that appears
    on every page. We keep paragraph-shaped body text only."""

    stripped = line.strip()
    if not stripped:
        return True
    return bool(_PAGE_NUM_RE.match(stripped))


# ──────────────────────────────────────────────────────────────────
# Main parse_file
# ──────────────────────────────────────────────────────────────────


def parse_file(
    path: Path,
    *,
    work_title: str,
    work_code: str,
) -> Iterator[Chunk]:
    """Yield one Chunk per detected chapter for an OCR'd Marx file.

    Pipeline:
      1. Read lines.
      2. Find every line that matches a chapter-heading regex.
      3. Filter out the front-matter TOC cluster (dense candidates
         near start of file).
      4. Cap by canonical chapter count for the work.
      5. Filter to monotonic in-order first-occurrence.
      6. Emit one Chunk per surviving heading; chunk text = lines
         from the heading to the next heading (or EOF), with blank
         lines and bare page numbers stripped.
    """

    max_chap = _MAX_CHAPTER_BY_CODE.get(work_code, _DEFAULT_MAX_CHAPTER)

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        lines = fh.read().split("\n")

    candidates = _find_chapter_candidates(lines)
    candidates = _filter_toc_cluster(candidates)
    candidates = _filter_chapter_cap(candidates, max_chap=max_chap)
    candidates = _filter_monotonic(candidates)

    if not candidates:
        # No chapters detected — emit a single chunk covering the
        # whole body (drop chrome). Better to have something
        # searchable than nothing.
        body = [ln.strip() for ln in lines if not _is_chrome(ln)]
        text = unicodedata.normalize("NFC", _norm_text(" ".join(body)))
        if len(text) >= 80:
            chunk_id = _make_chunk_id(
                path.name,
                work_title,
                "deu",
                "",
                "",
                "",
                text[:120],
            )
            yield Chunk(
                chunk_id=chunk_id,
                corpus="marx",
                author="Marx",
                work=work_title,
                lang="deu",
                section=None,
                book=None,
                page=None,
                speaker=None,
                text=text,
                source_file=path.name,
                translator="(Original)",
                edition_year=_edition_year_for(work_code),
                citation_system=None,
            )
        return

    # Emit one chunk per chapter — body = lines[start:end] minus chrome.
    for i, (start_line, chap_num) in enumerate(candidates):
        end_line = candidates[i + 1][0] if i + 1 < len(candidates) else len(lines)
        body = [ln.strip() for ln in lines[start_line + 1 : end_line] if not _is_chrome(ln)]
        text = unicodedata.normalize("NFC", _norm_text(" ".join(body)))
        if len(text) < 80:
            continue
        section = f"Kapitel {chap_num}"
        chunk_id = _make_chunk_id(
            path.name,
            work_title,
            "deu",
            "",
            section,
            "",
            text[:120],
        )
        yield Chunk(
            chunk_id=chunk_id,
            corpus="marx",
            author="Marx",
            work=work_title,
            lang="deu",
            section=section,
            book=None,
            page=None,
            speaker=None,
            text=text,
            source_file=path.name,
            translator="(Original)",
            edition_year=_edition_year_for(work_code),
            citation_system=None,
        )


def _edition_year_for(work_code: str) -> str:
    """Match marx_works.py's edition_year fields."""
    return {
        "kapital_bd1": "1867",
        "kapital_bd2": "1885",
        "kapital_bd3": "1894",
    }.get(work_code, "")


# ──────────────────────────────────────────────────────────────────
# Directory walker
# ──────────────────────────────────────────────────────────────────


def parse_dir(directory: Path) -> Iterator[Chunk]:
    """Walk `data/marx/raw_deu_ocr/` and parse each Marx OCR file
    via `marx_works.find_work` to recover its (title, code)."""

    from minerva.authors.marx_works import find_work

    for entry in sorted(directory.iterdir()):
        if not entry.is_file() or not entry.name.endswith(".txt"):
            continue
        cw = find_work(entry.name)
        if cw is None:
            print(f"marx_de: skipping unknown file {entry.name!r}")
            continue
        yield from parse_file(entry, work_title=cw.title, work_code=cw.code)
