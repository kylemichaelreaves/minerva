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
  * Latin: Internet Archive OCR of William Molesworth's *Opera
    philosophica quae latine scripsit omnia* (London: Bohn, 1839) —
    vol. III for Leviathan (``thomhobbesmalme02hobbgoog``), vol. II for
    De Cive (``thomhobbesmalmes0002hobb``) — via
    ``perseus/download_hobbes_la.py``, which slices each work out of
    its volume. Parsed by ``src/minerva/sources/hobbes_la.py``, whose
    job is Molesworth's two-column page: the marginal gloss column that
    the OCR linearizes into the body lines.

    ``edition_year`` below is the year of each work's first
    publication (1668 / 1642), not of the Molesworth reprint, matching
    every other Latin original in the corpus.

    Corrected 2026-09-12 (#535): this paragraph previously named
    ``leviathansivedem00hobb`` and ``gri_elementaphilos00ho`` — scans of
    the 1668 and 1704 printings — and described the parser as
    "Molesworth-aware", which it was not; Molesworth was not the source
    then. Those long-s printings are what made the Latin unusable.
    The parser is Molesworth-aware now, and the path here was wrong
    besides (``src/minerva/hobbes_la.py``, missing ``sources/``).
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
        # The e-text's transcriber's notes (14 paragraphs) sit between the
        # title page and the Godolphin dedication (#705).
        editorial_runs=(("TRANSCRIBER’S NOTES ON THE E-TEXT", "TO MY MOST HONOR’D FRIEND"),),
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
        # both split at sentence ends (#176). The Latin De Cive needs no
        # cap: since the Molesworth re-source (#535) it chunks per
        # paragraph like this one, and its longest is 5,099 chars.
        max_paragraph_chars=8000,
        # Transcriber's notes at both ends (#705): four paragraphs before
        # the Molesworth title page, and at the tail a note plus a 17-line
        # page.line corrections list ("56.14 Prov. xxii. 10[)]: Removed.").
        editorial_runs=(("Transcriber’s Note:", "THE"), ("Transcriber’s Note", None)),
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
