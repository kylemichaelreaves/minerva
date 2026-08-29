#!/usr/bin/env python3
"""Source the Theognidea — Greek (el.wikisource.org) + English (Banks 1856).

**Greek re-sourced 2026-08-29 (#431)**: Welcker 1826's OCR is corrupted —
Latin letters substituted into Greek words (``vívovra`` for γίνονται) and
its Latin critical apparatus interleaved with the poems as body text
(26.9% of the work's letters, against 0.0–0.1% for a clean ``grc`` work).
No PerseusDL/First1KGreek/Diorisis/Scaife CTS source exists for Theognis
(TLG 0002 — a prior investigation confirmed this 2026-05/06, re-verified
empty 2026-08-29). A source neither investigation checked does:
``el.wikisource.org``'s Ἐλεγεῖαι Θεόγνιδος — the complete canonical
sequence (lines 1–1389, both books), human-transcribed, no apparatus,
stable since 2017. Same site this corpus already sources Greek text
from for Marcus Aurelius (``download_marcus_aurelius.py``), fetched here
via the ``action=parse&prop=wikitext`` API rather than the rendered-HTML
REST endpoint those scrapers use — the raw wikitext's ``{{r|N}}``
line-number templates are what let this recover canonical line numbers
at all; the rendered HTML would need those numbers re-derived from
absolutely-positioned markup instead of a plain regex.

* **English**: J. Banks 1856 *The Works of Hesiod, Callimachus,
  and Theognis* (archive.org ``worksofhesiodca00hesi``). Complete
  prose translation. Page headers like ``MAXIMS OF THEOGNIS.
  13—26`` give canonical-line-range anchors. Not re-sourced — #431
  is specifically about the Greek text's quality, and Banks isn't
  flagged as corrupted.

Output:

    data/theognis/theognidea_grc.txt       # el.wikisource, canonical order
    data/theognis/theognidea_eng.txt       # page-anchored English prose

Both are emitted as plain text (not XML/TEI): the ingest pipeline's
generic ``locator="chapter"`` paragraph splitter already consumes this
shape (one blank-line-separated block per elegy), and neither source
carries markup rich enough to justify a structured format.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from _download import fetch_with_retry

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "theognis"

ENGLISH_URL = (
    "https://archive.org/download/worksofhesiodca00hesi/"
    "worksofhesiodca00hesi_djvu.txt"
)

UA = "minerva-corpus-fetch/1.0 (+personal research; PD-only sources)"

# Wikisource fetch, same shape as download_augustine.py's `_fetch` (the
# rate-limit-as-200 gotcha — see wikimedia-rest-gotchas memory): Wikimedia's
# edge layer sometimes answers 200 OK with a plaintext throttle notice
# instead of a 429, which a retry keyed on HTTPError alone would miss.
_WIKISOURCE_API = "https://el.wikisource.org/w/api.php"
_WIKISOURCE_PAGE = "Ελεγείαι Θεόγνιδος"
_RATE_LIMIT_MARKER = "You are making too many requests"
_MIN_VALID_CHARS = 1024


def _fetch(url: str) -> str:
    return fetch_with_retry(url, timeout=60, user_agent=UA, encoding="utf-8")


def _fetch_wikisource_wikitext(*, retries: int = 6) -> str:
    """Raw wikitext of `_WIKISOURCE_PAGE`, via MediaWiki's `action=parse`.

    Retried the same way `download_augustine.py::_fetch` is: a 200 OK
    whose body is Wikimedia's plaintext rate-limit notice is retried
    with backoff exactly like a real 429 would be, since the edge layer
    does not always return one.
    """

    params = {
        "action": "parse",
        "page": _WIKISOURCE_PAGE,
        "prop": "wikitext",
        "format": "json",
    }
    url = f"{_WIKISOURCE_API}?{urllib.parse.urlencode(params)}"
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            if attempt + 1 >= retries:
                raise
            wait = min(60.0, 5.0 * (2**attempt))
            print(f"  {exc}; retry in {wait:.0f}s ({attempt + 1}/{retries})")
            time.sleep(wait)
            continue
        if len(body) < _MIN_VALID_CHARS and _RATE_LIMIT_MARKER in body:
            if attempt + 1 >= retries:
                raise RuntimeError(f"rate-limited after {retries} retries: {url}")
            wait = min(60.0, 5.0 * (2**attempt))
            print(f"  rate-limit plaintext body; retry in {wait:.0f}s ({attempt + 1}/{retries})")
            time.sleep(wait)
            continue
        payload = json.loads(body)
        if "parse" not in payload:
            raise RuntimeError(f"unexpected API response (no 'parse' key): {payload}")
        return payload["parse"]["wikitext"]["*"]
    raise RuntimeError(f"download failed after {retries} retries: {url}")


#: `{{r|20}}` -> a canonical line-number marker every ~5 lines.
_LINE_MARKER_RE = re.compile(r"\{\{r\|(\d+)\}\}")
#: MediaWiki chrome this page carries that isn't part of the poem.
_HEADER_TEMPLATE_RE = re.compile(r"\{\{κεφαλίδα.*?\}\}", re.DOTALL)
_TRANSLATION_LINK_RE = re.compile(r"^\*μετάφραση.*$", re.MULTILINE)
_CATEGORY_LINK_RE = re.compile(r"^\[\[Κατηγορία:.*\]\]\s*$", re.MULTILINE)
#: The wikitext line-wraps at every `<br>` too, so the tag is always
#: immediately followed by its own real newline — substituting the tag
#: alone for `\n` would double it into a blank line between every verse.
_BR_RE = re.compile(r"<br\s*/?>[ \t]*\n?")


def _extract_greek_wikisource(wikitext: str) -> str:
    """Plain text, one blank-line-separated block per elegy, shaped for
    the generic `locator="chapter"` paragraph splitter.

    `{{r|N}}` templates become inline `[N]` annotations — informational
    anchors preserving the canonical line position, in the same spirit
    as the superseded Welcker file's `[~lines N–N+9]` markers, kept
    inline rather than as parser-recognized headings since neither
    `ΕΛΕΓΕΙΩΝ Α/Β` nor a bracketed line range matches `_HEADING_RE`
    (Latin-alphabet-only) — the same status quo the Welcker file was
    already chunked under, just with clean content underneath it now.
    """

    text = _HEADER_TEMPLATE_RE.sub("", wikitext)
    text = _TRANSLATION_LINK_RE.sub("", text)
    text = _CATEGORY_LINK_RE.sub("", text)
    text = _LINE_MARKER_RE.sub(lambda m: f"[{m.group(1)}]", text)
    text = _BR_RE.sub("\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" \n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def fetch_greek(*, out_dir: Path) -> Path:
    print("\n=== theognidea_grc.txt: el.wikisource Ελεγείαι Θεόγνιδος ===")
    wikitext = _fetch_wikisource_wikitext()
    text = _extract_greek_wikisource(wikitext)
    dest = out_dir / "theognidea_grc.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    print(f"  → {dest} ({len(text):,} chars; {text.count(chr(10))} lines)")
    return dest


def _extract_english(raw: str) -> str:
    """Pull the Theognis section out of the Banks 1856 bundle.

    Strategy: start at "THEOGNIS THE MEGAREAN", end at the next
    work boundary (we look for "INDEX" / "FINIS" / END marker
    after that point). Within the section, drop OCR-detected
    page-header lines and footnote blocks.

    Footnote heuristic: lines starting with a digit + space
    followed by lowercase prose, or lines that are mostly Greek/
    Latin commentary (low English-letter ratio). Imperfect — some
    body sentences will leak footnote content. Hand-curation is
    the safety net.
    """

    lines = raw.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if "THEOGNIS THE MEGAREAN" in ln:
            start = i + 1
            break
    if start is None:
        raise RuntimeError("Banks 1856: Theognis section start not found")

    # The Theognis section runs through the end of the volume.
    # Banks orders Hesiod → Callimachus → Theognis. End markers
    # may include INDEX, FINIS, or copyright pages.
    end = len(lines)
    for i in range(start, len(lines)):
        if any(
            tok in lines[i]
            for tok in ("INDEX TO", "FINIS.", "PRINTED BY", "BOHN'S CLASSICAL")
        ):
            end = i
            break

    out_lines: list[str] = []
    for ln in lines[start:end]:
        s = ln.rstrip()
        stripped = s.strip()
        # Page headers (e.g. "218 MAXIMS OF THEOGNIS. 13—26,").
        # Replace with a section anchor only when we recovered the
        # canonical-line range; bare "[Page]" markers without a
        # range are useless noise downstream.
        if "MAXIMS OF THEOGNIS" in s:
            m2 = re.search(r"(\d+)\s*[—\-]\s*(\d+)", s)
            if m2:
                out_lines.append(f"\n[Lines {m2.group(1)}–{m2.group(2)}]\n")
            continue
        # Lines dominated by Greek characters are footnote
        # commentary (Banks's footnotes quote the Greek alongside
        # the English) — drop.
        if re.search(r"[α-ωΑ-Ω]{3,}", s):
            continue
        # Latin citation footnotes — common abbreviations of
        # ancient sources Banks cross-references.
        if re.match(
            r"\s+(Cf\.|Hor\.|Virg\.|Hom\.|Aristot\.|Plat\.|Pl\.|Sch\.) ",
            s,
        ):
            continue
        # OCR noise: lines too short to be substantive prose. Skip
        # everything < 8 chars unless it's a blank line (which the
        # downstream chunker uses for paragraph splits).
        if stripped and len(stripped) < 8:
            continue
        # Footnote-only lines: pure citation fragments like
        # "1076." or ", 1076." (Banks's line-number annotations).
        if re.fullmatch(r"[,\.;:]?\s*\d{1,4}[,\.;:]?\s*", stripped):
            continue
        # OCR-junk pure-punctuation lines.
        if stripped and not re.search(r"[A-Za-zα-ωΑ-Ω]", stripped):
            continue
        out_lines.append(s)

    # Collapse multi-blank runs.
    text = "\n".join(out_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def fetch_english(*, out_dir: Path) -> Path:
    print("\n=== theognidea_eng.txt: Banks 1856 ===")
    raw = _fetch(ENGLISH_URL)
    text = _extract_english(raw)
    dest = out_dir / "theognidea_eng.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    print(f"  → {dest} ({len(text):,} chars; {text.count(chr(10))} lines)")
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--include-english",
        action="store_true",
        help=(
            "Also re-fetch theognidea_eng.txt. OFF BY DEFAULT (#448): "
            "_extract_english() does not reproduce the 1,492-chunk file "
            "the 2026-06-06 manual trim curated — it regenerates the "
            "untrimmed ~14,805-line original, silently reintroducing the "
            "Hesiod/Callimachus/publisher-catalog pollution that trim "
            "removed. Only pass this once #448's fix lands, or if you "
            "have independently reconstructed and diffed the trim."
        ),
    )
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching el.wikisource Greek ...", file=sys.stderr)
    fetch_greek(out_dir=OUT_DIR)

    if args.include_english:
        print("Fetching Banks 1856 English ...", file=sys.stderr)
        fetch_english(out_dir=OUT_DIR)
    else:
        print(
            "\nSkipping English (see #448) — pass --include-english to "
            "force it.",
            file=sys.stderr,
        )

    print(
        "\nDone. Greek is now el.wikisource's Ελεγείαι Θεόγνιδος (#431) — "
        "clean, complete, canonical order. English is still the Banks 1856 "
        "first-cut OCR extraction; hand-curation remains the safety net "
        "there. See add-theognis-plan / theognis-ingest-done memory.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
