#!/usr/bin/env python3
"""
Download Aristotle English translations from the Internet Classics
Archive (classics.mit.edu).

Source: https://classics.mit.edu/Aristotle/
License: Translations are public domain (Edghill, Ross, Smith, Stocks,
Beare, Thompson, Forster, Peck, Jowett — turn-of-the-20th-century).
The ICA's web layer (page chrome, JavaScript) is © Daniel C. Stevenson;
we ingest only the prose, not the site furniture.

Why a separate downloader: Perseus's TEI bundle covers only 9
Aristotle works in English; ICA carries roughly 22 more (Categories,
the Organon, Physics, On the Soul, the Parva Naturalia, biological
works, …). First1KGreek fills the Greek side for the same set; this
script fills the English.

Output layout
-------------
``perseus/raw_text_aristotle_ica/<canonical_title>/eng.txt``

Two source shapes on ICA, handled here so the parser doesn't need to
distinguish them:

1. Long works have a ``.mb.txt`` plain-text mirror with SECTION /
   BOOK / Part headers and blank-line-separated paragraphs. We grab
   that file verbatim.
2. Short works (most of the Parva Naturalia: On Memory, On Dreams, On
   Sleep, etc.) have NO text mirror — only the per-work HTML page.
   For these we fetch the HTML, strip the ICA page chrome, normalize
   the prose into the same SECTION/Part shape, and write the result
   as ``eng.txt`` so the parser sees a uniform input.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from _download import fetch_bytes_with_retry

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from minerva.authors.aristotle_works import works_with_ica  # noqa: E402

BASE = "https://classics.mit.edu/Aristotle"
USER_AGENT = (
    "perseus-corpus-fetch/1.0 (+personal research; respects ICA terms; "
    "contact: local user)"
)


_HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def _fetch(url: str, *, timeout: float = 60, retries: int = 8) -> bytes:
    return fetch_bytes_with_retry(
        url,
        timeout=timeout,
        retries=retries,
        user_agent=USER_AGENT,
        extra_headers=_HTML_HEADERS,
        backoff_initial=5.0,
        backoff_max=120.0,
    )

def _slug_for(title: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in title).strip("_")


# ── HTML → text-mirror fallback ─────────────────────────────────────
# Used when ICA doesn't carry a `.mb.txt` for a work (most short
# Parva Naturalia). The single-page HTML has this shape:
#   <BLOCKQUOTE>
#     ... <A NAME="..."> anchors, <BR> line-breaks ...
#     <B>Part 1</B>
#       prose with anchors and <BR><BR> paragraph splits
#     <B>Part 2</B>
#       ...
#   </BLOCKQUOTE>
# We extract the prose, normalize anchors to whitespace, split on
# <BR><BR>, and emit the same SECTION 1 / Part N shape the .mb.txt
# files use.

_BLOCKQUOTE_RE = re.compile(r"<BLOCKQUOTE>(.*?)</BLOCKQUOTE>", re.IGNORECASE | re.DOTALL)
_PART_RE       = re.compile(r"<B>\s*Part\s+(\d+)\s*</B>", re.IGNORECASE)
_TRANSLATOR_RE = re.compile(r"Translated by\s+([^<]+)")
_ANCHOR_RE     = re.compile(r"<A\s+NAME=\"[^\"]*\"[^>]*></A>", re.IGNORECASE)
_TAG_RE        = re.compile(r"<[^>]+>")
_HTML_ENTITY   = re.compile(r"&[a-zA-Z]+;|&#\d+;")


def _html_entity(m: re.Match[str]) -> str:
    import html as _h
    return _h.unescape(m.group(0))


def _html_to_text_mirror(html: str, canonical_title: str) -> str:
    """Convert one ICA per-work HTML page into ``.mb.txt``-shaped text.

    Returns a string with the standard header line "Translated by X",
    a dividers row, then ``SECTION 1`` followed by ``Part N`` headers
    and paragraph-by-paragraph prose. Empty when no recognizable
    content is found — caller decides whether to skip or persist.
    """

    m = _BLOCKQUOTE_RE.search(html)
    if m is None:
        return ""
    body = m.group(1)
    translator = ""
    tm = _TRANSLATOR_RE.search(body)
    if tm:
        translator = tm.group(1).strip()

    # Drop everything BEFORE the first Part marker — that region is
    # ICA page-chrome ("Commentary:", "Download:", duplicated title
    # block, table-of-contents link) and would otherwise leak into
    # the SECTION 1 body and pollute term-glossary chunks.
    first_part = _PART_RE.search(body)
    if first_part is not None:
        body = body[first_part.start():]

    # Replace Part markers with synthetic line headers BEFORE stripping
    # other tags, so the boundary survives the tag-strip pass.
    body = _PART_RE.sub(lambda mm: f"\n\nPART_MARKER_{mm.group(1)}\n\n", body)

    # Anchors leave behind line-position markers we don't want. Drop
    # the empty anchor tags entirely.
    body = _ANCHOR_RE.sub("", body)
    # <BR><BR> separates paragraphs. Promote to a double newline.
    body = re.sub(r"<BR>\s*<BR>", "\n\n", body, flags=re.IGNORECASE)
    # Single <BR> is a soft line break inside a paragraph; normalize
    # to a single space so the join step below doesn't introduce
    # paragraph splits.
    body = re.sub(r"<BR>", " ", body, flags=re.IGNORECASE)
    # Remove everything else that looks like a tag.
    body = _TAG_RE.sub("", body)
    body = _HTML_ENTITY.sub(_html_entity, body)

    # Now glue back together with proper SECTION/Part markers.
    parts: list[str] = []
    parts.append("Provided by The Internet Classics Archive (HTML-derived).")
    parts.append(f"\n{canonical_title}\nBy Aristotle\n")
    if translator:
        parts.append(f"\nTranslated by {translator}\n")
    parts.append("\n" + "-" * 70 + "\n")
    parts.append("SECTION 1\n")

    # Replace PART_MARKER_N with "Part N", then split on those markers
    # to ensure each Part's prose is a separate region we can clean
    # paragraph-by-paragraph.
    body = re.sub(r"PART_MARKER_(\d+)", r"\n\nPart \1\n\n", body)
    # Collapse multi-blank-lines to exactly two.
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    parts.append(body)
    return "\n".join(parts).strip() + "\n"


def _fetch_via_html_fallback(slug: str, canonical_title: str) -> bytes | None:
    """Fetch the canonical single-page HTML and convert it to
    text-mirror shape. Returns the encoded bytes or None when the
    page returns 404 or has no recognizable prose."""

    url = f"{BASE}/{slug}.html"
    try:
        raw = _fetch(url).decode("utf-8", errors="replace")
    except urllib.error.HTTPError:
        return None
    text = _html_to_text_mirror(raw, canonical_title)
    if not text or "Part 1" not in text:
        return None
    return text.encode("utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "raw_text_aristotle_ica",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds between ICA requests (default: 1.5 — be polite).",
    )
    ap.add_argument("--skip-existing", action="store_true")
    args = ap.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    works = works_with_ica()
    print(f"=== ICA Aristotle ({len(works)} works) ===")
    for i, w in enumerate(works, 1):
        url = f"{BASE}/{w.ica_slug}.mb.txt"
        slug = _slug_for(w.canonical_title)
        dest_dir = out / slug
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "eng.txt"
        print(f"[{i}/{len(works)}] {w.ica_slug} {w.canonical_title!r} "
              f"-> {dest.relative_to(out)}")
        if args.skip_existing and dest.is_file() and dest.stat().st_size > 0:
            print("  skip (already exists)")
            if i < len(works):
                time.sleep(args.delay)
            continue
        try:
            data = _fetch(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # ICA didn't make a .mb.txt for this work — usually a
                # short Parva Naturalia (memory, sleep, dreams, etc.).
                # Fall back to the per-work HTML page and convert.
                print(f"  no .mb.txt ({e.code}); trying HTML fallback")
                data = _fetch_via_html_fallback(w.ica_slug, w.canonical_title)
                if data is None:
                    print("  HTML fallback also failed; skipping")
                    if i < len(works):
                        time.sleep(args.delay)
                    continue
                # Smaller polite-delay budget already consumed by the
                # text-mirror miss; fall through to write.
            else:
                print(f"  HTTP {e.code}: skipping (ICA slug may be wrong)")
                continue
        dest.write_bytes(data)
        if i < len(works):
            time.sleep(args.delay)

    print(f"\nDone. Wrote files under {out.resolve()}")


if __name__ == "__main__":
    main()
