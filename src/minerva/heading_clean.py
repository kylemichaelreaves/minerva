"""Pure text normalization for chapter headings detected during ingest.

Sister module to `corpus_parse.py`. Lives separately because none of
these helpers touch PDF/EPUB/HTML I/O — they're string-in, string-out
predicates and transforms. Keeping them isolated keeps the ingest
extractors and splitters legible.

Imported back into `corpus_parse` (via re-export) so existing test
imports — `corpus_parse._clean_heading_label`, etc. — keep working
without churn.
"""

from __future__ import annotations

import re

from .corpus_works import CorpusWork

# Some scholarly editions render chapter heads with typographic
# letter-spacing (e.g. "T H E   F I R S T   P E R I O D"); PDF text
# extraction flattens this into single spaces between every character,
# losing word boundaries. We can't recover the original spacing without
# a dictionary, so the cleanup strategy is to *drop* letter-spaced runs
# from heading labels and fall back to the work + paragraph locator —
# noisy locators are worse than no heading.
_LETTER_SPACED_RUN_RE = re.compile(r"(?:\b[A-Za-z]\b\s+){3,}\b[A-Za-z]\b")

# Articles, prepositions, and conjunctions that stay lowercase in
# Title Case unless they're the first word. Includes a few German tokens
# so de-language headings ("Vom Wesen", "Die Phänomenologie...") render
# correctly when normalized from ALL CAPS.
_TITLE_LOWER = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "but",
        "by",
        "for",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "up",
        "vs",
        "with",
        "der",
        "die",
        "das",
        "des",
        "den",
        "dem",
        "ein",
        "eine",
        "einer",
        "von",
        "vom",
        "und",
        "oder",
        "im",
        "zu",
        "zum",
        "zur",
        "auf",
    }
)

_ROMAN_RE = re.compile(r"^[IVXLCDM]+$")

# Keyword signals that a heading is publisher / copyright front-matter
# rather than a real chapter title. Conservative: only obvious signals,
# so we don't accidentally drop "Preface" / "Introduction" / chapter
# names that include common words.
_FRONT_MATTER_KEYWORDS = frozenset(
    {
        "UNIVERSITY",
        "PRESS",
        "PUBLISHED",
        "PUBLISHER",
        "COPYRIGHT",
        "ISBN",
        "EDITION",
    }
)

_VOLUME_PREFIX_RE = re.compile(r"^volume\s+[ivxlcdm]+\b", re.IGNORECASE)

# Phrases that, when present in a heading label, signal the chunk
# belongs to editor / translator apparatus rather than Hegel's own
# text. The chapter splitter drops entire heading regions whose label
# matches one of these, so the chunks aren't surfaced as `author:
# Hegel` at retrieval time.
#
# Stored in whitespace-stripped, alpha-only form so OCR variants like
# "Editorial Intr O Duction" or "Editori a L Intro Duction" still
# match after normalization.
#
# Deliberately omitted: bare "preface" and "introduction". Hegel
# himself writes prefaces and introductions (PhG Vorrede, PR Vorrede,
# Encyclopaedia Einleitung), so we only catch the qualified variants
# — "editorial introduction", "translator's preface".
# Whole labels only: "index" as a substring would catch "Indexical".
# A back-of-book index is the editor's apparatus, and Hume's was indexed as
# his body text until INDEX became a heading (#731).
_EDITORIAL_LABELS = frozenset({"index"})

_EDITORIAL_PHRASES = frozenset(
    {
        "editorialintroduction",
        "editorsintroduction",
        "translatorspreface",
        "translatorsintroduction",
        "translatorsnote",
        "editorsnote",
        "editorialnote",
        "editorsforeword",
        "foreword",
        "listofabbreviations",
        "keytoabbreviations",
        "abbreviations",
        "glossary",
        "bibliography",
        "bibliographical",
        "bibliographicalnote",
        "selectedbibliography",
        "secondaryworks",
        "selectedreadings",
        "selectedreading",
        "furtherreading",
        "suggestedreading",
        "suggestedreadings",
        "sourcesusedoralludedtoby",
        "workscited",
        "tableofcontents",
        "contents",
        "indexofnames",
        "nameindex",
        "subjectindex",
        "indexofsubjects",
        "indexofcitations",
        "acknowledgments",
        "acknowledgements",
        "inmemoriam",
        "dedication",
        "abouttheauthor",
        "abouttheeditor",
        "aboutthetranslator",
        "chronology",
    }
)

_EDITORIAL_NORM_RE = re.compile(r"[^a-z]")

#: Only phrases this long get the fuzzy pass. The short entries in
#: `_EDITORIAL_PHRASES` ("contents", "glossary", "foreword") are matched by
#: substring, and letting them match approximately fires on ordinary chapter
#: titles — "The Content of Religion" is not a table of contents.
_FUZZY_MIN_PHRASE_LEN = 12
#: Edit distance allowed on the whole normalized label. Measured over all
#: 94,424 distinct heading labels in the corpus: d<=2 newly matches exactly
#: two, "Bjbljography" and "Editorial Introouctjon", both genuine. d<=3
#: starts admitting real headings.
_FUZZY_MAX_DISTANCE = 2


def _within_distance(a: str, b: str, cap: int) -> bool:
    """True when `a` and `b` are within `cap` edits (Levenshtein).

    Full-row Levenshtein with an early bailout — not banded. Once a row's
    minimum exceeds `cap` the final distance cannot come back under it, so the
    walk stops there. The caller runs this against every long phrase for every
    heading in an ingest, which is why the cheap length check comes first.
    """

    if abs(len(a) - len(b)) > cap:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        if min(cur) > cap:
            return False
        prev = cur
    return prev[-1] <= cap


def _smart_title_case(label: str) -> str:
    """Convert an ALL-CAPS heading to Title Case.

    Mixed-case input is left untouched (we treat it as already
    intentionally cased). Roman numerals are preserved verbatim
    ("II" stays "II", not "Ii"). Articles in `_TITLE_LOWER` stay
    lowercase except in the first word position.
    """

    if not label.strip():
        return label
    # Anything with internal lowercase is already cased — don't touch it.
    if any(c.islower() for c in label):
        return label
    words = label.split()
    out: list[str] = []
    for i, w in enumerate(words):
        # Split the token into surrounding punctuation + the alpha core
        # so word-level rules apply to the core only.
        m = re.match(r"^([^\w]*)([\w'-]*)([^\w]*)$", w, re.UNICODE)
        if m is None:
            out.append(w)
            continue
        prefix, core, suffix = m.group(1), m.group(2), m.group(3)
        if not core:
            out.append(w)
            continue
        if _ROMAN_RE.match(core):
            out.append(prefix + core + suffix)
            continue
        lower = core.lower()
        if i > 0 and lower in _TITLE_LOWER:
            out.append(prefix + lower + suffix)
        else:
            out.append(prefix + core[0].upper() + core[1:].lower() + suffix)
    return " ".join(out)


def _is_likely_front_matter(label: str) -> bool:
    """Heuristic: a heading dominated by publisher / copyright signals."""

    upper = label.upper()
    return any(kw in upper for kw in _FRONT_MATTER_KEYWORDS)


def _surnames_for(work: CorpusWork) -> set[str]:
    """Lower-cased surnames associated with the work — used to detect
    headings that are actually author / translator attributions from the
    title page (e.g. "Robert F. Brown" appearing as a chapter label
    when the translator field is "Brown / Stewart")."""

    out: set[str] = set()
    for src in (getattr(work, "author", None), work.translator):
        if not src:
            continue
        for part in re.split(r"[/&,]", src):
            words = part.strip().split()
            if words:
                out.add(words[-1].lower())
    return out


def _is_garbled_letter_spacing(label: str) -> bool:
    """Catch letter-spaced text that the strict regex misses because PDF
    extraction partially fused some characters into short tokens
    ("C Ont E N Ts" was originally "CONTENTS" with character spacing).
    Signal: 4+ tokens of which 60%+ are 1–3 chars long.
    """

    tokens = label.split()
    if len(tokens) < 4:
        return False
    short = sum(1 for t in tokens if len(re.sub(r"\W", "", t)) <= 3)
    return short >= len(tokens) * 0.6


def _is_label_too_short(label: str) -> bool:
    """Drop labels that have too few alphabetic characters to be useful
    as a citation locator. Two thresholds:

    * Any label with < 4 alpha chars (catches single-token fragments like
      "IL" / "Hy" produced by PDF extraction at line breaks).
    * Multi-token labels with < 6 alpha chars (catches "Ed Od", "Int on"
      where two short tokens together still don't say anything).
    """

    alpha = re.sub(r"\W", "", label)
    n_tokens = len(label.split())
    if not alpha:
        return False
    if len(alpha) < 4:
        return True
    return n_tokens >= 2 and len(alpha) < 6


def _is_title_page_artifact(label: str, work: CorpusWork) -> bool:
    """Detect heading labels that are likely title-page text rather than
    chapter titles. Several signals are checked, ordered by confidence:

    1. **Garbled letter-spacing.** Mostly-1-or-2-char tokens (PDF
       extraction artifact of typographic character spacing).
    2. **Attribution.** A 2–5 word label that includes an author or
       translator surname (e.g. "Robert F. Brown").
    3. **Author + title concatenation.** A longer label that combines
       an author/translator surname with multiple words from the work's
       own title (e.g. "Georg Wilhelm Friedrich Hegel Lectures on the
       History of Philosophy").
    4. **Volume marker.** A label that opens with "Volume <Roman>".
    5. **Single title word.** A single-word label that's part of the
       work's title (does not match "Preface" / "Introduction" / etc.).
    """

    if _is_garbled_letter_spacing(label):
        return True

    if _is_label_too_short(label):
        return True

    label_words = label.split()
    surnames = _surnames_for(work)
    if surnames and 2 <= len(label_words) <= 5:
        for w in label_words:
            bare = re.sub(r"[^\w]", "", w).lower()
            if bare in surnames:
                return True

    if surnames and len(label_words) > 5:
        label_lower_tokens = {re.sub(r"[^\w]", "", w).lower() for w in label_words}
        if any(s in label_lower_tokens for s in surnames):
            title_words = set(re.findall(r"[A-Za-z]{4,}", work.title.lower()))
            label_words_filtered = set(re.findall(r"[A-Za-z]{4,}", label.lower()))
            if len(label_words_filtered & title_words) >= 2:
                return True

    if _VOLUME_PREFIX_RE.match(label):
        return True

    if len(label_words) == 1:
        bare = re.sub(r"[^\w]", "", label_words[0]).lower()
        title_tokens = set(re.findall(r"[A-Za-z]+", work.title.lower()))
        if bare in title_tokens:
            return True

    return False


def _is_editorial_heading(label: str) -> bool:
    """Detect headings naming editor / translator material rather than
    Hegel's own text.

    Two passes. The exact pass matches on a normalized form (lowercased,
    non-letters removed), which absorbs *spacing and punctuation* damage —
    "Editorial Intr O Duction" collapses to "editorialintroduction". It does
    NOT absorb letter substitution, which is what OCR mostly produces:
    "Introouctjon", "Bjbljography". Those are caught by the fuzzy pass below,
    bounded to phrases of length >= `_FUZZY_MIN_PHRASE_LEN` so the short
    substring-matched entries ("contents", "glossary") cannot fire on real
    chapter titles. See #534.
    """

    if not label:
        return False
    norm = _EDITORIAL_NORM_RE.sub("", label.lower())
    if not norm:
        return False
    if norm in _EDITORIAL_LABELS or any(phrase in norm for phrase in _EDITORIAL_PHRASES):
        return True
    # Fuzzy fallback for OCR letter substitution — "introouctjon" for
    # "introduction", "bjbljography" for "bibliography". The exact pass above
    # already handles spacing and punctuation damage, which is all
    # `_EDITORIAL_NORM_RE` can absorb on its own.
    if len(norm) < _FUZZY_MIN_PHRASE_LEN:
        return False
    return any(
        _within_distance(norm, phrase, _FUZZY_MAX_DISTANCE)
        for phrase in _EDITORIAL_PHRASES
        if len(phrase) >= _FUZZY_MIN_PHRASE_LEN
    )


def _is_skipped_for_work(label: str, skip_headings: tuple[str, ...]) -> bool:
    """Per-work counterpart to `_is_editorial_heading`. Used when an
    edition's "Preface" or "Introduction" is editor apparatus that the
    global filter can't drop without false positives elsewhere.
    """

    if not label or not skip_headings:
        return False
    norm = _EDITORIAL_NORM_RE.sub("", label.lower())
    if not norm:
        return False
    return any(_EDITORIAL_NORM_RE.sub("", pat.lower()) in norm for pat in skip_headings if pat)


def _clean_heading_label(label: str) -> str:
    """Pipeline of heading normalizations:

    1. Strip letter-spaced runs (PDF-extraction signature of typographic
       character spacing — see `_LETTER_SPACED_RUN_RE`).
    2. Drop labels that look like publisher / copyright front-matter,
       which match the source's heading regex because they're set in
       caps but aren't real chapter heads.
    3. Title-case ALL-CAPS labels for readability in citations.

    Returns "" when the label should be discarded; the caller falls back
    to the work-level locator (`¶N` only, no heading prefix).
    """

    cleaned = _LETTER_SPACED_RUN_RE.sub("", label)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" :,;.-—")
    if not cleaned:
        return ""
    if _is_likely_front_matter(cleaned):
        return ""
    return _smart_title_case(cleaned)
