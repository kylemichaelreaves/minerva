"""Generic per-work configuration shared by all author-specific WORKS tables.

The original Hegel-only design lived in `hegel_works.HegelWork`. As we
added Kant (and could add others) the dataclass became generic — its
`corpus`, `author`, and `lang` fields override the Hegel defaults — so it
moved here. `hegel_works.py` and `kant_works.py` import `CorpusWork` from this
module and define their author-specific `WORKS` tuples.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable


@dataclasses.dataclass(frozen=True)
class CorpusWork:
    code: str  # short identifier, e.g. "pr", "phg", "krv_de"
    title: str  # canonical work title for citations
    translator: str
    edition_year: str  # year of the translation (or "1820" / "(Original)")
    filenames: tuple[str, ...]  # any of these in the corpus directory matches
    fmt: str  # "pdf" | "epub" | "html" (informational; dispatch is by extension)
    locator: str  # "section" | "paragraph" | "chapter"
    # Hard cap for `paragraph` / `section` locators: any detected number
    # above this is rejected as a spurious match against page numbers or
    # footnote ordinals. None disables the cap.
    max_section: int | None = None
    # Lower bound for the same — useful when a partial-volume edition
    # might catch low numbers from OCR noise or front-matter cross-refs.
    min_section: int | None = None
    # ISO 639-3 language code stored on every chunk (default English;
    # override for German/Greek/etc. originals).
    lang: str = "eng"
    # Corpus + author for the chunk; override for non-Hegel works.
    corpus: str = "hegel"
    author: str = "Hegel"
    # Per-work heading overrides. Chapter labels (after the standard
    # heading normalization) matching any of these are dropped, even
    # if the global editorial-heading filter would keep them. Match is
    # substring on the alpha-only lowercase form, so OCR / spacing
    # variants of the listed term still hit.
    #
    # Used for translator-or-editor prefaces in editions where "Preface"
    # is apparatus rather than Hegel's own Vorrede — too risky to drop
    # globally (Hegel writes plenty of his own).
    skip_headings: tuple[str, ...] = ()
    # Front-matter headings to capture under `locator="section"`. The
    # default §-splitter drops everything before the first `§N` marker,
    # which silently loses Hegel's own Preface / Introduction in
    # §-numbered editions. When this tuple is set (e.g. `("Preface",)`
    # for the Nisbet/Wood PR), the splitter looks for each listed
    # heading as a standalone Title-case line in the prefix and emits
    # paragraph chunks under `book="<heading>"`, `section="<heading>,
    # ¶N"`. Editorial front matter (Cambridge series prose, copyright
    # page) before the first listed heading is skipped.
    front_matter_headings: tuple[str, ...] = ()
    # Page-range routing for multi-work PDFs. When set to ``(start,
    # end)`` (1-indexed inclusive page numbers), the PDF extractor
    # restricts text to that range, letting one physical PDF — e.g.
    # the Cambridge "Practical Philosophy" Gregor omnibus — produce
    # multiple CorpusWork rows. Each major work declares its own page span
    # in ``kant_works.WORKS``. Editorial content (publisher's
    # preface, editorial notes, glossary, indexes) is excluded by
    # the simple expedient of NO CorpusWork pointing at those pages.
    pages: tuple[int, int] | None = None
    # Citation-system override for the ``works.citation_system``
    # column when this CorpusWork is materialized. Most works fall through
    # to the corpus default (see ``runtime_helpers.citation_system_for_corpus``),
    # but a few — notably the Critique of Pure Reason, which is
    # canonically cited by Kant's A (1781) and B (1787) edition page
    # numbers — want a different scheme. Set per-CorpusWork to pin the
    # value; leave ``None`` to inherit from the corpus default.
    citation_system: str | None = None
    # Structural role stamped on every chunk this work emits (paragraphic
    # splitters only). Used for editorial-apparatus works whose entire
    # content is set-apart material — e.g. the Hegel PR editor's-endnotes
    # work sets ``block_type="note"`` so its chunks attribute to the
    # editor, not Hegel. Leave ``None`` for ordinary body works.
    block_type: str | None = None


def filename_index(works: Iterable[CorpusWork]) -> dict[str, CorpusWork]:
    """Map each work's ``filenames`` entry to the work row."""

    out: dict[str, CorpusWork] = {}
    for w in works:
        for fn in w.filenames:
            out[fn] = w
    return out


def make_find_work(
    works: Iterable[CorpusWork],
    *,
    case_insensitive: bool = False,
) -> Callable[[str], CorpusWork | None]:
    """Return a ``find_work(filename)`` callable for a ``WORKS`` tuple."""

    works_tuple = tuple(works)
    if case_insensitive:

        def find_work(filename: str) -> CorpusWork | None:
            lower = filename.lower()
            for w in works_tuple:
                if any(c.lower() == lower for c in w.filenames):
                    return w
            return None

        return find_work

    by_fn = filename_index(works_tuple)

    def find_work(filename: str) -> CorpusWork | None:
        return by_fn.get(filename)

    return find_work
