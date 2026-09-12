"""Generic ingest engine for local PDF / EPUB / HTML works.

Sister to `tei.py` (which handles Perseus TEI XML). Both emit
`tei.Chunk`s so the rest of the pipeline (`ingest.py`, `store.py`,
`retrieve.py`, `agent.py`) stays unchanged.

Files are looked up by name in a `find_work` callable supplied by
the caller (defaults to `hegel_works.find_work`; see also
`kant_works.find_work`). Each work declares a locator strategy:

* ``"section"``   — split on `§N` markers (e.g. Hegel's Philosophy of Right)
* ``"paragraph"`` — split on `\\nN. ` paragraph numbering (e.g. Pinkard's PhG)
* ``"chapter"``   — split on heading-shaped lines + sequential paragraph
                    index inside each heading; works for narrative texts
                    and zeno.org-style HTML dumps
* ``"kant_ab"``   — Kant A/B marginal pagination (Cambridge KrV)

For zeno.org HTML dumps, `<!-- ZENO_PAGE: /path -->` markers give us
deterministic chapter boundaries; we skip the regex heuristics in
that case.

Layout
------
* :mod:`.text_repair` — pre-split heuristics (cross-ref repair,
  bibliography detection).
* :mod:`.split_paragraphic` — the generic section / paragraph /
  chapter splitters.
* :mod:`.split_kant` — Kant A/B splitter + Roman-numeral OCR demangle.
* :mod:`.split_zeno` — zeno.org HTML dispatcher.
* :mod:`.pipeline` — `parse_file` / `parse_dir` driver + splitter
  dispatch table.

The names re-exported below are reached by tests and by
``ingest.py``; new code should import directly from the relevant
submodule.
"""

from __future__ import annotations

# Heading-cleaning helpers live in `..heading_clean` and PDF / EPUB /
# HTML extractors in `..corpus_extract`. Re-exported here for the same
# reason the splitters are: keeping the test-facing surface stable as
# the internal layout evolved.
from ..corpus_extract import (  # noqa: F401
    _KERNING_FUSION_THRESHOLD,
    IngestDepsMissing,
    _detect_page_chrome,
    _extract_pdf_page_lines,
    _fuse_kerned_words,
    extract_epub,
    extract_html,
    extract_ocr_pages,
    extract_pdf,
)
from ..heading_clean import (  # noqa: F401
    _EDITORIAL_PHRASES,
    _FRONT_MATTER_KEYWORDS,
    _LETTER_SPACED_RUN_RE,
    _ROMAN_RE,
    _TITLE_LOWER,
    _VOLUME_PREFIX_RE,
    _clean_heading_label,
    _is_editorial_heading,
    _is_garbled_letter_spacing,
    _is_label_too_short,
    _is_likely_front_matter,
    _is_skipped_for_work,
    _is_title_page_artifact,
    _smart_title_case,
    _surnames_for,
)
from .pipeline import parse_dir, parse_file  # noqa: F401
from .split_kant import (  # noqa: F401
    _KANT_AB_CHAPTER_RE,
    _KANT_AB_COMBO_RE,
    _KANT_AB_MARKER_RE,
    _ROMAN_MISREAD_FIXES,
    _demangle_roman_misreads,
    _norm_ab_marker,
    split_by_kant_ab,
)
from .split_paragraphic import (  # noqa: F401
    _HEADING_RE,
    _PARAGRAPH_RE,
    _SECTION_MIN_BODY,
    _SECTION_RE,
    _emit,
    _in_section_range,
    _merge_continuation_headings,
    _split_chapter_block,
    split_by_chapter,
    split_by_fable,
    split_by_paragraph,
    split_by_section,
)
from .split_zeno import (  # noqa: F401
    _ZENO_MARKER,
    _derive_zeno_heading,
    split_zeno_pages,
)
from .text_repair import (  # noqa: F401
    _BIB_AUTHOR_RE,
    _BIB_CITY_YEAR_RE,
    _CROSSREF_OPENERS_RE,
    _looks_like_bibliography,
    _repair_crossref_linebreaks,
)
