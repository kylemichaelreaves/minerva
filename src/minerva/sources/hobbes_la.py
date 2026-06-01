"""Parser for the OCR'd Latin Hobbes corpora.

Two source files, both from Internet Archive scans of historical
editions:

  * ``leviathan_lat.txt`` — IA ``leviathansivedem00hobb``, the 1668
    Blaeu edition of *Leviathan, sive de materia, forma, & potestate
    civitatis ecclesiasticae et civilis*. Chapter headings appear as
    explicit ``C A P V T <ROMAN>.`` markers (OCR linearizes the column
    layout with extra whitespace between letters).
  * ``de_cive_lat.txt`` — IA ``gri_elementaphilos00ho``, a 1704
    reprint of the 1642 *Elementa philosophica de cive*. No explicit
    chapter headings survive the OCR linearization; chapter
    transitions are inferred from changes in the page-running-head
    ``Cap.<roman>.`` marker.

OCR noise pattern shared by both files:

  * Long-s confused with ``f`` (``Poteftate`` for ``Potestate``).
  * Repeated page running heads polluting the line stream
    (``Cap.  N.  De  Homine.  PAGE`` in Leviathan; ``Cap.N.
    LIBERTAS.  PAGE`` in De Cive).
  * Front-matter / dedication / TOC scanned alongside the body — we
    drop everything before the FIRST chapter marker.
  * Bare page numbers and stray digits.

Both works number chapters continuously across Pars (Lev: I–XLVII,
De Cive: I–XVIII). We use ``section = "Cap <arabic>"`` and trust the
chapter number to identify the chunk uniquely. Pars / Part detection
is deferred — it's nice-to-have for display but not load-bearing
for retrieval.

Each chapter becomes one ``Chunk``. The OCR is noisy enough that
finer-grained per-article chunking would be unreliable; chapter
granularity is what the FTS / embedding retrieval needs.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path

from minerva.tei import Chunk, _make_chunk_id, _norm_text

# ──────────────────────────────────────────────────────────────────
# Chapter detection
# ──────────────────────────────────────────────────────────────────

# Leviathan "CAPVT <roman>." heading line. The OCR yields two forms:
#   * spaced: "C    A    P    V    T      XIV." (column-linearized)
#   * tight:  "CAPVT       XXVII."
# We accept both, allow an optional title on the same line ("CAPVT
# XXX. De officio Summi Imperantis."), and tolerate roman numerals
# with OCR substitutions (L for I, T for I — e.g. "XIL" = XII).
_CAPVT_HEADING_RE = re.compile(
    # Pre-numeral skeleton tolerates two OCR pathologies seen in the
    # 1668 Latin Leviathan scan:
    #   * F-for-P substitution ("C A F V T XXV." at L989 of the IA OCR);
    #   * stray non-whitespace glyphs between letters, e.g. a literal
    #     backslash ("C A P V T\ XI." at L438) where OCR misread a
    #     vertical type rule as `\`. We allow `\` alongside whitespace
    #     as a separator between every CAPVT letter and before the
    #     numeral.
    r"^\s*C[\s\\]*A[\s\\]*[PF][\s\\]*V[\s\\]*T[\s\\]+"
    # Numeral group: 1–6 roman/OCR-substituted letters, each
    # potentially separated by whitespace (column-linearization
    # spaces between every glyph). We capture the whole group then
    # strip whitespace before converting.
    r"([IVXLTC](?:\s*[IVXLTC]){0,7})"
    r"[.,;:]?(?:\s+.{0,80})?\s*$",
    re.IGNORECASE,
)

# Page-running-head pattern: `Cap.  <roman-or-arabic>.  <Title>.  <page>`
# Used both to skip running heads from chunk text (Leviathan) AND to
# detect chapter transitions in De Cive (which has no explicit
# chapter heading). Tolerant of OCR noise:
#   - "Cap." can OCR as "Cap.", "Cap,", "Cap.T", "Cap.I"
#   - chapter numeral can be roman (I, II, III, IL, XV) or arabic (1, 2)
#   - "I L" / "T L" appear for "II" (the second `I` OCRs as `L`)
_RUNNING_HEAD_CHAP_RE = re.compile(
    r"^\s*Cap\.?\s*([IVXLCDM]{1,5}|\d{1,3})[.,;]?\s+",
    re.IGNORECASE,
)

# Bare page number line (1-3 digits, possibly with garbage punct).
_PAGE_NUM_RE = re.compile(r"^\s*[\divxlcdmIVXLCDM]{1,4}[.,;]?\s*$")

_ROMAN_VALUES = {
    "I": 1,
    "V": 5,
    "X": 10,
    "L": 50,
    "C": 100,
    "D": 500,
    "M": 1000,
}


def _roman_to_int(roman: str) -> int | None:
    """Convert a Roman numeral string to int. Returns None when the
    input is plainly not Roman (e.g., already arabic, or OCR garbage).
    Lenient: tolerates lowercase, internal whitespace from column-
    linearized OCR (``X X V I I L`` for "XXVIII"), and common
    glyph substitutions but refuses to invent a value for empty
    or unknown input."""

    if not roman:
        return None
    # Strip internal whitespace from spaced numerals.
    upper = re.sub(r"\s+", "", roman).upper()
    # Common OCR substitutions for Roman numerals:
    #   - Trailing or internal "L" where "I" should be (the final
    #     stroke of "II" misread as a tall "L"): "XIL" → "XII",
    #     "I L" → "II", "X X V I I L" → "XXVIII".
    #   - "T" for "I".
    # Apply *trailing*-L → I only (a real "L"=50 in valid Roman
    # numerals only appears at the start of XL/L/LX/LXX etc., never
    # as a tail glyph after I).
    upper = upper.replace("T", "I")
    # OCR substitution: trailing "I" after multiple X's misread as
    # "L" (`CAPVT  XXX  L` for chapter XXXI in the 1668 Latin
    # Leviathan, L1326). Only fire when the prefix ends in `X` and
    # contains no internal `L`, and the whole string is ≥3 chars —
    # that excludes legitimate `XL` (=40) and forms with a real
    # L-component (`XLI`, `LX`, `LXX`). Run before the I-final-stroke
    # rule below so "XXX  L" rewrites cleanly without colliding.
    if len(upper) >= 3 and upper.endswith("L") and upper[-2] == "X" and "L" not in upper[:-1]:
        upper = upper[:-1] + "I"
    if upper.endswith("L") and "I" in upper[-3:-1]:
        upper = upper[:-1] + "I"
    # Pure-digit case: caller wanted a roman but it's arabic; convert.
    if upper.isdigit():
        try:
            return int(upper)
        except ValueError:
            return None
    if not all(c in _ROMAN_VALUES for c in upper):
        return None
    total = 0
    prev = 0
    for c in reversed(upper):
        v = _ROMAN_VALUES[c]
        if v < prev:
            total -= v
        else:
            total += v
            prev = v
    return total or None


def _classify(line: str) -> tuple[str, object]:
    """One line → (kind, payload). Kinds:
    * ``chapter_heading`` (payload = chapter int) — explicit CAPVT
    * ``running_head`` (payload = chapter int or None) — page header
    * ``page_num`` — bare number, drop
    * ``blank`` — whitespace only
    * ``body`` — content for the current chunk
    """

    if not line.strip():
        return "blank", None
    m = _CAPVT_HEADING_RE.match(line)
    if m is not None:
        n = _roman_to_int(m.group(1))
        if n is not None:
            return "chapter_heading", n
    m = _RUNNING_HEAD_CHAP_RE.match(line)
    if m is not None:
        n = _roman_to_int(m.group(1))
        return "running_head", n
    if _PAGE_NUM_RE.match(line):
        return "page_num", None
    return "body", line.strip()


# Canonical chapter counts per work — used as a hard cap to reject
# OCR-noise chapter numbers (a "Cap. 49." inside body text would
# otherwise spawn a spurious chunk).
_MAX_CHAPTER_BY_CODE: dict[str, int] = {
    "leviathan_lat": 47,
    "de_cive_lat": 18,
}


def parse_file(
    path: Path,
    *,
    work_title: str,
    work_code: str,
) -> Iterator[Chunk]:
    """Yield one Chunk per chapter for an OCR'd Latin Hobbes file.
    The caller supplies the canonical work title (used as both
    ``Chunk.work`` and the input to the chunk-id hash) and the
    short work-code identifier carried in ``CorpusWork.code``.

    Robustness to OCR noise comes from three constraints on the
    chapter number we accept:

    1. **Cap**: integer must be in ``1..MAX`` where MAX is the
       canonical chapter count for this work (47 for Leviathan, 18
       for De Cive). Anything beyond is an OCR misread.
    2. **Monotonic-with-tolerance**: we only accept a new chapter
       number that's ``> current`` or equal-then-rising via running-
       head repetition. Backwards jumps (current=15, candidate=3)
       are typically references to earlier chapters in body text, not
       real transitions.
    3. **Once-per-chapter**: once a chapter has been emitted, we
       don't re-emit it (a stray running head referencing an earlier
       chapter is ignored).
    """

    max_chap = _MAX_CHAPTER_BY_CODE.get(work_code, 99)

    with path.open("r", encoding="utf-8") as fh:
        lines = fh.read().split("\n")

    # Two-pass strategy: first decide which mode this file uses for
    # CHAPTER DETECTION. Either:
    #   * "capvt" mode — there's a robust set of CAPVT marker lines
    #     in the file (Latin Leviathan). We use ONLY those for
    #     chapter transitions; running heads are stripped from
    #     chunk text but ignored for detection. This avoids the
    #     interleaving problem where running heads and CAPVT lines
    #     get scrambled in column-linearized OCR.
    #   * "running_head" mode — no CAPVT markers exist (De Cive).
    #     We track chapter boundaries via changes in the page
    #     running head, requiring monotonic increases.
    # The threshold "≥10 CAPVTs" distinguishes a genuine chapter-
    # header system from one or two false-positive matches.
    capvt_count = sum(1 for ln in lines if _CAPVT_HEADING_RE.match(ln) is not None)
    mode = "capvt" if capvt_count >= 10 else "running_head"

    current_chap: int | None = None
    current_buf: list[str] = []
    # Parallel raw-line buffer — captures EVERY line for the current
    # chapter (running heads, body, page numbers) without the
    # body-only filtering applied to `current_buf`. Needed by the
    # gap-fill post-pass so it can search the donor chunk for
    # repeated page-running-head clusters that mark a chapter the
    # primary detector missed entirely (e.g. Latin Lev. Cap IV,
    # whose CAPVT line never survived the OCR).
    current_raw: list[str] = []
    # Deferred-emission list of (chap_num, clean_buf, raw_buf)
    # captured at every former yield site. After the main loop runs,
    # the post-pass walks this list looking for chapter-number gaps
    # and splits donor chunks at running-head clusters. Then we call
    # `emit()` once per pending entry and yield the result.
    pending: list[tuple[int, list[str], list[str]]] = []
    chunk_seen_chapters: set[int] = set()

    def flush_pending() -> None:
        """Move the current accumulator into `pending` if its chapter
        is set and hasn't been recorded yet. Used at every chapter-
        transition / end-of-file boundary."""

        nonlocal current_chap, current_buf, current_raw
        if current_chap is not None and current_chap not in chunk_seen_chapters:
            pending.append((current_chap, list(current_buf), list(current_raw)))
            chunk_seen_chapters.add(current_chap)
        current_buf = []
        current_raw = []

    def emit(chap: int, buf: list[str]) -> Chunk | None:
        # Skip OCR-noise chapter numbers (above the canonical count
        # for the work, or non-positive).
        if chap <= 0 or chap > max_chap:
            return None
        text = unicodedata.normalize("NFC", _norm_text(" ".join(buf)))
        # Below 80 chars is essentially empty (OCR'd page chrome only)
        # — drop it; the section locator would point at nothing.
        if len(text) < 80:
            return None
        section = f"Cap {chap}"
        chunk_id = _make_chunk_id(
            path.name,
            work_title,
            "lat",
            "",
            section,
            "",
            text[:120],
        )
        return Chunk(
            chunk_id=chunk_id,
            corpus="hobbes",
            author="Hobbes",
            work=work_title,
            lang="lat",
            section=section,
            book=None,
            page=None,
            speaker=None,
            text=text,
            source_file=path.name,
            translator="(Original)",
            edition_year="1668" if "leviathan" in work_code else "1642",
            citation_system=None,
        )

    for raw in lines:
        kind, payload = _classify(raw)

        if kind == "chapter_heading":
            # Explicit CAPVT marker (Leviathan). Flush prior chapter.
            new_chap = payload  # type: ignore[assignment]
            assert isinstance(new_chap, int)
            # Out-of-range chapter numbers come from OCR noise that
            # happened to match the CAPVT regex — drop and stay on
            # the current chapter.
            if new_chap <= 0 or new_chap > max_chap:
                continue
            # Backwards jumps after we've reached the final chapter
            # signal end-of-book apparatus (TOC restarts at Cap I).
            # Flush the final chapter and stop accumulating.
            if current_chap == max_chap and new_chap < current_chap:
                flush_pending()
                current_chap = None
                # Stop processing — everything past here is TOC/index.
                break
            # Other backwards jumps (current=15, new=3) are usually
            # body-text references to earlier chapters; ignore.
            if current_chap is not None and new_chap < current_chap:
                continue
            flush_pending()
            current_chap = new_chap
            continue

        if kind == "running_head":
            if mode == "capvt":
                # In CAPVT mode (Leviathan) running heads never drive
                # chapter transitions — the OCR scrambling makes them
                # unreliable for that. But we DO retain them in the
                # raw buffer so the gap-fill post-pass can use them
                # to detect chapters the primary detector missed.
                if current_chap is not None:
                    current_raw.append(raw)
                continue
            # In running-head mode (De Cive), chapter transitions ARE
            # detected here. Treat as a new chapter ONLY if the number
            # differs from the current one (re-running same chapter
            # is just another page within it).
            new_chap = payload  # type: ignore[assignment]
            if isinstance(new_chap, int):
                if new_chap <= 0 or new_chap > max_chap:
                    continue
                if current_chap is None:
                    current_chap = new_chap
                elif new_chap < current_chap:
                    # Backwards reference in body text — skip.
                    continue
                elif new_chap != current_chap and new_chap not in chunk_seen_chapters:
                    flush_pending()
                    current_chap = new_chap
                # else: same chapter or already-seen — skip the running
                # head line and continue.
            continue

        if kind in ("blank", "page_num"):
            continue

        # kind == "body" — accumulate if we have an active chapter.
        if current_chap is not None:
            current_buf.append(payload)  # type: ignore[arg-type]
            current_raw.append(raw)

    # Final flush of whatever was in flight at end of file.
    flush_pending()

    # ── Gap-fill post-pass ──────────────────────────────────────────
    # The CAPVT detector misses chapters whose heading didn't survive
    # OCR at all (Latin Lev. Cap IV is the canonical case). For each
    # missing chapter N where the surrounding chapters (N-1) and
    # (N+1) BOTH made it into `pending`, walk the (N-1) donor's raw
    # lines looking for a cluster of page-running-heads `Cap. N.`
    # (Arabic or Roman). Two or more such running heads within ±6
    # lines indicates we've found the donor's tail = the missing
    # chapter's body. Split and re-label.
    pending = _gap_fill_pending(pending)

    # ── Emit ────────────────────────────────────────────────────────
    pending.sort(key=lambda triple: triple[0])
    for chap, buf, _raw in pending:
        chunk = emit(chap, buf)
        if chunk is not None:
            yield chunk


def _gap_fill_pending(
    pending: list[tuple[int, list[str], list[str]]],
) -> list[tuple[int, list[str], list[str]]]:
    """Scan `pending` for missing chapter numbers between recorded
    ones and try to recover them from the preceding donor chunk's
    raw lines. Returns a (possibly-extended) pending list."""

    if not pending:
        return pending
    seen = {chap for chap, _, _ in pending}
    seen_max = max(seen)
    # Index donors by chapter number for quick lookup.
    by_chap = {chap: (buf, raw) for chap, buf, raw in pending}
    recovered: list[tuple[int, list[str], list[str]]] = []
    for n in range(1, seen_max + 1):
        if n in seen:
            continue
        if (n - 1) not in by_chap or (n + 1) not in by_chap:
            # Need both neighbours present to ground the split.
            continue
        donor_buf, donor_raw = by_chap[n - 1]
        split = _find_running_head_cluster(donor_raw, target_chap=n)
        if split is None:
            continue
        # `split` is the index into donor_raw where the cluster
        # starts. Translate that into the corresponding index into
        # donor_buf: every body line in donor_raw appears in
        # donor_buf in the same order (running heads were filtered
        # out), so count body lines in donor_raw[:split].
        body_lines_before = sum(1 for ln in donor_raw[:split] if _classify(ln)[0] == "body")
        new_n_minus_1_buf = donor_buf[:body_lines_before]
        new_n_buf = donor_buf[body_lines_before:]
        new_n_minus_1_raw = donor_raw[:split]
        new_n_raw = donor_raw[split:]
        # Update donor in-place via the by_chap mapping; record the
        # recovered chapter for later append.
        by_chap[n - 1] = (new_n_minus_1_buf, new_n_minus_1_raw)
        recovered.append((n, new_n_buf, new_n_raw))
    # Re-emit pending from by_chap to pick up the donor updates, then
    # append the recovered chapters.
    rebuilt = [(chap, buf, raw) for chap, (buf, raw) in by_chap.items()]
    rebuilt.extend(recovered)
    return rebuilt


def _find_running_head_cluster(raw_lines: list[str], *, target_chap: int) -> int | None:
    """Find the index of the FIRST line in `raw_lines` that is a
    page-running-head for chapter ``target_chap``, provided the
    chapter has ≥2 such running heads anywhere in `raw_lines`. The
    ≥2 guard filters out one-off body-text mentions like "vide
    Cap. 4 supra"; real page running heads recur on every page of
    the chapter, so any genuine chapter-N region has multiple.

    Returns the index of the first matching running head, or None
    if the chapter is mentioned 0 or 1 times (insufficient signal)."""

    def _matches(line: str) -> bool:
        m = _RUNNING_HEAD_CHAP_RE.match(line)
        if m is None:
            return False
        n = _roman_to_int(m.group(1))
        return n is not None and n == target_chap

    hits = [i for i, ln in enumerate(raw_lines) if _matches(ln)]
    if len(hits) < 2:
        return None
    return hits[0]


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
