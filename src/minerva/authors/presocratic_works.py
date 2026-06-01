"""Per-philosopher configuration for the pre-Socratic ingest.

Source: *Die Fragmente der Vorsokratiker*, Hermann Diels, 3rd edition,
1912 (volume 1), OCR'd from the archive.org scan. The 3rd edition
predates Walther Kranz's collaboration — chapter numbers in the
source differ from modern DK (Kranz 1951, 6th ed., which is the
universal scholarly citation standard today).

This module maintains both:

* the source's 1912 chapter number — used by the parser to match
  chapter-heading lines in the OCR text (where the integer is
  sometimes mis-recognized; primary match is by name);
* the modern DK chapter number — used in the canonical
  ``section`` locator written to ``chunks.section`` (e.g.,
  ``"22 B 1"`` for Heraclitus's first B-fragment).

Phase 1 covers the canonical ~12 pre-Socratics — the figures
responsible for >90% of philosophical references to the school.
Minor figures and Volume 2 (Atomists, Sophists) are deferred to
Phase 2 expansions of this table.

Each philosopher gets TWO ``CorpusWork`` entries: a Greek edition
(``lang="grc"``, ``translator="(Original)"``) and Diels's German
translation (``lang="deu"``, ``translator="Hermann Diels"``). Both
share ``corpus="presocratic"`` and ``citation_system="diels_kranz"``;
``store._resolve_work_refs`` links them through one ``works`` row
because Greek is the corpus's original_language and German is a
translation.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork

# (1912_chapter, modern_dk_chapter, source_name_uppercase, canonical_name)
# 1912 numbers verified against the TOC in the OCR source.
# Modern DK numbers are from Kranz 1951 (universal scholarly standard).
_PHASE_1: tuple[tuple[int, int, str, str], ...] = (
    (1,  11, "THALES",       "Thales"),
    (2,  12, "ANAXIMANDROS", "Anaximander"),
    (3,  13, "ANAXIMENES",   "Anaximenes"),
    (4,  14, "PYTHAGORAS",   "Pythagoras"),
    (11, 21, "XENOPHANES",   "Xenophanes"),
    (12, 22, "HERAKLEITOS",  "Heraclitus"),
    (18, 28, "PARMENIDES",   "Parmenides"),
    (19, 29, "ZENON",        "Zeno of Elea"),
    (20, 30, "MELISSOS",     "Melissus"),
    (21, 31, "EMPEDOKLES",   "Empedocles"),
    (46, 59, "ANAXAGORAS",   "Anaxagoras"),
    (51, 64, "DIOGENES",     "Diogenes of Apollonia"),
)


_SOURCE_FILE = "diefragmentederv12diel_hocr_searchtext.txt"


def _make_corpuswork(
    entry: tuple[int, int, str, str], lang: str
) -> CorpusWork:
    _, dk_mod, _, canonical = entry
    return CorpusWork(
        code=f"dk_{dk_mod}_{lang}",
        title=f"Fragments (DK {dk_mod})",
        translator="(Original)" if lang == "grc" else "Hermann Diels",
        edition_year="1912",
        filenames=(_SOURCE_FILE,),
        fmt="txt",
        locator="presocratic",
        lang=lang,
        corpus="presocratic",
        author=canonical,
        citation_system="diels_kranz",
    )


WORKS: tuple[CorpusWork, ...] = tuple(
    _make_corpuswork(e, lang) for e in _PHASE_1 for lang in ("grc", "deu")
)


# Lookup tables used by the parser. The OCR rewrites some chapter
# integers (e.g., 32→92, 38→98), so the parser's primary key is the
# uppercase source name — but it'll cross-check the integer when the
# OCR got it right.
_BY_SOURCE_NAME: dict[str, tuple[int, int, str, str]] = {
    e[2]: e for e in _PHASE_1
}
_BY_1912_CHAPTER: dict[int, tuple[int, int, str, str]] = {
    e[0]: e for e in _PHASE_1
}


def find_by_chapter_heading(
    chapter_int: int | None, source_name: str
) -> tuple[int, int, str, str] | None:
    """Resolve a chapter-heading line (``N. NAME.``) to a Phase-1
    philosopher entry. Match is on NAME only: integer fallback would
    be unsafe because the source's A-fragments include lines like
    ``2. STRABO XIV 8 ...`` (testimonium #2 from Strabo) that
    superficially look like a chapter heading. The OCR keeps Phase-1
    uppercase names intact, so name-only is reliable enough.

    The ``chapter_int`` argument is accepted but unused; kept in the
    signature so future expansions can re-introduce a guarded fallback
    once we have a way to distinguish a chapter heading from a
    fragment citation that uses an ancient author's name.
    """

    return _BY_SOURCE_NAME.get(source_name.upper())
