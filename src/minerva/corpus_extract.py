"""Format-specific text extraction for the ingest pipeline.

Sister module to `corpus_parse.py`. Lives separately because none of
these helpers know anything about chunk boundaries, section locators,
or the `Work` config — they take a `Path`, return a string. Splitters
(in `corpus_parse.py`) consume that string and produce chunks.

The PDF path has its own twist: scholarly editions typeset chapter
heads with typographic letter-spacing, which PyMuPDF's plain text
extractor flattens into word breaks. We extract per-word bounding
boxes and fuse adjacent "words" whose horizontal gap is well below the
line's average character width, but only on lines that look like
headings (≥85% uppercase). See `_fuse_kerned_words` for the details.

Optional deps (`pymupdf`, `ebooklib`, `beautifulsoup4`) are imported
lazily so the rest of the project can run without the `[hegel]` extras
installed; calling an extractor without its dep raises a friendly
`IngestDepsMissing`.
"""

from __future__ import annotations

import re
from itertools import pairwise
from pathlib import Path


class IngestDepsMissing(RuntimeError):
    """Raised when the optional `[hegel]` extras aren't installed."""


# ---------- PDF ----------


def extract_pdf(
    path: Path,
    *,
    pages: tuple[int, int] | None = None,
) -> str:
    """Extract text from a PDF, with kerning-aware word fusion to
    recover from typographic letter-spacing in chapter headings.

    PDFs from scholarly editions often typeset chapter heads with wide
    intra-letter kerning (e.g. ``PRESOCRATICS`` rendered with a 1px gap
    between every glyph). PyMuPDF's plain ``get_text("text")`` mode
    treats those gaps as word breaks, producing junk like ``PRESO
    CRATICS`` or ``IN TRODUCTION``. We extract per-word bounding boxes
    instead and fuse adjacent words whose horizontal gap falls below
    a fraction of the line's average character width.

    Running headers/footers are still stripped via the page-chrome
    heuristic at the line level.

    ``pages``
        Optional ``(start, end)`` 1-indexed inclusive page range —
        restricts extraction to that span. Used to carve a single
        Cambridge omnibus PDF (Gregor's Practical Philosophy) into
        per-work chunks: each Work declares its own page range and
        gets only its own pages extracted. ``None`` extracts the
        whole document, preserving backward compatibility.
    """

    try:
        import fitz  # type: ignore[import-untyped]
    except ImportError as exc:
        raise IngestDepsMissing(
            "PDF ingest requires `pymupdf`. Install with `pip install -e '.[hegel]'`."
        ) from exc

    page_lines: list[list[str]] = []
    with fitz.open(path) as doc:
        if pages is None:
            iterable = list(doc)
        else:
            start, end = pages
            # Clamp to the document and convert 1-indexed inclusive →
            # 0-indexed half-open slice. PyMuPDF page numbers are
            # 0-indexed; user-facing page ranges (and the TOC bookmarks
            # we get from `doc.get_toc`) are 1-indexed.
            lo = max(0, start - 1)
            hi = min(doc.page_count, end)
            iterable = [doc[i] for i in range(lo, hi)]
        for page in iterable:
            page_lines.append(_extract_pdf_page_lines(page))

    return _clean_page_lines(page_lines)


# Cambridge editions of Kant typeset the Akademie-Ausgabe volume
# and page number in the margin of each printed page, which the PDF
# extractor surfaces as a separate line at the top or bottom of the
# page. Pattern: a volume number (1-30), a colon, an Akademie page
# (Arabic digits or lowercase Roman numerals for front matter), then
# a short trailing work-title fragment. We trim them out so chunks
# only carry running prose.
_AKADEMIE_RUNNING_HEADER_RE = re.compile(
    r"^\d{1,2}:(?:[ivxlcdm]+|\d{1,4})\b.{0,80}$",
    re.IGNORECASE,
)


# Below this fraction of the line's average character width, an
# inter-word gap is treated as kerning rather than a real space and
# the two "words" are fused. Tuned against LHP / KrV PDFs where real
# spaces sit at ~0.6–0.8× char width and kerning artifacts at ~0.15×.
_KERNING_FUSION_THRESHOLD = 0.4


def _clean_page_lines(page_lines: list[list[str]]) -> str:
    """Strip page furniture from per-page line lists and join to text.

    Shared by every extractor that works page-by-page, so a second source
    of the same pages — a re-OCR, say — gets identical treatment rather
    than a second copy of these rules (#540).
    """

    chrome = _detect_page_chrome(page_lines)
    cleaned: list[str] = []
    for lines in page_lines:
        for line in lines:
            stripped = line.strip()
            if stripped and stripped in chrome:
                continue
            # Drop Akademie-Ausgabe running-page headers like
            # "4:385 Groundwork of The metaphysics of morals" or
            # "5:i Critique of practical reason". These vary by page
            # so the page-chrome heuristic (which matches whole-line
            # repeats) doesn't catch them; this regex does. The
            # information they carry (the Akademie page reference) is
            # recoverable from a future locator pass — for now we'd
            # rather have clean prose than noise chunks.
            if stripped and _AKADEMIE_RUNNING_HEADER_RE.match(stripped):
                continue
            cleaned.append(line)
        cleaned.append("")  # page break preserves paragraph boundaries
    return "\n".join(cleaned)


def extract_ocr_pages(path: Path) -> str:
    """Text from a re-OCR artefact: ``{"pages": [[line, ...], ...]}``.

    Written by `perseus/ocr_lpwh.py` for a scan whose embedded OCR layer
    is too corrupt to use (#540). The file stores *per-page line lists*
    rather than flat text precisely so this path can hand them to
    `_clean_page_lines` and get the same page-chrome and running-head
    treatment `extract_pdf` gets — the furniture is a property of the
    page, and flattening first would throw away what identifies it.

    `data/` is gitignored, so the artefact is not in version control any
    more than the PDF it comes from; the script that regenerates it is.
    """

    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    pages = data.get("pages")
    if not isinstance(pages, list):
        # Loudly, because silence is this pipeline's failure mode: a
        # malformed artefact must not read as a work with no text.
        raise ValueError(f"{path.name}: expected a 'pages' list, got {type(pages).__name__}")
    return _clean_page_lines([[str(line) for line in page] for page in pages])


def _extract_pdf_page_lines(page) -> list[str]:
    """Extract a single page as a list of plain-text lines, fusing
    adjacent words whose horizontal gap is below the kerning threshold.
    """

    # `words` returns tuples (x0, y0, x1, y1, text, block_no, line_no, word_no).
    words = page.get_text("words")
    if not words:
        return []
    grouped: dict[tuple[int, int], list[tuple]] = {}
    for w in words:
        key = (w[5], w[6])
        grouped.setdefault(key, []).append(w)
    out: list[str] = []
    for key in sorted(grouped.keys()):
        line_words = sorted(grouped[key], key=lambda w: w[0])
        out.append(_fuse_kerned_words(line_words))
    return out


def _fuse_kerned_words(line_words: list[tuple]) -> str:
    """Join words whose pairwise gap is below the kerning threshold.

    Restricted to lines that are predominantly uppercase, where
    typographic letter-spacing actually occurs in scholarly editions.
    Body text often has tight word spacing in justified PDFs that the
    threshold would misclassify; mixed-case lines are returned with
    PyMuPDF's default tokenization.
    """

    if not line_words:
        return ""
    if len(line_words) == 1:
        return line_words[0][4]
    alpha_chars = [c for w in line_words for c in w[4] if c.isalpha()]
    if not alpha_chars:
        return " ".join(w[4] for w in line_words)
    upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
    if upper_ratio < 0.85:
        return " ".join(w[4] for w in line_words)
    # Compute pairwise horizontal gaps. Only fuse when the distribution
    # is bimodal (some clearly kerned, some clearly real word gaps).
    # Uniformly tight gaps mean the whole line is one letter-spaced
    # banner — let the post-extraction title-page heuristics drop it.
    gaps: list[float] = []
    for prev, curr in pairwise(line_words):
        gaps.append(curr[0] - prev[2])
    if not gaps:
        return " ".join(w[4] for w in line_words)
    min_gap = min(gaps)
    max_gap = max(gaps)
    if max_gap < 2 * max(min_gap, 0.5):
        return " ".join(w[4] for w in line_words)
    # Per-word average character width — the threshold scales with the
    # font size, which matters for headings rendered larger than body.
    widths: list[float] = []
    for w in line_words:
        text = w[4]
        if not text:
            continue
        widths.append((w[2] - w[0]) / max(1, len(text)))
    if not widths:
        return " ".join(w[4] for w in line_words)
    avg_char_width = sum(widths) / len(widths)
    threshold = avg_char_width * _KERNING_FUSION_THRESHOLD
    parts: list[str] = [line_words[0][4]]
    for (_prev, curr), gap in zip(pairwise(line_words), gaps, strict=True):
        if gap < threshold:
            parts[-1] += curr[4]
        else:
            parts.append(curr[4])
    return " ".join(parts)


def _detect_page_chrome(pages: list[list[str]], threshold: float = 0.5) -> set[str]:
    """Identify lines that recur in the top/bottom 4 lines of >= 50% of pages."""

    if len(pages) < 4:
        return set()
    top_counts: dict[str, int] = {}
    bot_counts: dict[str, int] = {}
    for page_lines in pages:
        # Headers and footers are typically short, so only count lines <= 80 chars.
        for line in page_lines[:4]:
            s = line.strip()
            if 0 < len(s) <= 80:
                top_counts[s] = top_counts.get(s, 0) + 1
        for line in page_lines[-4:]:
            s = line.strip()
            if 0 < len(s) <= 80:
                bot_counts[s] = bot_counts.get(s, 0) + 1
    cutoff = max(2, int(len(pages) * threshold))
    chrome: set[str] = set()
    for counts in (top_counts, bot_counts):
        for s, n in counts.items():
            if n >= cutoff:
                chrome.add(s)
    return chrome


# ---------- EPUB ----------


_EPUB_SUBSTANTIAL_TEXT = 5_000


def extract_epub(path: Path) -> str:
    """Extract text from an EPUB by walking each HTML document in order.

    Scholarly EPUBs are laid out as front matter → main text → back
    matter, with each region split across its own spine items. Items
    whose leading heading names editor / translator apparatus —
    "Editor's introduction", "Translator's preface", "Editorial notes",
    "Glossary", "Index of names", etc. — are filtered out so they
    aren't attributed to the work's author downstream:

    * Before any substantial main-text item is seen, individual
      editorial items are skipped (the next item could still be Hegel).
    * After main text has appeared, the first editorial item stops the
      walk entirely — subsequent items are also back matter, but their
      headings (e.g. continuation pages of Editorial Notes) aren't
      always recognizable on their own. Stopping here drops them too.

    "Substantial" is defined by `_EPUB_SUBSTANTIAL_TEXT`. PR's main
    body items run 12k–145k chars cleaned; its front matter pages cap
    out around 2k.
    """

    try:
        import ebooklib  # type: ignore[import-untyped]
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]
        from ebooklib import epub  # type: ignore[import-untyped]
    except ImportError as exc:
        raise IngestDepsMissing(
            "EPUB ingest requires `ebooklib` and `beautifulsoup4`. "
            "Install with `pip install -e '.[hegel]'`."
        ) from exc

    # `book.spine` preserves the publication's reading order;
    # `get_items_of_type(ITEM_DOCUMENT)` does not (e.g. titlepage.xhtml
    # may end up at the tail), and reading order is what the editorial-
    # filter logic relies on (front matter → main text → back matter).
    book = epub.read_epub(path)
    parts: list[str] = []
    seen_substantial = False
    for item_id, _ in book.spine:
        item = book.get_item_with_id(item_id)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        html = item.get_content().decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        # Drop nav and toc-y elements before extraction.
        for tag in soup.select("nav, header, footer, [epub\\:type=toc]"):
            tag.decompose()
        if _epub_item_is_editorial(soup):
            if seen_substantial:
                break
            continue
        text = soup.get_text("\n", strip=True)
        parts.append(text)
        if len(text) >= _EPUB_SUBSTANTIAL_TEXT:
            seen_substantial = True
    return "\n\n".join(parts)


def _epub_item_is_editorial(soup) -> bool:
    """Test whether an EPUB spine item's leading heading names editor /
    translator apparatus rather than the work's author. Looks at the
    first ``<h1>``–``<h6>`` and falls back to ``<title>``.
    """

    from .heading_clean import _is_editorial_heading

    for sel in ("h1", "h2", "h3", "h4", "h5", "h6"):
        h = soup.find(sel)
        if h:
            label = h.get_text(" ", strip=True)
            if label:
                return _is_editorial_heading(label)
    title_tag = soup.find("title")
    if title_tag:
        return _is_editorial_heading(title_tag.get_text(" ", strip=True))
    return False


# ---------- HTML ----------


def extract_html(path: Path) -> str:
    """Extract text from a stand-alone HTML file.

    Recognizes two source-specific layouts:
    * **zeno.org** — body text lives inside ``#zenoCOText`` containers,
      one per subpage. Concatenated dumps from
      `perseus/download_hegel_de.py` have many such containers in a
      single file, separated by site chrome that we drop wholesale.
    * **Wikisource** — body text lives inside ``.mw-parser-output``.

    Falls back to whole-document text if neither marker is present.
    """

    try:
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]
    except ImportError as exc:
        raise IngestDepsMissing(
            "HTML ingest requires `beautifulsoup4`. Install with `pip install -e '.[hegel]'`."
        ) from exc

    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    # Strip elements that are pure site chrome regardless of source. We do
    # this before container selection so any chrome embedded inside a
    # content container also gets dropped.
    for sel in (
        "nav",
        "header",
        "footer",
        "script",
        "style",
        # Wikisource
        ".navigation-not-searchable",
        ".printfooter",
        ".mw-editsection",
        ".reference",
        ".references",
        ".sister-projects",
        "[role=navigation]",
        # zeno.org
        ".zenoSF",
        ".zenoCOHeader",
        ".zenoCOHeadline",
        ".zenoCOHeadlineSub",
        ".zenoCOHeadlineLibName",
        ".zenoCOBackForth",
        ".zenoCOFooterLine",
        ".zenoCOFooterLineLeft",
        ".zenoCOFooterLineRight",
        ".adsbygoogle",
        ".zenoLSInnerProductTableRightAmazon",
        ".zenoLSInnerProductTableRightLesesaal",
        ".zenoLRBox",
        "#socialBookmarks",
        "#socialshareprivacy",
    ):
        for tag in soup.select(sel):
            tag.decompose()

    # Prefer source-specific content containers when present.
    for selector in ("#zenoCOText", ".mw-parser-output"):
        bodies = soup.select(selector)
        if bodies:
            return "\n\n".join(b.get_text("\n", strip=True) for b in bodies)
    return soup.get_text("\n", strip=True)
