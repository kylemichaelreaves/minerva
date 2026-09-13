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


# ── Recovering spaces that were never in the text layer ────────────
#
# Some spans in scholarly PDFs carry no space glyphs at all. Two lines of
# the Inwood *Phenomenology*'s editor's introduction extract as
# `IthasbeensaidthatthedifferencebetweenNietzscheandHegel…`, and no
# PyMuPDF mode recovers them: `get_text("text")` and `get_text("words")`
# agree, because there is nothing to find. See #561.
#
# The character positions still hold the answer. Within a word the glyph
# gap is about -0.14pt; between words it is +1.3 to +1.4pt. Cutting at
# the large gaps restores the words exactly — nothing is guessed and no
# dictionary is consulted, which is what separates this from a
# space-insertion pass over damaged text.
#
# Almost every space-less span is an ordinary single word — over the two
# Hegel PDFs, 12,072 of 63,065 spans contain no space and only a couple
# of dozen are damaged. So the shape of the gap distribution, not
# space-lessness and not length, is what identifies the damage. That is
# also what makes the pass immune to #561's predicted false positive:
# `Transzendentalphilosophie` really is one word and its gaps really are
# uniform.
#
# **Measured across all 15 PDFs in the corpus, the guards below matter
# more than the rule they guard.** The bare "gap above the median" test
# fired 296 times and was wrong nearly every time; with the guards it
# fires 20 times and is right every time, touching only the two PDFs
# #561 names. The four false-positive families it had to learn are
# documented on `_split_on_char_gaps`. Anyone loosening a guard should
# re-run that sweep rather than sample a page.

#: Width of the empty band that must separate word gaps from letter gaps.
#: The test is a real *valley*, not "above the median": the smallest gap
#: taken as a word break must exceed the largest gap left inside a word
#: by this much. "Widest gap in the span" is not enough, because every
#: span has a widest gap — that version split `INTRODUCTION` (a
#: letter-spaced heading, whose gaps are all equal) into `IN TRODUCTION`.
_SPACE_GAP_VALLEY = 0.6

#: A word break must also be positive in absolute terms. Glyph boxes in
#: a tight font overlap, so gaps inside a word run slightly negative.
_SPACE_GAP_MIN = 0.4

#: Below this many characters a span has too few gaps to read a
#: distribution off.
_SPACE_MIN_CHARS = 12

#: Private Use Area. The Inwood PDF encodes some runs in PUA glyphs that
#: carry no usable character identity; splitting them tidies nothing and
#: the result is unreadable either way.
_PUA = range(0xE000, 0xF900)

_VOWEL_RE = re.compile(r"[aeiouyàâäéèêëîïôöùûüAEIOUYÀÂÄÉÈÊËÎÏÔÖÙÛÜ]")

#: The only single letters that stand alone as words in the languages
#: these PDFs are set in (English, German, French).
_STANDALONE_LETTER_WORDS = frozenset("aAiIoOyY")


def _split_on_char_gaps(
    chars: list[tuple[str, float, float]],
) -> str | None:
    """Re-insert spaces into a run-on span using its glyph geometry.

    ``chars`` is ``(character, x0, x1)`` in reading order. Returns the
    spaced text, or None when the span is not damaged — the common case,
    which must stay cheap.

    **A span carrying any space at all is declined, and that costs real
    repairs.** Damage can be partial — ``–Itwillnotbewithoutinterest
    toexaminethisconstruction`` is one span with a real space in the
    middle and a lost one either side — and about 13 genuine runs are
    left unrepaired by this rule. Tracked separately rather than fixed
    here, because judging each space-delimited segment on its own was
    tried and is much worse: it takes the corpus-wide count from 23
    repairs to **284**, and the additions split ordinary words —
    ``tr ansmitted``, ``Hoff meister``, ``j uxtapositions``,
    ``o bjectionable``. An eleven-character word has ten gaps, one kern
    pair is enough to look bimodal across so few, and the surrounding
    spaces that would have revealed the span as healthy are exactly what
    segmenting throws away. The whole-span space test is doing most of
    the work of this function.
    """

    if any(c.isspace() for c, _, _ in chars):
        return None
    return _split_segment(chars)


def _split_segment(
    chars: list[tuple[str, float, float]],
) -> str | None:
    """One space-free run → its spaced form, or None if undamaged.

    **Every guard below was added because it had to be.** Run against all
    15 PDFs in the corpus, the bare "gap above the median" rule fired 296
    times, of which fewer than two dozen were real. The rest were four
    recurring shapes, and each guard names the one it exists for:

    * a spacing diacritic (``Barthe´lemy``, ``Zur¨uckf¨uhrung``) is a
      zero-advance glyph whose box arithmetic fakes one wide gap — 164 of
      the 296 had exactly one break, and this was nearly all of them;
    * a letter-spaced heading (``INTRODUCTION``) has *uniform* wide gaps,
      so it has a widest one without having a bimodal one;
    * PUA-encoded runs, which are unreadable whatever is done to them;
    * punctuation spacing (``thing-in-itself);`` → ``thing-in-itself );``),
      which is not a lost word space at all.
    """

    if len(chars) < _SPACE_MIN_CHARS:
        return None
    if all(x1 - x0 <= 0 for _, x0, x1 in chars):
        return None
    if any(ord(c) in _PUA for c, _, _ in chars):
        return None
    gaps = [nxt[1] - cur[2] for cur, nxt in pairwise(chars)]
    if len(gaps) < _SPACE_MIN_CHARS - 1:
        return None

    # Find the widest empty band in the sorted gaps. A span with lost
    # spaces is bimodal — a tight cluster inside words, a tight cluster
    # between them, and nothing in between.
    ordered = sorted(gaps)
    valley_at = max(range(1, len(ordered)), key=lambda i: ordered[i] - ordered[i - 1])
    valley = ordered[valley_at] - ordered[valley_at - 1]
    if valley < _SPACE_GAP_VALLEY:
        return None
    threshold = max(ordered[valley_at], _SPACE_GAP_MIN)
    breaks = {i for i, g in enumerate(gaps) if g >= threshold}
    if not breaks:
        return None

    # A lost word space sits between two letters. A break beside a
    # diacritic, a bracket or a quote mark is the glyph-box artefact
    # above, not a missing space.
    if not any(chars[i][0].isalpha() and chars[i + 1][0].isalpha() for i in breaks):
        return None

    # Letter-spaced headings are the other shape with wide gaps, and
    # `_fuse_kerned_words` below already exists to *close* them — this
    # pass must not fight it. Uniform spacing usually fails the valley
    # test, but not always: `TRANSLATIONS` has one tight pair (`AT`) and
    # so reads as bimodal, and came out `T R A N S L AT I O N S`. Prose
    # that lost its spaces is mixed case; a banner is not. Same 0.85
    # ratio `_fuse_kerned_words` uses, for the same phenomenon.
    letters = [c for c, _, _ in chars if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) >= 0.85:
        return None

    out: list[str] = []
    for i, (c, _, _) in enumerate(chars):
        out.append(c)
        if i in breaks:
            out.append(" ")
    result = "".join(out)

    # Last guards: every part that is a word must look like one.
    parts = result.split()
    for index, part in enumerate(parts):
        # A lone letter in the *middle* is a cut inside a word — a
        # drop cap, in the one case that reached here (`[Gedankenbes`
        # → `[ G edankenbes`). At either end it is legitimate, because
        # a span often begins or ends mid-word: the damaged run after
        # `Nietzsche’` opens with a bare `s`.
        if (
            len(part) == 1
            and part.isalpha()
            and 0 < index < len(parts) - 1
            and part not in _STANDALONE_LETTER_WORDS
        ):
            return None
        # A wholly alphabetic part of three or more letters with no
        # vowel is a cut inside a word.
        #
        # **Alphabetic only, and that restriction is load-bearing.** A
        # first version tested any part containing a letter, and
        # rejected three correct repairs on abbreviations that have no
        # vowel by nature: `cf.`, and the `W.` and `L.` of
        # `Selected Essays on G. W. F. Hegel` and
        # `. Edited by L. Stepelevich.` Requiring `isalpha()` exempts
        # anything carrying a period.
        if len(part) >= 3 and part.isalpha() and not _VOWEL_RE.search(part):
            return None
    return result


def _page_space_repairs(page) -> dict[str, str]:
    """Map every damaged run-on on this page to its repaired form.

    Keyed on the run-on string itself rather than on position, so the
    repair can be applied to the lines the existing word-based
    extraction produces without restructuring it. The keys are 12+
    characters with no spaces, so a plain substring replacement cannot
    collide with ordinary text.
    """

    repairs: dict[str, str] = {}
    for block in page.get_text("rawdict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                chars = span.get("chars") or []
                triples = [
                    (c["c"], float(c["bbox"][0]), float(c["bbox"][2]))
                    for c in chars
                ]
                fixed = _split_on_char_gaps(triples)
                if fixed is None:
                    continue
                original = "".join(c for c, _, _ in triples)
                if fixed != original:
                    repairs[original] = fixed
    return repairs


def _extract_pdf_page_lines(page) -> list[str]:
    """Extract a single page as a list of plain-text lines, fusing
    adjacent words whose horizontal gap is below the kerning threshold,
    and re-inserting spaces that the text layer never carried.
    """

    repairs = _page_space_repairs(page)
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
        line = _fuse_kerned_words(line_words)
        # Applied after fusion, not before: `_fuse_kerned_words` joins
        # kerned words and could otherwise re-close a gap this just
        # opened. Longest key first, so a run-on that contains a shorter
        # one is not partly rewritten out from under itself.
        for original in sorted(repairs, key=len, reverse=True):
            if original in line:
                line = line.replace(original, repairs[original])
        out.append(line)
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
