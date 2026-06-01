"""Per-work configuration for Kant ingest from zeno.org.

Mirrors `hegel_works.py` shape; both modules use the generic `CorpusWork`
dataclass from `corpus_works.py`. Each entry sets `corpus="kant"` /
`author="Kant"`, which makes existing `--corpus kant` retrieval filters
work for free.

All works are public domain (Kant died 1804). Sourced from
`http://www.zeno.org/Philosophie/M/Kant,+Immanuel/...`. Locators are
chapter-shaped because zeno's Kant edition, like its Hegel one, omits
the explicit Akademie-Ausgabe page numbers we'd want for §-precision.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="krv_de",
        title="Kritik der reinen Vernunft",
        translator="(Original)",
        edition_year="1781/1787",
        filenames=("krv_de.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="kant",
        author="Kant",
        # KrV is canonically cited by Kant's A (1781) and B (1787)
        # marginal pagination. citation_system='kant_ab' makes
        # curator tagging accept A123/B147 locators via `terms tag`.
        #
        # Known gap: zeno's German HTML strips the marginal A/B
        # annotations, so chunks here have section='¶N'-style values
        # rather than 'A47'/'B63'. zeno *does* preserve AA-volume page
        # references inline as `[NN]` brackets (e.g. `[45]` = AA Vol III
        # p. 45 ≈ start of B-body), but those don't map 1:1 to A/B
        # pages. Curators must pass `--locator A47` (or similar) on
        # the CLI when tagging German source occurrences. The helper
        # `minerva terms suggest-locator --chunk <cid>` reports the
        # corresponding English Cambridge chunks at the same relative
        # document position as a starting hint — alignment is
        # approximate because chunk density differs across editions.
        # Closing the gap automatically would require OCRing the
        # printed Akademie-Ausgabe (AA Vol III, B edition with A
        # variants in footnotes) and extracting marginal Roman/Arabic
        # numerals; we surveyed archive.org's scan
        # (gesammelteschrif0003kant) but its Fraktur typography
        # defeats PyMuPDF's text extraction. korpora.org, Wikisource,
        # and Project Gutenberg do not preserve markers either.
        citation_system="kant_ab",
    ),
    CorpusWork(
        code="kpv_de",
        title="Kritik der praktischen Vernunft",
        translator="(Original)",
        edition_year="1788",
        filenames=("kpv_de.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="ku_de",
        title="Kritik der Urteilskraft",
        translator="(Original)",
        edition_year="1790",
        filenames=("ku_de.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="ku_einl_de",
        title="Einleitung in die Kritik der Urteilskraft (1. Fassung)",
        translator="(Original)",
        edition_year="1789",
        filenames=("ku_einl_de.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="gms_de",
        title="Grundlegung zur Metaphysik der Sitten",
        translator="(Original)",
        edition_year="1785",
        filenames=("gms_de.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="ms_de",
        title="Die Metaphysik der Sitten",
        translator="(Original)",
        edition_year="1797",
        filenames=("ms_de.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="prol_de",
        title="Prolegomena zu einer jeden künftigen Metaphysik",
        translator="(Original)",
        edition_year="1783",
        filenames=("prol_de.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="rel_de",
        title="Die Religion innerhalb der Grenzen der bloßen Vernunft",
        translator="(Original)",
        edition_year="1793",
        filenames=("rel_de.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="anf_naturwiss_de",
        title="Metaphysische Anfangsgründe der Naturwissenschaft",
        translator="(Original)",
        edition_year="1786",
        filenames=("anf_naturwiss_de.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="aufklaerung_de",
        title="Beantwortung der Frage: Was ist Aufklärung?",
        translator="(Original)",
        edition_year="1784",
        filenames=("aufklaerung_de.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="orientieren_de",
        title="Was heißt: sich im Denken orientieren?",
        translator="(Original)",
        edition_year="1786",
        filenames=("orientieren_de.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="frieden_de",
        title="Zum ewigen Frieden. Ein philosophischer Entwurf",
        translator="(Original)",
        edition_year="1795",
        filenames=("frieden_de.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="gemeinspruch_de",
        title="Über den Gemeinspruch: Das mag in der Theorie richtig sein, taugt aber nicht für die Praxis",
        translator="(Original)",
        edition_year="1793",
        filenames=("gemeinspruch_de.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="luegen_de",
        title="Über ein vermeintes Recht aus Menschenliebe zu lügen",
        translator="(Original)",
        edition_year="1797",
        filenames=("luegen_de.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
        corpus="kant",
        author="Kant",
    ),
    # ─── English Critiques (Cambridge editions, PDF) ────────────────
    # These point at PDFs the curator drops into `data/kant_en/`. The
    # English title is canonical for each work; pairing with the
    # German originals via the term-glossary `works.title` join is
    # NOT automatic — they remain separate CorpusWork rows because the
    # Cambridge series uses English titles and the zeno German uses
    # German ones. To make them pair, either retitle the German
    # entries here OR have the curator manually mark them as
    # translations of the same canonical work in the term system.
    #
    # Locator: `chapter` for now. Cambridge editions of KrV preserve
    # Kant's A/B marginal pagination, so we could potentially run a
    # follow-on parser pass to recover those as a `kant_ab` locator,
    # but that needs the PDF text to consistently carry the page
    # markers — verify after the first ingest.
    CorpusWork(
        code="krv_en",
        title="Critique of Pure Reason",
        translator="Guyer / Wood",
        edition_year="1998",
        filenames=("krv_en.pdf",),
        # Cambridge KrV opens with a 93-page editorial introduction
        # (cover, copyright, contents, General editors' preface,
        # Guyer/Wood's "Introduction to the Critique of Pure Reason"
        # with its own bibliography). Kant's text starts at p94 with
        # the work title page and his own Preface. Back matter
        # (Editorial Notes, Glossary, Index) starts at p718.
        pages=(94, 717),
        fmt="pdf",
        # `kant_ab` splitter walks the extracted text for A/B
        # marginal page markers (A47, B63, A449/B477) and uses them
        # as section boundaries. The chapter heading carries through
        # as the `book` label. Arabic-paginated body chunks parse
        # cleanly under citation_system='kant_ab'; the rare
        # Roman-numeral preface pages (A xiii, B vii) emit with the
        # marker intact but require --locator override to tag
        # because the parser accepts Arabic page numbers only.
        locator="kant_ab",
        lang="eng",
        corpus="kant",
        author="Kant",
        # KrV is canonically cited by Kant's A (1781) and B (1787)
        # edition page numbers.
        citation_system="kant_ab",
        # `skip_headings` left in place as a safety net in case the
        # chapter splitter still picks up a translator-introduction
        # heading the page range fails to fully suppress.
        skip_headings=("Translator's Preface", "Introduction to the Translation"),
    ),
    # ─── Cambridge "Practical Philosophy" omnibus (Gregor, 1996) ───
    # Single PDF; each major work below claims a page range from the
    # volume's TOC bookmarks. Page ranges START 4 pages PAST the
    # bookmark — the Cambridge convention is: bookmark on the title
    # page, then a blank verso, then 2–3 pages of translator's
    # introduction, then Kant's text proper. Skipping those 4 pages
    # keeps the editorial intro out of Kant's attributed chunks. Pages
    # outside any declared range — the General editors' preface
    # (pp. 10–37), Editorial note (665–677), Glossary (678–697), and
    # indexes (698–end) — are excluded by virtue of having no CorpusWork
    # that points at them.
    CorpusWork(
        code="schulz_review_en",
        title="Review of Schulz's Attempt at an Introduction to a Doctrine of Morals",
        translator="Gregor",
        edition_year="1996",
        filenames=("practical_philosophy_gregor.pdf",),
        pages=(42, 47),
        fmt="pdf",
        locator="chapter",
        lang="eng",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="aufklaerung_en",
        title="An Answer to the Question: What is Enlightenment?",
        translator="Gregor",
        edition_year="1996",
        filenames=("practical_philosophy_gregor.pdf",),
        pages=(52, 59),
        fmt="pdf",
        locator="chapter",
        lang="eng",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="book_publication_en",
        title="On the Wrongfulness of Unauthorized Publication of Books",
        translator="Gregor",
        edition_year="1996",
        filenames=("practical_philosophy_gregor.pdf",),
        pages=(64, 73),
        fmt="pdf",
        locator="chapter",
        lang="eng",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="gms_en",
        title="Groundwork of the Metaphysics of Morals",
        translator="Gregor",
        edition_year="1996",
        filenames=("practical_philosophy_gregor.pdf",),
        pages=(78, 145),
        fmt="pdf",
        locator="chapter",
        lang="eng",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="hufeland_review_en",
        title="Review of Hufeland's Essay on the Principle of Natural Right",
        translator="Gregor",
        edition_year="1996",
        filenames=("practical_philosophy_gregor.pdf",),
        pages=(150, 155),
        fmt="pdf",
        locator="chapter",
        lang="eng",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="ulrich_review_en",
        title="Kraus's Review of Ulrich's Eleutheriology",
        translator="Gregor",
        edition_year="1996",
        filenames=("practical_philosophy_gregor.pdf",),
        pages=(160, 169),
        fmt="pdf",
        locator="chapter",
        lang="eng",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="kpv_en",
        title="Critique of Practical Reason",
        translator="Gregor",
        edition_year="1996",
        filenames=("practical_philosophy_gregor.pdf",),
        pages=(176, 313),
        fmt="pdf",
        locator="chapter",
        lang="eng",
        corpus="kant",
        author="Kant",
        skip_headings=("Preface", "Translator's Preface", "Introduction to the Translation"),
    ),
    CorpusWork(
        code="theory_practice_en",
        # No editorial intro for this short essay — Kant's text starts
        # right at the TOC bookmark.
        title="On the Common Saying: That May Be Correct in Theory, but It Is of No Use in Practice",
        translator="Gregor",
        edition_year="1996",
        filenames=("practical_philosophy_gregor.pdf",),
        pages=(316, 347),
        fmt="pdf",
        locator="chapter",
        lang="eng",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="perpetual_peace_en",
        title="Toward Perpetual Peace",
        translator="Gregor",
        edition_year="1996",
        filenames=("practical_philosophy_gregor.pdf",),
        pages=(352, 389),
        fmt="pdf",
        locator="chapter",
        lang="eng",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="metaphysics_morals_en",
        # The Metaphysics of Morals has an unusually long editorial
        # apparatus: title (p390), blank, then a Translator's Note on
        # the text (pp. 392-406, ~14 pages). Kant's own writing —
        # "Introduction to the metaphysics of morals" — starts at
        # p407 per the bookmark TOC. Skip the apparatus by starting
        # the range there.
        title="The Metaphysics of Morals",
        translator="Gregor",
        edition_year="1996",
        filenames=("practical_philosophy_gregor.pdf",),
        pages=(407, 641),
        fmt="pdf",
        locator="chapter",
        lang="eng",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="right_to_lie_en",
        title="On a Supposed Right to Lie from Philanthropy",
        translator="Gregor",
        edition_year="1996",
        filenames=("practical_philosophy_gregor.pdf",),
        pages=(646, 653),
        fmt="pdf",
        locator="chapter",
        lang="eng",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="turning_out_books_en",
        title="On Turning Out Books",
        translator="Gregor",
        edition_year="1996",
        filenames=("practical_philosophy_gregor.pdf",),
        pages=(658, 664),
        fmt="pdf",
        locator="chapter",
        lang="eng",
        corpus="kant",
        author="Kant",
    ),
    CorpusWork(
        code="ku_en",
        title="Critique of the Power of Judgment",
        translator="Guyer / Matthews",
        edition_year="2000",
        filenames=("ku_en.pdf",),
        # Cambridge KU's "Editor's introduction" runs pp. 15-54. Kant's
        # writing (his suppressed "First Introduction" + the second
        # Introduction + the Critique itself) starts at p55 and ends
        # at p404. Editorial notes / glossary / index follow.
        pages=(55, 404),
        fmt="pdf",
        locator="chapter",
        lang="eng",
        corpus="kant",
        author="Kant",
        skip_headings=("Translator's Preface", "Introduction to the Translation"),
    ),
)


find_work = make_find_work(WORKS, case_insensitive=True)


def find_works(filename: str) -> list[CorpusWork]:
    """All Works that claim this filename. Order matches ``WORKS``."""
    lower = filename.lower()
    return [w for w in WORKS if any(c.lower() == lower for c in w.filenames)]
