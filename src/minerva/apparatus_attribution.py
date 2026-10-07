"""Who wrote an apparatus chunk (#710).

A footnote in Shorey's *Republic* is Shorey's text, and a citation in it is
Shorey's citation. Retrieval already says so (``retrieve.format_locator``);
refs did not, and credited 1,161 editors' and translators' citations to
Plato, Aristotle, Hegel and Cicero. The owner decision (2026-10-07) was to
relabel rather than filter: ``chunks.attributed_to`` holds the chunk's real
author, NULL for the work author's own text, and every view that credits a
citation to a source author reads ``COALESCE(c.attributed_to, works.author)``.

The name comes from the edition's responsible party, cleaned out of the
bibliography blob the TEI header gives (``clean_responsible``), unless the
source file is listed in :data:`ATTRIBUTION_OVERRIDES` — the cases where that
blob names no person, the wrong person, or the host author. Each override
records the evidence it was read from.
"""

from __future__ import annotations

import re

from .block_types import APPARATUS_TYPES

# Credited when no person can be named. Never the host author: crediting the
# work's author is exactly the misattribution this module removes.
UNIDENTIFIED_EDITOR = "unidentified editor"

# Source file → the person who wrote that file's apparatus. Only for files
# whose bibliography does not name them; everything else is derived.
ATTRIBUTION_OVERRIDES: dict[str, str] = {
    # Perseus header: <monogr><title> is the book title; the translator is
    # in <respStmt><name>Thomas Wentworth Higginson</name>.
    "discourses_en.xml": "Thomas Wentworth Higginson",
    # Title page: "THE TEXT REVISED AND EXPLAINED BY JAMES S. REID" (#730).
    "academica_en.txt": "James S. Reid",
    # Cambridge 1991 edition, "Editor's Notes": Allen W. Wood edited,
    # H. B. Nisbet translated; the notes are the editor's.
    "elements_phil_of_right_eng_editors_notes.html": "Allen W. Wood",
    # Diels's apparatus. His Greek editions carry translator "(Original)"
    # and an edition named after the work ("Fragments (DK 22)").
    "diefragmentederv12diel_hocr_searchtext.txt": "Hermann Diels",
    # The apparatus is the e-text's transcriber's notes and contents list;
    # the translator field says "Thomas Hobbes".
    # Perseus spells this volume's translator "Harold North Fowler" and
    # the others "Harold N. Fowler"; one person, one name.
    "perseus_01_euthyphro_apology_crito_phaedo_en.xml": "Harold N. Fowler",
    "leviathan.txt": "Project Gutenberg transcriber",
    "philosophical_rudiments.txt": "Project Gutenberg transcriber",
}

_TRANSLATED_BY_RE = re.compile(
    r"(?:translated by|English Translation by|Translation by|trans\.?\s*by)\s+(.+)$", re.I
)
# Leading initials ("J. Bywater") are taken whole: without them the name
# group needed a second character before the first ".", failed on every
# initialled editor, and the whole blob passed as an "already clean" name.
_EDITED_BY_RE = re.compile(r"\bed(?:ited by|\.)\s+((?:[A-Z]\.\s*)*[A-Z][^.,;]+)")
_PLACEHOLDERS = frozenset({"(Original)", "(uncredited)"})


def clean_responsible(blob: str | None) -> str | None:
    """Pull a clean translator/editor name from a source-bibliography blob,
    e.g. 'Plato in Twelve Volumes, Vol. 8 translated by W.R.M. Lamb.' →
    'W.R.M. Lamb'. None when no name is recoverable (caller falls back to a
    bare 'editorial note' label), as for an original-language edition,
    whose translator field is the placeholder '(Original)'."""
    if not blob or blob in _PLACEHOLDERS:
        return None
    m = _TRANSLATED_BY_RE.search(blob)
    if m:
        name = re.split(r";|\bIntroduction\b|\bin (?:two|three) volumes", m.group(1))[0]
        return name.strip(" .,") or None
    m = _EDITED_BY_RE.search(blob)
    if m:
        return "ed. " + m.group(1).strip(" .,")
    # Already a clean name (e.g. "Wood / Nisbet"), not a bibliography blob.
    if len(blob) <= 50 and "Volume" not in blob and ":" not in blob:
        return blob.strip(" .,") or None
    return None


def attribute_chunk(
    *,
    block_type: str | None,
    author: str,
    source_file: str,
    responsible: str | None,
) -> str | None:
    """The chunk's real author, or None when it is the work author's own text.

    ``responsible`` is the translator for a translation and the editor's
    name for an edition, or None/"(Original)" when the source names nobody.
    """
    if block_type not in APPARATUS_TYPES:
        return None
    if block_type == "spurious":
        # Diels did not write the fragments he judged doubtful or forged,
        # and nobody knows who did — so neither he nor the author is named.
        return f"{author} (doubtful or spurious)"
    name = ATTRIBUTION_OVERRIDES.get(source_file) or clean_responsible(responsible)
    if not name or _is_host(name, author):
        return UNIDENTIFIED_EDITOR
    return name


def _is_host(name: str, author: str) -> bool:
    """'Thomas Hobbes' is Hobbes: compare on the author's surname."""
    tokens = name.replace(".", " ").split()
    return name == author or (bool(tokens) and tokens[-1] == author.split()[-1])
