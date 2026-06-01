#!/usr/bin/env python3
"""Download three major Augustine works in Latin from la.wikisource.

Augustine wrote in Latin; Wikisource Latin carries clean Maurist-edition
transcriptions of:

  • Confessiones (13 Libri, ~390 paragraphs). Canonical citation
    `Conf. <Book>.<Chapter>.<Paragraph>` (e.g. Conf. VIII.7.16). The
    Wikisource markup uses inline `<book>.<chap>.<para>` standalone
    headings (e.g. `8.7.16`) before each paragraph body, so each
    paragraph is recoverable as one chunk.
  • De civitate Dei (22 Libri + Prologus). Canonical citation
    `Civ. Dei <Book>.<Chapter>`. Wikisource only carries chapter-level
    structure (`[I]`, `[II]`, ... inline at the start of each chapter
    paragraph), so the chapter is our granularity ceiling here.
  • De Trinitate (Prologus + 15 Libri). Canonical citation
    `Trin. <Book>.<Chapter>.<Paragraph>` (e.g. Trin. IX.4.7). The
    Wikisource markup uses MediaWiki `== <RomanChap> <ArabicPara> ==`
    H2 headings at chapter starts and `== <ArabicPara> ==` for
    intermediate paragraphs within a chapter. Each paragraph → one
    chunk. Some chapters lack the paragraph number in their heading
    (`== VIII ==`) — those are filled in as (last_para + 1).

Each REST fetch uses the same retry-with-backoff helper shape as
`download_spinoza.py`; per-book content goes through the same stdlib
`HTMLParser`-based paragraph extractor (`_ParagraphExtractor`) we
already use for Spinoza/Descartes. Markers emitted to the raw .txt
files (one per work):

    [CONF.<b>.<c>.<p>]   Confessiones, Liber `b`, Caput `c`, ¶ `p`
    [CIV.<b>.<c>]        De civitate Dei, Liber `b`, Caput `c`
    [TRIN.<b>.<c>.<p>]   De Trinitate, Liber `b`, Caput `c`, ¶ `p`

Output:

    data/augustine/raw_la/confessiones.txt
    data/augustine/raw_la/civitate_dei.txt
    data/augustine/raw_la/trinitate.txt

Run:

    uv run python perseus/download_augustine.py
    uv run python perseus/download_augustine.py --only confessiones
"""

from __future__ import annotations

import argparse
import re
import time
import urllib.error
from html.parser import HTMLParser
from pathlib import Path

from _download import fetch_bytes_with_retry

USER_AGENT = "minerva-research/1.0 (local research; bulk fetch with delays)"

_REST = "https://la.wikisource.org/api/rest_v1/page/html"

# Confessions: 13 Books on Wikisource. The slugs use Latin ordinal
# names (Liber_Primus … Liber_Tertius_Decimus), NOT Roman numerals,
# which is idiomatic for Wikisource's Confessiones organization. Each
# tuple is (book_number, slug-after-`Confessiones/`).
_CONF_SUBPAGES: tuple[tuple[int, str], ...] = (
    (1, "Liber_Primus"),
    (2, "Liber_Secundus"),
    (3, "Liber_Tertius"),
    (4, "Liber_Quartus"),
    (5, "Liber_Quintus"),
    (6, "Liber_Sextus"),
    (7, "Liber_Septimus"),
    (8, "Liber_Octavus"),
    (9, "Liber_Nonus"),
    (10, "Liber_Decimus"),
    (11, "Liber_Undecimus"),
    (12, "Liber_Duodecimus"),
    (13, "Liber_Tertius_Decimus"),
)

# De civitate Dei: 22 Books + Prologus. Slugs are Roman numerals
# (Liber_I … Liber_XXII). The Prologus is short — we don't currently
# emit chunks for it; the first chunk is Civ. Dei I.1.
_CIV_SUBPAGES: tuple[tuple[int, str], ...] = tuple(
    (i, f"Liber_{r}")
    for i, r in (
        (1, "I"), (2, "II"), (3, "III"), (4, "IV"), (5, "V"),
        (6, "VI"), (7, "VII"), (8, "VIII"), (9, "IX"), (10, "X"),
        (11, "XI"), (12, "XII"), (13, "XIII"), (14, "XIV"), (15, "XV"),
        (16, "XVI"), (17, "XVII"), (18, "XVIII"), (19, "XIX"), (20, "XX"),
        (21, "XXI"), (22, "XXII"),
    )
)

# De Trinitate: 15 Books. Slugs Roman, under
# `De_trinitate_(Aurelius_Augustinus)/Liber_<R>`. The lowercase `t` in
# `trinitate` (and the disambiguator suffix in parens) are exactly
# how the Wikisource canonical title is spelled — the disambiguator
# distinguishes Augustine's De Trinitate from Boethius's and Hilary's.
_TRIN_SUBPAGES: tuple[tuple[int, str], ...] = tuple(
    (i, f"Liber_{r}")
    for i, r in (
        (1, "I"), (2, "II"), (3, "III"), (4, "IV"), (5, "V"),
        (6, "VI"), (7, "VII"), (8, "VIII"), (9, "IX"), (10, "X"),
        (11, "XI"), (12, "XII"), (13, "XIII"), (14, "XIV"), (15, "XV"),
    )
)


# The Wikimedia REST API will sometimes return HTTP 200 with a
# plain-text body that begins with "You are making too many requests"
# instead of returning a real 429. We have to detect that in the
# response body and retry — the HTTPError-based path won't fire. Empty
# or extremely short bodies are also treated as transient.
_RATE_LIMIT_MARKER = b"You are making too many requests"
_MIN_VALID_BYTES = 1024


_HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _fetch(url: str, *, timeout: float = 60, retries: int = 8) -> bytes:
    """Retry-with-backoff fetch — delegates HTTP to ``_download``, then
    detects Wikimedia's plaintext-200 rate-limit bodies."""

    for attempt in range(retries):
        try:
            body = fetch_bytes_with_retry(
                url,
                timeout=timeout,
                retries=1,
                user_agent=USER_AGENT,
                extra_headers=_HTML_HEADERS,
                backoff_initial=5.0,
                backoff_max=120.0,
            )
        except urllib.error.HTTPError as e:
            if e.code in (408, 425, 429, 500, 502, 503, 504) and attempt + 1 < retries:
                wait = min(120.0, 5.0 * (2**attempt))
                print(f"  {e.code} {e.reason}; retry in {wait:.0f}s ({attempt + 1}/{retries})")
                time.sleep(wait)
                continue
            raise
        except urllib.error.URLError as e:
            if attempt + 1 < retries:
                wait = min(120.0, 5.0 * (2**attempt))
                print(f"  URL error {e.reason!r}; retry in {wait:.0f}s ({attempt + 1}/{retries})")
                time.sleep(wait)
                continue
            raise
        if len(body) < _MIN_VALID_BYTES and _RATE_LIMIT_MARKER in body:
            if attempt + 1 < retries:
                wait = min(120.0, 5.0 * (2**attempt))
                print(
                    f"  rate-limit plaintext body ({len(body)} bytes); "
                    f"retry in {wait:.0f}s ({attempt + 1}/{retries})"
                )
                time.sleep(wait)
                continue
            raise RuntimeError(f"rate-limited after {retries} retries: {url}")
        return body
    raise RuntimeError(f"download failed after {retries} retries: {url}")


# Polite inter-request delay. The first run blew through 50 GETs in a
# few seconds and tripped Wikimedia's rate limit; a small fixed delay
# between requests keeps us well under the documented 200 req/sec
# limit and avoids the per-IP rolling-window throttle that returned
# 200-with-rate-limit-body responses.
_INTER_REQUEST_DELAY = 1.0


# ----- HTML → paragraph stream -----
#
# Identical to the Spinoza/Descartes extractor: each `<p>` (or `<li>`
# / `<div>`) close flushes a paragraph; `<script>` / `<style>` /
# `<table>` / `<sup>` are dropped. Wikisource Latin's body content
# arrives as a series of `<p>` blocks with standalone heading paras
# for section markers.
_SKIP_TAGS = frozenset({"script", "style", "table", "sup", "noscript"})
_BREAK_END_TAGS = frozenset({"p", "li", "div"})


class _ParagraphExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._buf: list[str] = []
        self.paragraphs: list[str] = []

    def _flush(self) -> None:
        text = " ".join("".join(self._buf).split()).strip()
        if text:
            self.paragraphs.append(text)
        self._buf.clear()

    def handle_starttag(self, tag: str, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag in _BREAK_END_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if tag in _BREAK_END_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._buf.append(data)

    def close(self) -> None:  # type: ignore[override]
        super().close()
        self._flush()


def _extract_paragraphs(html: bytes) -> list[str]:
    p = _ParagraphExtractor()
    p.feed(html.decode("utf-8"))
    p.close()
    return p.paragraphs


# ----- numeric helpers -----

_ROMAN_DIGIT = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(s: str) -> int | None:
    """Subtractive-rule Roman → int. Returns None on non-Roman input.
    Used in chapter-heading scans where we already know the surrounding
    context is numeric; never trusted blind."""

    if not s:
        return None
    s = s.upper()
    if any(ch not in _ROMAN_DIGIT for ch in s):
        return None
    total = 0
    prev = 0
    for ch in reversed(s):
        v = _ROMAN_DIGIT[ch]
        if v < prev:
            total -= v
        else:
            total += v
        prev = v
    return total


# ----- Confessions walker -----
#
# Each paragraph chunk begins with a standalone `<book>.<chap>.<para>`
# heading (e.g. `8.7.16`), then a body paragraph (or sometimes
# several wrapped paragraphs that we glue together until the next
# heading). The book number from the heading must match the book we
# requested — books occasionally include a Bible-verse-style citation
# `(8.7)` in the body, which we don't want to misparse as a heading.
# The full B.C.P regex anchored to start-of-paragraph + nothing-else
# rules those out.
_CONF_HEADING = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _extract_confessions(html: bytes, book_n: int) -> list[tuple[str, str]]:
    """Walk one Confessions Liber's paragraph stream; emit one
    `(marker, body)` per paragraph chunk. Marker is `[CONF.<b>.<c>.<p>]`."""

    paragraphs = _extract_paragraphs(html)
    out: list[tuple[str, str]] = []

    current_marker: str | None = None
    current_body: list[str] = []

    def flush() -> None:
        nonlocal current_marker, current_body
        if current_marker is not None:
            body = " ".join(current_body).strip()
            if body:
                out.append((current_marker, body))
        current_marker = None
        current_body = []

    for raw in paragraphs:
        p = raw.strip()
        if not p:
            continue
        m = _CONF_HEADING.match(p)
        if m:
            b, c, par = int(m.group(1)), int(m.group(2)), int(m.group(3))
            # Defensive: only honour headings whose book number matches
            # the Liber we're parsing. Wikisource is consistent here,
            # but a stray Bible reference in the body could otherwise
            # masquerade as a heading on a future edition revision.
            if b != book_n:
                # Treat as body content; keep accumulating.
                if current_marker is not None:
                    current_body.append(p)
                continue
            flush()
            current_marker = f"[CONF.{b}.{c}.{par}]"
            current_body = []
            continue
        if current_marker is not None:
            current_body.append(p)

    flush()
    return out


# ----- De civitate Dei walker -----
#
# Each chapter begins with an inline `[<Roman>]` marker at the start
# of the chapter's first paragraph. Body paragraphs that continue a
# chapter have no marker. We detect the marker by anchoring to the
# start of a paragraph string after whitespace trim. Chapter numbers
# in book XIX run I–XXVIII; longest book is II (29 chapters); we
# accept up to LX to be safe.
_CIV_CHAPTER_RE = re.compile(r"^\[\s*([IVXLC]+)\s*\]\s*(.*)$", re.DOTALL)


def _extract_civ(html: bytes, book_n: int) -> list[tuple[str, str]]:
    """Walk one Civ. Dei Liber. Emit one `(marker, body)` per chapter."""

    paragraphs = _extract_paragraphs(html)
    out: list[tuple[str, str]] = []

    current_marker: str | None = None
    current_body: list[str] = []

    def flush() -> None:
        nonlocal current_marker, current_body
        if current_marker is not None:
            body = " ".join(current_body).strip()
            if body:
                out.append((current_marker, body))
        current_marker = None
        current_body = []

    for raw in paragraphs:
        p = raw.strip()
        if not p:
            continue
        m = _CIV_CHAPTER_RE.match(p)
        if m:
            chap = _roman_to_int(m.group(1))
            rest = m.group(2).strip()
            if chap is None:
                if current_marker is not None:
                    current_body.append(p)
                continue
            flush()
            current_marker = f"[CIV.{book_n}.{chap}]"
            current_body = [rest] if rest else []
            continue
        if current_marker is not None:
            current_body.append(p)

    flush()
    return out


# ----- De Trinitate walker -----
#
# Wikisource carries the work in two distinct markup styles depending
# on which Liber the editor used:
#
#   Style A (Libri I–VIII): inline bracketed markers at the start of
#   a paragraph — `[I 1] Lecturus haec quae…`, `[2] Vt ergo…`, etc.
#   The first paragraph of a chapter carries `[<Roman> <Arabic>]`;
#   subsequent paragraphs in the same chapter carry `[<Arabic>]`.
#   A bare `[<Roman>]` (no paragraph number) is also possible — the
#   downloader infers the paragraph as `last_para + 1`.
#
#   Style B (Libri IX–XV): standalone H2 headings — `I 1`, `II 4`,
#   `5`, etc., emitted as their own paragraph by the extractor.
#
# We try Style A first (because Style A's regex is anchored to `^[`
# and can't false-positive on Style B headings), then fall back to
# Style B. Both populate the same chapter/paragraph state machine.
_TRIN_BRACKET_CHAP_PARA = re.compile(r"^\[\s*([IVXLC]+)\s+(\d+)\s*\]\s*(.*)$", re.DOTALL)
_TRIN_BRACKET_PARA = re.compile(r"^\[\s*(\d+)\s*\]\s*(.*)$", re.DOTALL)
_TRIN_BRACKET_CHAP = re.compile(r"^\[\s*([IVXLC]+)\s*\]\s*(.*)$", re.DOTALL)
_TRIN_CHAPTER_PARA = re.compile(r"^([IVXLC]+)\s+(\d+)$")
_TRIN_CHAPTER_ONLY = re.compile(r"^([IVXLC]+)$")
_TRIN_PARA_ONLY = re.compile(r"^(\d+)$")


def _extract_trin(html: bytes, book_n: int) -> list[tuple[str, str]]:
    """Walk one De Trinitate Liber. Emit one `(marker, body)` per
    paragraph chunk."""

    paragraphs = _extract_paragraphs(html)
    out: list[tuple[str, str]] = []

    current_chapter: int | None = None
    last_para: int = 0
    current_marker: str | None = None
    current_body: list[str] = []

    def flush() -> None:
        nonlocal current_marker, current_body
        if current_marker is not None:
            body = " ".join(current_body).strip()
            if body:
                out.append((current_marker, body))
        current_marker = None
        current_body = []

    for raw in paragraphs:
        p = raw.strip()
        if not p:
            continue

        # ----- Style A: inline bracketed markers (Libri I–VIII) -----

        m = _TRIN_BRACKET_CHAP_PARA.match(p)
        if m:
            chap = _roman_to_int(m.group(1))
            par = int(m.group(2))
            rest = m.group(3).strip()
            if chap is None:
                if current_marker is not None:
                    current_body.append(p)
                continue
            flush()
            current_chapter = chap
            last_para = par
            current_marker = f"[TRIN.{book_n}.{chap}.{par}]"
            current_body = [rest] if rest else []
            continue

        m = _TRIN_BRACKET_PARA.match(p)
        if m and current_chapter is not None:
            par = int(m.group(1))
            rest = m.group(2).strip()
            if 1 <= par <= 200 and par > last_para:
                flush()
                last_para = par
                current_marker = f"[TRIN.{book_n}.{current_chapter}.{par}]"
                current_body = [rest] if rest else []
                continue

        m = _TRIN_BRACKET_CHAP.match(p)
        if m:
            # Bracketed bare chapter — accept only if it advances the
            # chapter counter by exactly one, same guard as Style B.
            chap = _roman_to_int(m.group(1))
            rest = m.group(2).strip()
            if chap is not None and 1 <= chap <= 60 and (
                (current_chapter is None and chap == 1)
                or (current_chapter is not None and chap == current_chapter + 1)
            ):
                flush()
                current_chapter = chap
                last_para += 1
                current_marker = f"[TRIN.{book_n}.{chap}.{last_para}]"
                current_body = [rest] if rest else []
                continue

        # ----- Style B: standalone-heading paragraphs (Libri IX–XV) -----

        m = _TRIN_CHAPTER_PARA.match(p)
        if m:
            chap = _roman_to_int(m.group(1))
            par = int(m.group(2))
            if chap is None:
                if current_marker is not None:
                    current_body.append(p)
                continue
            flush()
            current_chapter = chap
            last_para = par
            current_marker = f"[TRIN.{book_n}.{chap}.{par}]"
            current_body = []
            continue

        m = _TRIN_CHAPTER_ONLY.match(p)
        if m:
            chap = _roman_to_int(m.group(1))
            # Only treat a bare Roman numeral as a chapter heading if
            # the value is plausibly in book-chapter range. Without
            # this guard a stray `I` or `V` mid-body would trigger.
            # De Trin. book chapter counts top out around 19 (Book
            # XV); we cap at LX which is conservative.
            if chap is None or not (1 <= chap <= 60):
                if current_marker is not None:
                    current_body.append(p)
                continue
            # Heuristic: only treat as a chapter heading if it's
            # exactly one more than the current chapter (or current
            # chapter is None and this is `I`). Otherwise it's
            # ambiguous body content.
            if (current_chapter is None and chap == 1) or (
                current_chapter is not None and chap == current_chapter + 1
            ):
                flush()
                current_chapter = chap
                last_para += 1
                current_marker = f"[TRIN.{book_n}.{chap}.{last_para}]"
                current_body = []
                continue
            if current_marker is not None:
                current_body.append(p)
            continue

        m = _TRIN_PARA_ONLY.match(p)
        if m:
            par = int(m.group(1))
            # Reject implausibly large paragraph numbers (defensive
            # against year-of-composition headers like `397-401` or
            # stray `<small>` digits — we already filter most via
            # the extractor, but be safe). Largest De Trin paragraph
            # count is around 50 per book.
            if 1 <= par <= 200 and current_chapter is not None and par > last_para:
                flush()
                last_para = par
                current_marker = f"[TRIN.{book_n}.{current_chapter}.{par}]"
                current_body = []
                continue
            if current_marker is not None:
                current_body.append(p)
            continue

        # Plain body content.
        if current_marker is not None:
            current_body.append(p)

    flush()
    return out


# ----- Output formatter (shared with Spinoza) -----


def _render(chunks: list[tuple[str, str]]) -> str:
    """Same canonical marker-then-blank-then-body shape used by all
    raw_la files in this corpus. The splitter is anchored to
    `^[MARKER]$`, so each marker MUST sit on its own line."""

    pieces: list[str] = []
    for marker, body in chunks:
        pieces.append(marker)
        pieces.append("")
        pieces.append(body)
        pieces.append("")
    return "\n".join(pieces).strip() + "\n"


# ----- per-work fetch entry points -----


def fetch_confessions(*, dest_root: Path) -> Path:
    all_chunks: list[tuple[str, str]] = []
    for book_n, slug in _CONF_SUBPAGES:
        url = f"{_REST}/Confessiones%2F{slug}"
        print(f"GET {url}")
        html = _fetch(url)
        time.sleep(_INTER_REQUEST_DELAY)
        chunks = _extract_confessions(html, book_n)
        print(f"  Liber {book_n}: {len(chunks)} chunks")
        all_chunks.extend(chunks)
    rendered = _render(all_chunks)
    dest_dir = dest_root / "augustine" / "raw_la"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "confessiones.txt"
    dest.write_text(rendered, encoding="utf-8")
    print(f"  → {dest} ({len(rendered):,} chars · {len(all_chunks)} chunks)")
    return dest


def fetch_civ(*, dest_root: Path) -> Path:
    all_chunks: list[tuple[str, str]] = []
    for book_n, slug in _CIV_SUBPAGES:
        url = f"{_REST}/De_civitate_Dei%2F{slug}"
        print(f"GET {url}")
        html = _fetch(url)
        time.sleep(_INTER_REQUEST_DELAY)
        chunks = _extract_civ(html, book_n)
        print(f"  Liber {book_n}: {len(chunks)} chunks")
        all_chunks.extend(chunks)
    rendered = _render(all_chunks)
    dest_dir = dest_root / "augustine" / "raw_la"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "civitate_dei.txt"
    dest.write_text(rendered, encoding="utf-8")
    print(f"  → {dest} ({len(rendered):,} chars · {len(all_chunks)} chunks)")
    return dest


def fetch_trinitate(*, dest_root: Path) -> Path:
    all_chunks: list[tuple[str, str]] = []
    for book_n, slug in _TRIN_SUBPAGES:
        # The disambiguator suffix `(Aurelius_Augustinus)` distinguishes
        # Augustine's De Trin. from Boethius's. URL-encoded parens.
        url = f"{_REST}/De_trinitate_%28Aurelius_Augustinus%29%2F{slug}"
        print(f"GET {url}")
        html = _fetch(url)
        time.sleep(_INTER_REQUEST_DELAY)
        chunks = _extract_trin(html, book_n)
        print(f"  Liber {book_n}: {len(chunks)} chunks")
        all_chunks.extend(chunks)
    rendered = _render(all_chunks)
    dest_dir = dest_root / "augustine" / "raw_la"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "trinitate.txt"
    dest.write_text(rendered, encoding="utf-8")
    print(f"  → {dest} ({len(rendered):,} chars · {len(all_chunks)} chunks)")
    return dest


_WORKS = {
    "confessions": fetch_confessions,
    "civitate": fetch_civ,
    "trinitate": fetch_trinitate,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
        help="Top of the data tree; files land in <root>/augustine/raw_la/.",
    )
    parser.add_argument(
        "--only",
        choices=sorted(_WORKS),
        action="append",
        help=(
            "Fetch only this work (repeatable). Defaults to all three. "
            "Useful for incremental testing without re-fetching every Liber."
        ),
    )
    args = parser.parse_args()
    targets = args.only or sorted(_WORKS)
    for name in targets:
        _WORKS[name](dest_root=args.data_root)


if __name__ == "__main__":
    main()
