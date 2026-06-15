"""Stephanus-aligned splitter for the MDZ hOCR of Schleiermacher's *Der Staat*.

The source (``perseus/download_plato_schleiermacher_mdz.py`` → MDZ item
``bsb10237333``) is per-page hOCR concatenated with ``<!-- MDZ_PAGE: N -->``
markers. Each page is single-column. Two signals matter:

* The **running header** (topmost line) carries the book ("SIEBENTES BUCH")
  and the edition page number — dropped (the ``book`` field is derived from
  the Stephanus page via the canonical book boundaries, which is more reliable
  than the OCR'd header).
* The **Stephanus page number** rides the right margin (x > 0.82·width) at the
  end of the body line where that Stephanus page begins — e.g. the cave
  allegory line "...vergleiche dir un- 514" marks the start of Stephanus 514.

We cluster words into lines, repair end-of-line hyphenation, strip the header
+ marginal Stephanus tokens from the prose, and emit one chunk per Stephanus
segment with ``section`` = the bare Stephanus page (e.g. "514").

Robustness: OCR throws the occasional spurious right-margin number (e.g. a
table-of-contents page lists "529" before Book I even starts). We therefore
collect every candidate marker in reading order and keep only those on the
**longest non-decreasing subsequence** — the true Stephanus run is monotonic
327→621, so outliers fall off. Margins are OCR'd on ~half the pages, so a
chunk labelled N spans to the next *captured* page; alignment is page-level
and approximate. Schleiermacher's Einleitung (before Book I) and Anmerkungen
(after the translation) carry no valid markers and are excluded.
"""

from __future__ import annotations

import html as _html
import re
from collections.abc import Iterator
from pathlib import Path

from ..corpus_works import CorpusWork
from ..tei import Chunk
from .split_paragraphic import _emit

_PAGE_RE = re.compile(r"<!-- MDZ_PAGE: (\d+) -->")
_WORD_RE = re.compile(
    r"<span class=['\"]ocrx_word['\"][^>]*\bbbox (\d+) (\d+) (\d+) (\d+)[^>]*>([^<]*)</span>"
)
# Canonical first-Stephanus-page of each Republic book — fixed across all
# editions, so we derive the book from the (reliable) Stephanus number rather
# than the OCR'd "X BUCH" running header (Book I's header, e.g., is often
# missed). Boundaries: I 327, II 357, III 386, IV 419, V 449, VI 484,
# VII 514, VIII 543, IX 571, X 595.
_BOOK_STARTS = [
    (327, 1),
    (357, 2),
    (386, 3),
    (419, 4),
    (449, 5),
    (484, 6),
    (514, 7),
    (543, 8),
    (571, 9),
    (595, 10),
]
_STEPH_MIN, _STEPH_MAX = 327, 621
_RIGHT_MARGIN = 0.82
_LINE_TOL = 20

_Word = tuple[int, int, int, int, str]


def _lines(hocr: str) -> tuple[list[list[_Word]], int]:
    """Cluster a page's words into reading-order lines; return (lines, width)."""
    words: list[_Word] = [
        (int(a), int(b), int(c), int(d), _html.unescape(t).strip())
        for a, b, c, d, t in _WORD_RE.findall(hocr)
    ]
    words = [w for w in words if w[4]]
    if not words:
        return [], 0
    width = max(w[2] for w in words)
    words.sort(key=lambda w: (w[1], w[0]))
    lines: list[list[_Word]] = []
    cur: list[_Word] = []
    last_y: int | None = None
    for w in words:
        if last_y is None or abs(w[1] - last_y) <= _LINE_TOL:
            cur.append(w)
        else:
            lines.append(sorted(cur, key=lambda v: v[0]))
            cur = [w]
        last_y = w[1]
    if cur:
        lines.append(sorted(cur, key=lambda v: v[0]))
    return lines, width


def _book_for(steph: int) -> int:
    """Republic book number for a Stephanus page (canonical boundaries)."""
    book = 1
    for start, n in _BOOK_STARTS:
        if steph >= start:
            book = n
        else:
            break
    return book


def _steph(tok: str) -> int | None:
    if re.fullmatch(r"\d{2,3}", tok):
        n = int(tok)
        if _STEPH_MIN <= n <= _STEPH_MAX:
            return n
    return None


def _join_hyphenation(parts: list[str]) -> str:
    out = re.sub(r"(\w)-\s+(\w)", r"\1\2", " ".join(parts))
    return re.sub(r"\s+", " ", out).strip()


def _keep_monotonic(values: list[int]) -> set[int]:
    """Indices of `values` lying on a longest non-decreasing subsequence."""
    n = len(values)
    if not n:
        return set()
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if values[j] <= values[i] and best[j] + 1 > best[i]:
                best[i] = best[j] + 1
                prev[i] = j
    end = max(range(n), key=lambda i: best[i])
    keep: set[int] = set()
    while end != -1:
        keep.add(end)
        end = prev[end]
    return keep


def split_stephanus_de(hocr: str, work: CorpusWork, path: Path) -> Iterator[Chunk]:
    parts = _PAGE_RE.split(hocr)  # ['', '1', page1, '2', page2, ...]

    # Pass 1 — flatten to an event stream in reading order.
    # Events: ("steph", value) | ("prose", text). The book comes from the
    # Stephanus page (canonical), not the OCR header.
    events: list[tuple[str, object]] = []
    in_notes = False
    for i in range(1, len(parts), 2):
        lines, width = _lines(parts[i + 1])
        if not lines or width == 0:
            continue
        header = " ".join(t for *_, t in lines[0]).upper()
        if "ANMERKUNGEN" in header:
            in_notes = True
        if in_notes:
            continue
        for line in lines[1:]:
            marker: int | None = None
            prose: list[str] = []
            for x0, _y0, _x1, _y1, t in line:
                n = _steph(t)
                if n is not None and x0 / width > _RIGHT_MARGIN:
                    marker = n
                    continue
                prose.append(t)
            if prose:
                events.append(("prose", " ".join(prose)))
            if marker is not None:
                events.append(("steph", marker))

    # Filter spurious markers to the longest non-decreasing run.
    steph_vals = [v for k, v in events if k == "steph"]
    keep = _keep_monotonic(steph_vals)  # type: ignore[arg-type]

    # Pass 2 — emit one chunk per kept Stephanus segment.
    cur_steph: int | None = None
    buf: list[str] = []
    seen = 0

    def flush() -> Chunk | None:
        if cur_steph is None or not buf:
            return None
        label = f"Buch {_book_for(cur_steph)}"
        return _emit(
            work, path, section=str(cur_steph), text=_join_hyphenation(buf), book_label=label
        )

    for kind, payload in events:
        if kind == "prose":
            buf.append(payload)  # type: ignore[arg-type]
        else:  # steph
            on_run = seen in keep
            seen += 1
            if not on_run:
                continue
            chunk = flush()
            if chunk is not None:
                yield chunk
            buf = []
            cur_steph = payload  # type: ignore[assignment]
    chunk = flush()
    if chunk is not None:
        yield chunk
