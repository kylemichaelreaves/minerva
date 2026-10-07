#!/usr/bin/env python3
"""Cleanup for the Boulainvilliers source texts.

Runs over the downloader's output (``perseus/download_boulainvilliers.py``
writes the Histoire and the Lettres) and, per paragraph, inside
``scripts/extract-essai-pdf.py`` for the Essai. It repairs:

1. **Long-s** (U+017F ``ſ``) and **Unicode ligatures** (U+FB00–FB06),
   via `minerva.textnorm.normalize_ligatures`.
2. **The long-s read as ``f``** (``Hiftoire``), by a dictionary-guided
   f→s swap (needs ``pyspellchecker``).
3. **OCR debris** — tokens with a stray ``^``, the Lettres' ``^^H``
   right-margin markers, whole lines that are page numbers, glyph soup
   (fewer than 40 % letters) or a running head.

It does not join words divided at the line end, split run-together words
or drop "column-edge" lines of short words: the first is done
compound-aware by `corpus/ocr_reflow` at ingest for the two works that
reach this script line by line, and the other two removed far more body
text than debris (#739: 87 of 103 column-edge drops in the Lettres were
body text; the splitter wrote ``Angle terre`` 89 times). The old join
also closed up a hyphen followed by a space mid-line (``inftan- ces``);
the reflow does not, so that shape now reaches the index as printed.

Idempotent: cleaning its own output changes nothing, so re-running it
over ``data/boulainvilliers`` is safe. (Before #739 it was not — the
hyphen join kept joining across the gaps it had made.)

The f→s pass needs ``pyspellchecker``, declared as the ``ocr-clean`` extra
(#740; it used to be imported without being declared anywhere)::

    uv run --extra ocr-clean python scripts/clean-boulainvilliers-texts.py

Role: oneoff
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

    The word is judged whole even when the printer divided it at the line
    end (``mau-`` / ``vaifes``): the fragments alone are either no word or
    the wrong one (``ef-`` / ``fectivement`` would become ``es-``). The
    hyphen and line break stay where they are, for `corpus/ocr_reflow` to
    rejoin at ingest.
    """

    sp = _french_dict()

    def _repl(m: re.Match[str]) -> str:
        left, sep, right = m.group(0).partition("-\n")
        fixed = _repair_long_s(left + right, sp)
        return fixed[: len(left)] + sep + fixed[len(left) :]

    return _WORD_OR_DIVIDED_WORD.sub(_repl, text)


#: A word, or a word divided at the line end (``mau-\nvaifes``). Letters only,
#: so apostrophes split tokens (``l'eft`` → ``l``, ``eft``).
_WORD_OR_DIVIDED_WORD = re.compile(r"[A-Za-zÀ-ÿ]+(?:-\n[a-zà-ÿ][A-Za-zÀ-ÿ]*)?")


def _medial_f_runs(lower: str) -> list[tuple[int, int]]:
    """The ``(start, end)`` of each run of ``f`` after the first letter."""

    return [(m.start(), m.end()) for m in re.finditer(r"f+", lower) if m.start() > 0]


def _swapped(word: str, positions: list[tuple[int, int]], mask: int) -> str:
    """*word* with the runs selected by *mask* turned to ``s``, keeping case."""

    variant = list(word)
    for idx, (start, end) in enumerate(positions):
        if (mask >> idx) & 1:
            for k in range(start, end):
                variant[k] = "S" if word[k].isupper() else "s"
    return "".join(variant)


def _repair_long_s(word: str, sp) -> str:
    """The dictionary's best reading of *word* with ``f`` runs read as ``s``.

    Word-initial ``f`` is left alone (usually genuine). Every combination of
    medial runs is tried — ``2**k`` variants, k rarely above 3 — and the
    dictionary form that swaps the most runs wins; the original stands if
    it is a word and no variant swapping two or more runs is.
    """

    if len(word) < 3 or word[0] in "fF":
        return word
    positions = _medial_f_runs(word.lower())
    if not positions:
        return word
    best, best_score = word, (1 if word.lower() in sp else -1)
    for mask in range(1, 1 << len(positions)):
        candidate = _swapped(word, positions, mask)
        swap_count = bin(mask).count("1")
        if swap_count > best_score and candidate.lower() in sp:
            best, best_score = candidate, swap_count
    return best


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
    # The Lettres' per-letter heads as the OCR mangles them: "Lett.V.",
    # "LiTT. V,", "Utt. IX.", "Tr.IX.". A dot after the letters and an
    # upper-case numeral, case-sensitively — the dotless form this replaced
    # matched "Roi." (Ro + i), "Bailli." and "Louis XI" (#739).
    r"|(?-i:[A-Za-z]{2,5}\.\s*[IVX]{1,4}\s*[.,]?)"
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


def _keep_line(line: str, drop_glyph_soup: bool) -> bool:
    if drop_glyph_soup and _is_glyph_soup(line):
        return False
    return not (_PAGE_NUMBER_LINE.match(line) or _RUNNING_HEADERS.match(line))


_MIDLINE_HYPHEN = re.compile(r"(\w)- ([a-zàâéèêëîïôöùûüç])")


def clean_text(raw: str, *, drop_glyph_soup: bool = True) -> str:
    text = _normalize_ligatures(raw)
    # A word split mid-line (`Mai- fon`, left by the PDF span join) is closed
    # up here; the ingest reflow only rejoins a hyphen at a line END. Before
    # the f→s pass, so the joined word is judged whole (batch 13m).
    text = _MIDLINE_HYPHEN.sub(r"\1\2", text)
    # Before the line filters, so a running head misread `Hiftoriques`
    # still matches them.
    text = _fix_medial_f_to_s(text)
    text = _strip_caret_artifacts(text)
    text = _strip_inline_running_headers(text)
    out_lines: list[str] = []
    for raw_line in text.split("\n"):
        # Strip margin debris first, then trailing whitespace.
        line = MARGIN_NOISE.sub("", raw_line).rstrip()
        if _keep_line(line, drop_glyph_soup):
            # Collapse intra-line multiple spaces (left over from
            # the caret-stripping pass).
            out_lines.append(re.sub(r" {2,}", " ", line))
    text = "\n".join(out_lines)
    # Collapse 3+ consecutive blank lines to 2.
    text = re.sub(r"\n{3,}", "\n\n", text)
    # And after them: stripping debris that stood at a line break
    # (`con- ^^^` / `fommation`) is what brings a divided word's halves
    # together, and only then can it be judged whole. The mid-line join runs
    # again for the same reason: `cbamtt- ^^ foibies` only becomes
    # `cbamtt- foibies` once the debris is gone.
    return _fix_medial_f_to_s(_MIDLINE_HYPHEN.sub(r"\1\2", text))


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
