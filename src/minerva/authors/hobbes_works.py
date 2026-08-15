"""Per-work configuration for Hobbes ingest.

Six works across two languages:

  * ``Leviathan`` — English 1651 (PG #3207) + Latin 1668 (Hobbes's
    self-authored Latin version, distinct text from the English).
    Bilingual edition pair: same ``works.title``, different langs;
    ``store._resolve_work_refs`` threads them through one ``works``
    row with Latin as ``original_language``.
  * ``De Cive`` — Latin 1642 (the original) + English 1651
    ("Philosophical Rudiments concerning Government and Society",
    Hobbes's own self-translation). Same bilingual-pair pattern as
    Leviathan; Latin is original.
  * ``Human Nature`` and ``De Corpore Politico`` — Parts I and II of
    *The Elements of Law Natural and Politic* (1640 manuscript,
    published 1650). Distinct ``works`` rows; English only (no
    canonical Latin parallel).

Sources:

  * English: Project Gutenberg via ``perseus/download_early_modern.py``.
    Leviathan = PG 3207; the two-part Volume 02 of Molesworth's
    English Works = PG 73906 (Philosophical Rudiments); Vol 04 =
    PG 74236 (Human Nature + De Corpore Politico + Of Liberty and
    Necessity, the first two split into separate files at download
    time by a post-process step in ``download_early_modern.py``).
  * Latin: Internet Archive OCR of public-domain editions
    (``leviathansivedem00hobb`` for the 1668 Latin Leviathan;
    ``gri_elementaphilos00ho`` for De Cive) via the dedicated
    ``perseus/download_hobbes_la.py`` script. Parsed by
    ``src/minerva/hobbes_la.py`` because the OCR is noisier than
    Wikisource-transcribed Latin and needs a Molesworth-aware
    chapter-detection state machine.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    # ─── Leviathan ────────────────────────────────────────────────
    # Latin first so it becomes original_language for the works row
    # (`_resolve_work_refs` walks WORKS in order; first chunk to land
    # against the (author, title) pair sets the original_language).
    CorpusWork(
        code="leviathan_lat",
        title="Leviathan",
        translator="(Original)",
        edition_year="1668",
        filenames=("leviathan_lat.txt",),
        fmt="txt",
        locator="hobbes_la",
        lang="lat",
        corpus="hobbes",
        author="Hobbes",
    ),
    CorpusWork(
        code="leviathan_eng",
        title="Leviathan",
        translator="Thomas Hobbes",
        edition_year="1651",
        filenames=("leviathan.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="hobbes",
        author="Hobbes",
    ),
    # ─── De Cive ──────────────────────────────────────────────────
    CorpusWork(
        code="de_cive_lat",
        title="De Cive",
        translator="(Original)",
        edition_year="1642",
        filenames=("de_cive_lat.txt",),
        fmt="txt",
        locator="hobbes_la",
        lang="lat",
        corpus="hobbes",
        author="Hobbes",
    ),
    CorpusWork(
        code="de_cive_eng",
        title="De Cive",
        translator="Thomas Hobbes",
        edition_year="1651",
        filenames=("philosophical_rudiments.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="hobbes",
        author="Hobbes",
        # Two paragraphs clear 8,000 chars in a work whose median is 166:
        # the dedicatory epistle to the Earl of Devonshire (10,709, one
        # paragraph of 153 lines) and §51 (8,151). Neither is dialogue, so
        # both split at sentence ends (#176). The Latin De Cive is
        # deliberately NOT capped — its 18 chapter-sized chunks are the
        # documented OCR trade-off in sources/hobbes_la.py.
        max_paragraph_chars=8000,
    ),
    # ─── Elements of Law (1640) ───────────────────────────────────
    # Two-part 1650 publication; English only.
    CorpusWork(
        code="human_nature",
        title="Human Nature",
        translator="(Original)",
        edition_year="1650",
        filenames=("human_nature.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="hobbes",
        author="Hobbes",
    ),
    CorpusWork(
        code="de_corpore_politico",
        title="De Corpore Politico",
        translator="(Original)",
        edition_year="1650",
        filenames=("de_corpore_politico.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="hobbes",
        author="Hobbes",
    ),
)

find_work = make_find_work(WORKS)
