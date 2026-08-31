"""Golden-file tests for the three biblical-corpus parsers.

These parsers (``vulgate.py``, ``tei_lxx.py``, ``sblgnt.py``) landed
in successive sessions and were caught by the maintainability audit
as untested — a regression here would corrupt every Aquinas →
Vulgate cross-reference and every LXX/NT chunk binding without any
test catching it. We assert verse-level shape on one well-known
chunk per parser.

Tests are skipped (not failed) when the source data isn't present on
disk: the downloaders live at ``perseus/download_*.py`` and aren't
run in CI. A local dev that's done ``minerva ingest`` will have
everything; CI without the data will skip cleanly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minerva.locations import BCV_BOOK_ABBR

REPO_ROOT = Path(__file__).resolve().parents[1]


# ════════════════════════════════════════════════════════════════════
# Vulgate — Clementine .lat
# ════════════════════════════════════════════════════════════════════


_VULGATE_DIR = REPO_ROOT / "data" / "vulgate" / "raw_lat"


@pytest.mark.skipif(
    not (_VULGATE_DIR / "Gn.lat").exists(),
    reason="Vulgate Genesis not downloaded; skipping golden test",
)
def test_vulgate_genesis_first_verse() -> None:
    from minerva.authors.vulgate_works import book_for_filename
    from minerva.sources.vulgate import parse_file

    path = _VULGATE_DIR / "Gn.lat"
    book = book_for_filename(path.name)
    assert book is not None
    chunks = list(
        parse_file(
            path,
            book_title=book.title,
            book_abbr=BCV_BOOK_ABBR[book.title],
            work_code=book.code,
        )
    )
    assert len(chunks) > 1500, "Genesis should have ~1530 verses"
    first = chunks[0]
    assert first.section == "Gen 1:1"
    assert first.book == "Genesis"
    assert first.author == "Vulgate"
    assert first.corpus == "vulgate"
    assert first.lang == "lat"
    assert first.citation_system == "bcv"
    assert "In principio creavit Deus" in first.text


@pytest.mark.skipif(
    not (_VULGATE_DIR / "Ps.lat").exists(),
    reason="Vulgate Psalms not downloaded; skipping",
)
def test_vulgate_psalm_50_is_miserere() -> None:
    """Ps 50 in the Vulgate is the Miserere (Hebrew Ps 51).
    Regression catches a Hebrew-vs-Vulgate numbering swap."""

    from minerva.authors.vulgate_works import book_for_filename
    from minerva.sources.vulgate import parse_file

    path = _VULGATE_DIR / "Ps.lat"
    book = book_for_filename(path.name)
    assert book is not None
    chunks = list(
        parse_file(
            path,
            book_title=book.title,
            book_abbr=BCV_BOOK_ABBR[book.title],
            work_code=book.code,
        )
    )
    # Find Ps 50:1 — should mention "In finem" or "Psalmus David".
    ps_50_1 = next((c for c in chunks if c.section == "Ps 50:1"), None)
    assert ps_50_1 is not None
    # The Miserere header in the Clementine starts "In finem. Psalmus David".
    assert "Psalmus David" in ps_50_1.text or "In finem" in ps_50_1.text


@pytest.mark.skipif(
    not (_VULGATE_DIR / "Dn.lat").exists(),
    reason="Vulgate Daniel not downloaded; skipping",
)
def test_vulgate_daniel_includes_chapter_13_susanna() -> None:
    """Vulgate Daniel has 14 chapters — chapter 13 is Susanna, 14 is
    Bel & the Dragon (LXX-only books embedded in Daniel per
    Vulgate convention)."""

    from minerva.authors.vulgate_works import book_for_filename
    from minerva.sources.vulgate import parse_file

    path = _VULGATE_DIR / "Dn.lat"
    book = book_for_filename(path.name)
    assert book is not None
    chunks = list(
        parse_file(
            path,
            book_title=book.title,
            book_abbr=BCV_BOOK_ABBR[book.title],
            work_code=book.code,
        )
    )
    sections = {c.section for c in chunks}
    assert "Dan 13:1" in sections, "Susanna missing — Vulgate Daniel must run through ch. 13"
    assert "Dan 14:1" in sections, (
        "Bel & the Dragon missing — Vulgate Daniel must run through ch. 14"
    )


# ════════════════════════════════════════════════════════════════════
# Septuagint — First1KGreek TEI P5
# ════════════════════════════════════════════════════════════════════


_LXX_DIR = REPO_ROOT / "perseus" / "raw_xml_lxx"
_LXX_GENESIS = _LXX_DIR / "tlg0527.tlg001.1st1K-grc1.xml"


@pytest.mark.skipif(
    not _LXX_GENESIS.exists(),
    reason="LXX Genesis not downloaded; skipping",
)
def test_lxx_genesis_first_verse() -> None:
    from minerva.authors.septuagint_works import book_for_filename
    from minerva.sources.tei_lxx import parse_file

    book = book_for_filename(_LXX_GENESIS.name)
    assert book is not None
    chunks = list(
        parse_file(
            _LXX_GENESIS,
            book_title=book.title,
            book_abbr=BCV_BOOK_ABBR[book.title],
            work_code=book.code,
        )
    )
    assert len(chunks) > 1000, "Genesis should have ~1496 verses"
    first = chunks[0]
    assert first.section == "Gen 1:1"
    assert first.book == "Genesis"
    assert first.author == "Septuagint"
    assert first.corpus == "septuagint"
    assert first.lang == "grc"
    assert first.citation_system == "bcv"
    # Famous opening: Ἐν ἀρχῇ ἐποίησεν ὁ θεός
    # Swete uses small-caps for the chapter incipit ("ΕΝ ΑΡΧΗ").
    text_lower = first.text.lower()
    # The Greek lowercase 'θεὸς' is the stable invariant since the
    # majuscule incipit varies by Swete edition.
    assert "θεὸς" in first.text or "θεός" in first.text or "ΘΕΟΣ" in first.text


@pytest.mark.skipif(
    not _LXX_GENESIS.exists(),
    reason="LXX Genesis not downloaded; skipping",
)
def test_lxx_genesis_1_2_has_no_apparatus_siglum() -> None:
    """Gen 1:2 used to read "ἡ δὲ γῆ A ἦν ἀόρατος…" — the marginal
    manuscript siglum from a mid-verse <note> leaked into the text."""

    from minerva.authors.septuagint_works import book_for_filename
    from minerva.sources.tei_lxx import parse_file

    book = book_for_filename(_LXX_GENESIS.name)
    assert book is not None
    chunks = list(
        parse_file(
            _LXX_GENESIS,
            book_title=book.title,
            book_abbr=BCV_BOOK_ABBR[book.title],
            work_code=book.code,
        )
    )
    import unicodedata

    gen_1_2 = next(c for c in chunks if c.section == "Gen 1:2")
    # NFC both sides — Swete's file mixes oxia/tonos accent codepoints.
    assert unicodedata.normalize("NFC", gen_1_2.text).startswith(
        unicodedata.normalize("NFC", "ἡ δὲ γῆ ἦν ἀόρατος")
    )


_LXX_JOB = _LXX_DIR / "tlg0527.tlg032.1st1K-grc1.xml"


@pytest.mark.skipif(
    not _LXX_JOB.exists(),
    reason="LXX Job not downloaded; skipping",
)
def test_lxx_job_poetry_in_l_lines_is_ingested() -> None:
    """Job is encoded verse-div → <l> lines with no <p> at all; the
    <p>-only walker dropped ALL 1,077 verses of the book (likewise
    Proverbs, Wisdom, Song of Songs — ~2,545 verses total)."""

    from minerva.authors.septuagint_works import book_for_filename
    from minerva.sources.tei_lxx import parse_file

    book = book_for_filename(_LXX_JOB.name)
    assert book is not None
    chunks = list(
        parse_file(
            _LXX_JOB,
            book_title=book.title,
            book_abbr=BCV_BOOK_ABBR[book.title],
            work_code=book.code,
        )
    )
    assert len(chunks) > 1000, "Job should have ~1077 verses"
    job_1_21 = next(c for c in chunks if c.section == "Job 1:21")
    assert "γυμνὸς" in job_1_21.text


# ════════════════════════════════════════════════════════════════════
# SBLGNT — Holmes 2010 NT custom XML
# ════════════════════════════════════════════════════════════════════


_NT_DIR = REPO_ROOT / "data" / "nt" / "raw_grc"


@pytest.mark.skipif(
    not (_NT_DIR / "John.xml").exists(),
    reason="SBLGNT John not downloaded; skipping",
)
def test_sblgnt_john_1_1() -> None:
    """John 1:1 is the regression test of regression tests for any NT
    parser. If this verse doesn't round-trip with proper spacing
    between words, the SBLGNT empty-suffix-means-space convention
    has regressed."""

    from minerva.authors.new_testament_works import book_for_filename
    from minerva.sources.sblgnt import parse_file

    path = _NT_DIR / "John.xml"
    book = book_for_filename(path.name)
    assert book is not None
    chunks = list(
        parse_file(
            path,
            book_title=book.title,
            book_abbr=BCV_BOOK_ABBR[book.title],
            work_code=book.code,
        )
    )
    first = chunks[0]
    assert first.section == "John 1:1"
    assert first.book == "John"
    assert first.author == "New Testament"
    assert first.corpus == "new_testament"
    assert first.lang == "grc"
    assert first.citation_system == "bcv"
    # The exact verse: spacing between words is the regression target.
    assert first.text == ("Ἐν ἀρχῇ ἦν ὁ λόγος, καὶ ὁ λόγος ἦν πρὸς τὸν θεόν, καὶ θεὸς ἦν ὁ λόγος.")


@pytest.mark.skipif(
    not (_NT_DIR / "1Cor.xml").exists(),
    reason="SBLGNT 1Cor not downloaded; skipping",
)
def test_sblgnt_1cor_13_1() -> None:
    """1 Corinthians 1:1 — uses the "1 Corinthians" multi-word book
    name in the verse-number id, which our parser must split on the
    last space (greedy book name + chap:verse)."""

    from minerva.authors.new_testament_works import book_for_filename
    from minerva.sources.sblgnt import parse_file

    path = _NT_DIR / "1Cor.xml"
    book = book_for_filename(path.name)
    assert book is not None
    chunks = list(
        parse_file(
            path,
            book_title=book.title,
            book_abbr=BCV_BOOK_ABBR[book.title],
            work_code=book.code,
        )
    )
    first = chunks[0]
    assert first.section == "1Cor 1:1"
    assert first.book == "1 Corinthians"
    assert first.text.startswith("Παῦλος")


@pytest.mark.skipif(
    not (_NT_DIR / "Rev.xml").exists(),
    reason="SBLGNT Revelation not downloaded; skipping",
)
def test_sblgnt_revelation_last_verse() -> None:
    """Rev 22:21 — the final verse of the NT. Ensures the parser
    walks all the way through the last <p> without dropping a
    trailing verse-number milestone."""

    from minerva.authors.new_testament_works import book_for_filename
    from minerva.sources.sblgnt import parse_file

    path = _NT_DIR / "Rev.xml"
    book = book_for_filename(path.name)
    assert book is not None
    chunks = list(
        parse_file(
            path,
            book_title=book.title,
            book_abbr=BCV_BOOK_ABBR[book.title],
            work_code=book.code,
        )
    )
    last = chunks[-1]
    assert last.section == "Rev 22:21"
    assert "Ἰησοῦ" in last.text or "κυρίου" in last.text
