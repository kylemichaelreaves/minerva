#!/usr/bin/env python3
"""One-shot cleanup for the Boulainvilliers source texts.

After ingest, the chunks were unreadable because of three layered
OCR artifacts that the original fetcher didn't normalize:

1. **Long-s** (U+017F ``ſ``) — the medial-s glyph the 18th-c
   printer used everywhere. Survived through Google Books OCR
   in some volumes, especially the EPUB-derived Essai. Maps to
   plain ``s``.
2. **Unicode ligatures** in the U+FB00–FB06 range — ``ﬀ ﬁ ﬂ ﬃ ﬄ ﬅ``.
   The Gallica-derived EPUB encodes typographic ligatures as
   atomic codepoints; modern French expects them decomposed.
3. **OCR margin debris** — the Lettres scan has trailing ``^^H``
   ``^^|`` ``^^B`` markers on every line (page-edge garbage); the
   Essai EPUB has multi-line runs of dots and stray Latin-1
   characters from image-as-text rendering between actual prose
   paragraphs.

We also collapse hyphenation across line breaks (``ruppri-\\nmer``
→ ``ruppri-mer`` becomes ``ruppri-mer`` joined; the chunker's
paragraph splitter then sees clean sentences). And we drop lines
that are predominantly non-letter characters (image-glyph soup).

Re-runnable: keeps idempotent properties — running twice gives the
same output as running once. Safe to call after a fetcher refresh.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Allow `import minerva.*` when running this script directly from the
# repo root (`uv run python scripts/clean-boulainvilliers-texts.py`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from minerva.textnorm import normalize_ligatures as _normalize_ligatures

REPO_ROOT = Path(__file__).resolve().parent.parent
BOULAINVILLIERS_DIR = REPO_ROOT / "data" / "boulainvilliers"

# Substring runs the OCR shipped as margin / page-edge noise.
# Each pattern is anchored to where the noise actually fires —
# the Lettres ``^^H`` etc. is right-margin; we strip these BEFORE
# the trailing-whitespace trim so the line below it becomes empty
# and gets collapsed by the blank-line dedup.
MARGIN_NOISE = re.compile(r"\s*\^\^[A-Z|]\s*$")


# Image-glyph-soup line predicate. A "line" qualifies as garbage
# when fewer than 40 % of its non-whitespace characters are
# Letters (Unicode L*). Real French prose runs ≥ 80 % letters
# even with punctuation — 40 % is permissive enough to keep verse
# but aggressive enough to drop the dots-and-arrows soup the
# Essai EPUB ships between paragraphs.
def _is_glyph_soup(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    # Pure-punctuation marker lines (page rules, ornamental
    # dividers) are noise. Also lines that are 80%+ digits +
    # punctuation (publisher's pagination scraps).
    letters = sum(1 for c in s if c.isalpha())
    if len(s) < 4:
        return False  # too short to confidently classify
    return letters < 0.40 * len(s)


def _join_hyphenation(text: str) -> str:
    """Merge hyphen-broken words across line endings AND across the
    spaces that html-extracted text sometimes leaves between them.

    ``ruppri-\\nmer`` → ``rupprimer``. The 18th-c print breaks any
    word at the right margin with ``-\\n``; without fixing, the
    chunker emits two half-words that lemmatize as bogus tokens.

    Gallica's HTML "Text View" sometimes collapses the line break
    into a single space (when paragraph-aware extraction joins
    inline spans), leaving the visible artifact ``inftan- ces``.
    The second sub catches that shape too. Both only fire when the
    continuation starts with a lowercase letter — uppercase signals
    a new sentence / heading.
    """

    text = re.sub(r"(\w)-\n([a-zàâéèêëîïôöùûüç])", r"\1\2", text)
    text = re.sub(r"(\w)- ([a-zàâéèêëîïôöùûüç])", r"\1\2", text)
    return text


_FRENCH_DICT = None


def _french_dict():
    """Lazy-init pyspellchecker's French word list. We do this once
    per process so the ~600 K-line dictionary doesn't reload per
    token."""

    global _FRENCH_DICT
    if _FRENCH_DICT is None:
        from spellchecker import SpellChecker

        _FRENCH_DICT = SpellChecker(language="fr")
    return _FRENCH_DICT


def _fix_medial_f_to_s(text: str) -> str:
    """Repair the 18th-c medial-s OCR misread.

    Google Books OCR routinely transcribed the long-s glyph (``ſ``)
    as a regular Latin ``f`` because the two share an ascender +
    cross-stroke. Result: ``Histoire`` → ``Hiftoire``, ``Assemblées``
    → ``Affemblées``, ``consentement`` → ``confentement``,
    ``nécessaire`` → ``néceffaire``. These are unreadable to a
    modern French reader and also poison the lemmatizer.

    Repair is dictionary-guided: for every word containing a medial
    ``f`` (not word-initial — those are usually genuine), we generate
    candidate spellings by swapping ``ff`` → ``ss`` and ``f`` → ``s``
    in various combinations, and ask pyspellchecker's French
    dictionary which form is real. If exactly one candidate is in
    the dict and the original isn't, we swap. This avoids the false
    positives a blind regex pass would hit (``différent`` → ``dissérent``,
    ``effet`` → ``esset``, ``enfant`` → ``ensant`` would all be
    wrong; the dict knows ``différent`` / ``effet`` / ``enfant``
    are real French and leaves them alone).
    """

    sp = _french_dict()

    def _try_candidates(word: str) -> str:
        # Skip word-initial f, all-cap acronyms, and short stubs.
        if len(word) < 3 or word.lower()[0] == "f":
            return word
        if not any(ch in word for ch in "fF"):
            return word
        # Generate candidates: replace every combination of f-clusters
        # with s-equivalents. For each medial-f position, the swap can
        # be f→s or ff→ss; we enumerate the 2^k cluster choices.
        # In practice, words have ≤ 3 medial-f positions, so the
        # enumeration cap is tiny.
        lower = word.lower()
        positions: list[tuple[int, int]] = []
        i = 0
        while i < len(lower):
            if lower[i] != "f":
                i += 1
                continue
            # word-initial f stays as f (the lower[0]=='f' guard
            # catches the leading-position case at the outer level,
            # but a word with an internal "f" preceded by f-initial
            # like "Ffrancesco" would loop; we don't expect those).
            if i == 0:
                i += 1
                continue
            run_end = i
            while run_end < len(lower) and lower[run_end] == "f":
                run_end += 1
            positions.append((i, run_end))
            i = run_end
        if not positions:
            return word
        # Enumerate 2^len(positions) variants — small (usually 2-8).
        n = len(positions)
        best = word
        best_score = -1  # higher = better dictionary match
        # Score the original first.
        if word.lower() in sp:
            best_score = 1
            best = word
        for mask in range(1, 1 << n):
            variant = list(word)
            for idx, (start, end) in enumerate(positions):
                if (mask >> idx) & 1:
                    for k in range(start, end):
                        # Preserve case of the original character.
                        variant[k] = "S" if word[k].isupper() else "s"
            candidate = "".join(variant)
            if candidate.lower() in sp:
                # Prefer candidates that swap MORE (closer to long-s
                # interpretation), but only beat the original if it's
                # also in dict. Tied candidates: prefer the highest
                # swap count.
                swap_count = bin(mask).count("1")
                if swap_count > best_score:
                    best_score = swap_count
                    best = candidate
        return best

    # Tokenise on word boundaries that preserve apostrophes inside
    # words (l'eft → ["l", "'", "eft"]). Each alphabetic-only token
    # gets the candidate-search treatment.
    def _repl(m: re.Match[str]) -> str:
        return _try_candidates(m.group(0))

    return re.sub(r"[A-Za-zÀ-ÿ]+", _repl, text)


# Boulainvilliers-specific running-header patterns. Each pattern is a
# complete-line regex (the entire line content); matches are stripped.
# Added piecemeal as samples surfaced them in the corpus.
_RUNNING_HEADERS = re.compile(
    r"^\s*(?:"
    # "Lettres sur les Anciens" / "Lettres sur les Anciens Parlemens"
    r"LETTRES?\s+sur\s+les\s+Anciens(?:\s+Parlemens)?(?:\s+\w+)?"
    # "PARLEMENS DE FRANCE" / "Parlemens de France"
    r"|PARLEMENS\s+de\s+France\s*\.?"
    # "Lettre N" / "LETTRE N" / "LETT. N" / "LETTREI" etc.
    r"|LETTRE?\.?\s*[IVX]+\s*\.?,?"
    # "LETT.II," / "XBPP.II." / "LETTREI." / "TBPP.II."
    r"|[A-Z]{2,5}\.?\s*[IVX]+\s*\.?,?"
    # "Tome L A" / "Tome PREMIER" / "Tome II"
    r"|Tome\s+(?:[IVX]+|PREMIER|SECOND|TROISIEME|L\s*A)"
    # "Differtation sur la Noblesse" / "Dissertation sur la Noblesse"
    r"|(?:Diff|Diss)ertation\s+sur\s+la\s+Noblesse\s*'?\.?"
    # Standalone "TABLE" / "PRÉFACE" / "INTRODUCTION"
    r"|(?:TABLE|TABLE\s+DES\s+TITRES|PR[ÉE]FACE|INTRODUCTION)\s*\.?"
    # "Mémoires Historiques" running header
    r"|M[ée]moires\s+Historiques?\s*\.?"
    # "Histoire de France" running header
    r"|Histoire\s+de\s+France\s*\.?"
    r")\s*$",
    re.IGNORECASE,
)


# Pure-page-number lines. Includes:
# * Arabic digits: "108", "I 09" (OCR-split), "108."
# * Roman numerals upper/lower: "XIV", "xiii", "iv", "IV."
# * Mixed (Gallica's catalog page markers): "p. 12", "Pag. 5"
_PAGE_NUMBER_LINE = re.compile(
    r"^\s*(?:"
    r"\d{1,4}\.?"  # bare arabic
    r"|[IVXLCDM]{1,8}\.?"  # uppercase roman
    r"|[ivxlcdm]{1,8}\.?"  # lowercase roman
    r"|[Pp]a?g\.?\s*\d+\.?"  # "p. 12" / "Pag. 12"
    r"|\d+\s*[°º]\.?"  # "1°" / "2º."
    r"|[IVX]+\s+\d+"  # split roman+arabic
    r")\s*$"
)


def _is_column_edge_garbage(line: str) -> bool:
    """Detect lines that are mostly OCR column-edge debris — runs of
    single-letter tokens separated by spaces (``I â à 'S e e p it 3 a 4 j r $``).
    Such lines are page-margin OCR scraps that the body-text reader
    never wanted.

    A line qualifies as column-edge garbage when ≥ 70% of its tokens
    are 1-2 chars long AND the total token count is ≥ 5 (short
    legitimate sentences pass).
    """

    s = line.strip()
    if len(s) < 8:
        return False
    tokens = s.split()
    if len(tokens) < 5:
        return False
    short = sum(1 for t in tokens if len(t) <= 2)
    return short / len(tokens) >= 0.70


def _strip_caret_artifacts(text: str) -> str:
    """Drop tokens that contain a stray ``^`` (Mezt^ ray, Pe^,
    Ckctrlema^ne). These are OCR column-edge artifacts where the page-
    rule mark intersected a character; the resulting token is unreadable
    and never lemmatises cleanly. Replace with a space-collapsed gap so
    the surrounding prose flows."""

    return re.sub(r"\S*\^\S*", "", text)


# Running-header patterns that appear MID-LINE (Gallica's HTML
# extraction collapses paragraph runs, so these end up inline).
# Text-level substitutions, not line-level filters.
#
# Critically, the running-head regex must REQUIRE a literal dot or
# specific spelling — earlier the loose
# ``[A-Z]{2,5}\.?\s*[IVX]{1,4}`` matched plain French words like
# ``ceux`` (``ceu`` + ``x``) and ``lui`` (``lu`` + ``i``) under
# IGNORECASE, destroying legitimate prose. The current patterns
# all anchor on either a literal dot or a specific source phrase.
_INLINE_RUNNING_HEADERS = re.compile(
    r"(?:"
    # Per-letter running heads with literal dots: ``LETT.II,``
    # ``XBPP.II.`` ``LETTREI.`` etc. 2-5 ASCII uppercase + dot +
    # 1-4 Roman numerals (case-sensitive — IGNORECASE removed).
    r"\b[A-Z]{2,5}\.[IVX]{1,4}[.,]?(?=\s|$)"
    # Specific page-header phrases (the running heads embedded by
    # Gallica). Case-insensitive variants are common in OCR output.
    r"|\bLETTRES?\s+sur\s+les\s+Anciens(?:\s+Parlemens)?\b"
    r"|\bPARLEMENS\s+(?:de|DE)\s+France\b"
    # Tome marker variants
    r"|\bTome\s+(?:[IVX]+|PREMIER|SECOND|TROISIEME|L\s*A)\b"
    r")",
)


def _strip_inline_running_headers(text: str) -> str:
    """Strip running headers that ended up mid-paragraph after HTML
    extraction joined inline spans. Substitutes a single space so
    the surrounding prose doesn't run together."""

    return _INLINE_RUNNING_HEADERS.sub(" ", text)


def _split_run_on_words(text: str) -> str:
    """Insert spaces in run-on tokens that the dictionary recognises as
    two consecutive French words.

    OCR sometimes drops the space between adjacent words: ``sensiblepar``,
    ``Arrierefiefs``, ``tefuis``, ``oude``. We try every possible split
    point on each unfamiliar token of length ≥ 6 and accept the split
    only when BOTH halves are real French words. The dict check makes
    this safe — words like ``avantageuses``, ``conférence``, ``régulier``
    that aren't run-ons stay intact because no valid split exists.

    The minimum-half-length of 3 stops false positives on short common
    fragments (``de``, ``la``, ``il``) that would otherwise match
    anywhere.
    """

    sp = _french_dict()

    def _try_split(word: str) -> str:
        if len(word) < 6:
            return word
        # Skip if the original is already in dict.
        lower = word.lower()
        if lower in sp:
            return word
        # Skip uppercase tokens (likely proper nouns / acronyms).
        if word.isupper():
            return word
        # Skip words containing ``f`` — those are very likely
        # long-s OCR misreads (``fervice`` for ``service``,
        # ``fanté`` for ``santé``) that the f→s pass either
        # already handled or couldn't fix because the dict didn't
        # know the 18th-c form. Either way, splitting them as
        # run-on words almost always yields nonsense — ``fervice``
        # → ``fer vice`` (iron vice), ``foulagement`` →
        # ``foulage ment``, ``fubftituer`` → ``fub stituer``. Leave
        # them unsplit so the reader can still recognise the
        # long-s misread.
        if "f" in lower:
            return word
        # Try every interior split; accept the FIRST that gives two
        # real words BOTH of length ≥ 4 (avoids breaking on tiny
        # function words like ``de``, ``la``, ``il``). The leftmost
        # split tends to be the right one (French lexicon is
        # dominated by 4-10-char words).
        for i in range(4, len(word) - 3):
            left, right = lower[:i], lower[i:]
            if left in sp and right in sp:
                # Preserve case: capital first letter on left if
                # the original was capitalised.
                a = word[:i]
                b = word[i:]
                return f"{a} {b}"
        return word

    return re.sub(r"[A-Za-zÀ-ÿ]+", lambda m: _try_split(m.group(0)), text)


def clean_text(raw: str, *, drop_glyph_soup: bool = True) -> str:
    text = _normalize_ligatures(raw)
    text = _join_hyphenation(text)
    text = _fix_medial_f_to_s(text)
    text = _strip_caret_artifacts(text)
    text = _strip_inline_running_headers(text)
    text = _split_run_on_words(text)
    out_lines: list[str] = []
    for line in text.split("\n"):
        # Strip margin debris first, then trailing whitespace.
        line = MARGIN_NOISE.sub("", line)
        line = line.rstrip()
        if drop_glyph_soup and _is_glyph_soup(line):
            continue
        if _PAGE_NUMBER_LINE.match(line):
            continue
        if _RUNNING_HEADERS.match(line):
            continue
        if _is_column_edge_garbage(line):
            continue
        # Collapse intra-line multiple spaces (left over from
        # the caret-stripping pass).
        line = re.sub(r" {2,}", " ", line)
        out_lines.append(line)
    text = "\n".join(out_lines)
    # Collapse 3+ consecutive blank lines to 2.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _process_file(path: Path) -> None:
    raw = path.read_text(encoding="utf-8")
    before = len(raw)
    cleaned = clean_text(raw)
    path.write_text(cleaned, encoding="utf-8")
    print(
        f"  {path.name}: {before:,} → {len(cleaned):,} chars",
        file=sys.stderr,
    )


def main() -> int:
    for name in (
        "histoire_anc_gouv_fra.txt",
        "lettres_parlemens_fra.txt",
        "essai_noblesse_fra.txt",
    ):
        p = BOULAINVILLIERS_DIR / name
        if not p.is_file():
            print(f"  {name}: SKIP (missing)", file=sys.stderr)
            continue
        _process_file(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
