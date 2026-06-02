#!/usr/bin/env python3
"""Download Spinoza's *Tractatus Theologico-Politicus* (TTP, 1670)
from spinozaetnous.org.

The TTP is Spinoza's anonymously-published 1670 critique of biblical
authority and miracle. It is the most biblically-engaged work in
Spinoza's canon (~30% biblical exegesis) and the foundational text
of critical-historical biblical interpretation. Without it the
minerva Spinoza corpus is the pure-metaphysics Spinoza, not the
religion-critic Spinoza.

**Source:** ``spinozaetnous.org`` (a Mediawiki site that ships clean
Latin TTP one chapter per page). 21 pages total: ``Praefatio`` plus
``Caput_I`` through ``Caput_XX``. Each page wraps the prose in
``<div class="text">…</div>``; Spinoza's own appended Adnotationes
appear inline as ``<ref>…</ref>`` blocks.

**Cite-shape convention** for the downstream
:mod:`minerva.corpus.split_spinoza` splitter:

    [TTP.<c>.<nnn>]   Caput `c` (0 = Praefatio), paragraph `nnn`

The paragraph number is sequential within the chapter (matches the
source's blank-line splitting). It does **not** align with the
Bruder/Gebhardt numbering used in academic citation, because
spinozaetnous.org doesn't carry those markers. Adding a Bruder-aligned
locator would require re-keying against a different scan (e.g. the
1843 Bruder edition at archive.org); deferred.

**Adnotationes**: Spinoza's own end-of-book annotations appear inline
as MediaWiki ``<ref>…</ref>`` blocks. We **strip** them for chunk
emission — they pollute retrieval context (heavy Hebrew transliteration,
rabbinic-commentary tone, distinct register from the main prose).
A future pass could ingest them as separate ``[TTP.<c>.Adn.<n>]``
chunks if the user wants them surfaced; today they're discarded.

Hebrew script appears as the placeholder ``[heb.]`` (the source uses
images for the actual Hebrew). Preserved verbatim — the placeholder
is harmless and any downstream Hebrew rule would have to fall back
to fragments anyway.

Output: ``data/spinoza/raw_la/ttp.txt``.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from _download import make_fetcher

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "data" / "spinoza" / "raw_la"


_BASE = "http://spinozaetnous.org/wiki"


def _caput_url(name: str) -> str:
    return f"{_BASE}/Tractatus_theologico-politicus/{name}?action=raw"


# Roman-numeral chapters in source order. ``Praefatio`` ingests as
# caput 0 so the marker shape stays uniform with the other 20.
_PAGES: tuple[tuple[int, str], ...] = (
    (0, "Praefatio"),
    *((i, f"Caput_{r}") for i, r in enumerate(
        ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
         "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"),
        start=1,
    )),
)


_fetch = make_fetcher()

def clean_wikitext(raw: str) -> str:
    """Strip refs, templates, wiki tags; keep prose + paragraph breaks."""

    text = _RE_REF.sub("", raw)
    # Templates can nest one level (e.g. ``{{x{{y}}z}}``) — iterate.
    for _ in range(5):
        new = _RE_TEMPLATE.sub("", text)
        if new == text:
            break
        text = new
    text = _RE_HTML_TAG.sub("", text)
    text = _RE_WIKILINK.sub(r"\1", text)
    text = _RE_EMPHASIS.sub(r"\1", text)
    text = _RE_TRAILING_WS.sub("\n", text)
    text = _RE_BLANK.sub("\n\n", text)
    return text.strip()


_RE_ROMAN_SECTION = re.compile(
    r"(?<=\n)(?=(?:I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV|XV)\.\s+[A-Z])"
)
_RE_SENTENCE = re.compile(r"(?<=[\.;])\s+(?=[A-Z])")

# Hard ceiling for any one chunk; keeps embeddings well-scoped and
# prevents single-paragraph chapters (Caput VI, VIII, XI etc. ship as
# one block in the wikitext) from becoming 30 KB megachunks that
# dominate the cosine sweep.
_MAX_CHUNK_CHARS = 3000


def _split_long(seg: str) -> list[str]:
    """Sub-split a too-long segment at Roman-numeral section markers,
    then at sentence boundaries. Best-effort: prefers semantic breaks
    but falls back to char-bucket splits if the prose is one long
    sentence (rare in Spinoza)."""

    if len(seg) <= _MAX_CHUNK_CHARS:
        return [seg]
    # First try Spinoza's own enumerators ("I. ... II. ... III. ...").
    parts = _RE_ROMAN_SECTION.split(seg)
    if any(len(p) <= _MAX_CHUNK_CHARS for p in parts) and len(parts) > 1:
        out: list[str] = []
        for p in parts:
            p = p.strip()
            if len(p) > _MAX_CHUNK_CHARS:
                out.extend(_split_long(p))
            elif len(p) >= 40:
                out.append(p)
        return out
    # Fallback: sentence-boundary splits, greedily packed up to the cap.
    buf: list[str] = []
    cur = ""
    for sent in _RE_SENTENCE.split(seg):
        if not cur:
            cur = sent
            continue
        if len(cur) + 1 + len(sent) <= _MAX_CHUNK_CHARS:
            cur = f"{cur} {sent}"
        else:
            buf.append(cur)
            cur = sent
    if cur:
        buf.append(cur)
    return buf


def split_paragraphs(text: str) -> list[str]:
    """Blank-line split first, with Roman-numeral + sentence-boundary
    sub-splits for chapters whose wikitext lacks blank lines. Drops
    paragraphs shorter than 40 chars (chapter headings, section breaks,
    stray fragments)."""

    out: list[str] = []
    for para in re.split(r"\n[ \t]*\n", text):
        s = para.strip()
        if len(s) < 40:
            continue
        # Collapse internal newlines to single spaces — paragraphs are
        # often wrapped at column 80 in wikitext. Done BEFORE the
        # long-chunk subdivision so the Roman-numeral / sentence regexes
        # see a uniform token shape.
        s = re.sub(r"\s+", " ", s)
        for piece in _split_long(s):
            if len(piece) >= 40:
                out.append(piece)
    return out


def _emit_chapter(c: int, page_name: str, paragraphs: list[str]) -> str:
    """Render one chapter as the marker stream split_spinoza consumes.

    Praefatio = caput 0. Other capita preserve their Roman ordinal."""

    lines: list[str] = []
    for idx, para in enumerate(paragraphs, start=1):
        marker = f"[TTP.{c}.{idx:03d}]"
        lines.append(marker)
        lines.append("")
        lines.append(para)
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Output directory (writes ttp.txt within).",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds to wait between page fetches (be polite).",
    )
    ap.add_argument("--skip-existing", action="store_true")
    args = ap.parse_args()

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "ttp.txt"

    if args.skip_existing and dest.is_file() and dest.stat().st_size > 0:
        print(f"skip (already exists): {dest}")
        return

    print("=== Spinoza Tractatus Theologico-Politicus (Latin) ===")
    pieces: list[str] = []
    total_paragraphs = 0
    for c, page_name in _PAGES:
        url = _caput_url(page_name)
        print(f"GET {page_name} (caput {c}) ... ", end="", flush=True)
        try:
            raw_bytes = _fetch(url)
        except urllib.error.HTTPError as e:
            print(f"\n  FAILED: HTTP {e.code} {e.reason}", file=sys.stderr)
            sys.exit(1)
        raw = raw_bytes.decode("utf-8", errors="replace")
        cleaned = clean_wikitext(raw)
        paragraphs = split_paragraphs(cleaned)
        total_paragraphs += len(paragraphs)
        print(f"{len(paragraphs)} paragraphs")
        pieces.append(_emit_chapter(c, page_name, paragraphs))
        if args.delay > 0 and (c, page_name) != _PAGES[-1]:
            time.sleep(args.delay)

    dest.write_text("\n".join(pieces) + "\n", encoding="utf-8")
    size = dest.stat().st_size
    print(
        f"\n  wrote {dest.resolve()} ({size:,} bytes; "
        f"{total_paragraphs:,} paragraphs across {len(_PAGES)} chapters)"
    )


if __name__ == "__main__":
    main()
