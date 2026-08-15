"""Tests for `minerva.corpus` — splitters, chrome detection, and the
file→work dispatch table.

All fixture text is invented, not from real Hegel/Kant translations. Real
extraction is exercised manually by `minerva ingest` against the user's
local files; we don't ship those into the test tree.
"""

from __future__ import annotations

from pathlib import Path

from minerva import corpus as corpus_parse
from minerva import corpus_works
from minerva.authors import hegel_works

# ---------- _detect_page_chrome ----------


def test_detect_page_chrome_flags_repeating_top_and_bottom_lines():
    pages = [
        ["Running header", "real content " + str(i), "more content", "Page footer"]
        for i in range(8)
    ]
    chrome = corpus_parse._detect_page_chrome(pages, threshold=0.5)
    assert "Running header" in chrome
    assert "Page footer" in chrome
    # Per-page distinct lines should NOT be flagged.
    assert "real content 3" not in chrome


def test_detect_page_chrome_returns_empty_for_short_books():
    pages = [["a", "b"], ["c", "d"]]
    assert corpus_parse._detect_page_chrome(pages) == set()


def test_detect_page_chrome_ignores_long_lines():
    long_line = "x" * 200
    pages = [[long_line, "v"], [long_line, "v"], [long_line, "v"], [long_line, "v"]]
    # Long lines are filtered out before counting (not chrome shape).
    assert long_line not in corpus_parse._detect_page_chrome(pages)


# ---------- split_by_section ----------


def _make_work(locator: str, code: str = "x") -> corpus_works.CorpusWork:
    return corpus_works.CorpusWork(
        code=code,
        title="Test CorpusWork",
        translator="T",
        edition_year="2000",
        filenames=("x.pdf",),
        fmt="pdf",
        locator=locator,
    )


# Section bodies in the real corpus are 136+ chars; the splitter
# enforces a minimum to suppress cross-reference artifacts. Test
# fixtures use realistic-length bodies so they pass the filter.
_BODY_A = "The first body of a section, long enough to exceed the minimum-body filter that drops cross-reference artifacts."
_BODY_B = "The second body is similarly substantive prose, the kind of paragraph Hegel actually writes inside a numbered section."
_BODY_C = "And the third body contains yet another long, complete-sentence piece of section text, also above the minimum threshold."


def test_split_by_section_emits_one_chunk_per_marker(tmp_path: Path):
    text = f"Front matter we drop.\n\n§1\n{_BODY_A}\n\n§2\n{_BODY_B}\n\n§3\n{_BODY_C}\n"
    chunks = list(corpus_parse.split_by_section(text, _make_work("section"), tmp_path / "x.pdf"))
    assert [c.section for c in chunks] == ["§1", "§2", "§3"]
    assert chunks[0].text == _BODY_A
    assert chunks[2].text == _BODY_C


def test_split_by_section_handles_whitespace_after_marker(tmp_path: Path):
    text = f"§ 17\n{_BODY_A}\n\n§  18\n{_BODY_B}"
    chunks = list(corpus_parse.split_by_section(text, _make_work("section"), tmp_path / "x.pdf"))
    assert [c.section for c in chunks] == ["§17", "§18"]


def test_split_by_section_skips_empty_bodies(tmp_path: Path):
    text = f"§1\n   \n§2\n{_BODY_A}\n"
    chunks = list(corpus_parse.split_by_section(text, _make_work("section"), tmp_path / "x.pdf"))
    assert [c.section for c in chunks] == ["§2"]


def test_split_by_section_ignores_inline_references(tmp_path: Path):
    """Inline cross-references like 'see §44' must not start a new chunk."""
    text = (
        f"§1\n"
        f"{_BODY_A} this body refers to §44 and §123 inline; those should not split.\n\n"
        f"§2\n"
        f"{_BODY_B}\n"
    )
    chunks = list(corpus_parse.split_by_section(text, _make_work("section"), tmp_path / "x.pdf"))
    assert [c.section for c in chunks] == ["§1", "§2"]
    assert "§44" in chunks[0].text  # inline ref preserved in body


def test_split_by_section_drops_crossref_artifacts(tmp_path: Path):
    """Body bodies under `_SECTION_MIN_BODY` chars are dropped — they
    indicate the §-match is an inline cross-reference like
    `(see §6 above)` that got broken across lines during extraction."""
    text = (
        f"§1\n{_BODY_A}\n\n"
        # Below: tiny body simulating a cross-ref artifact that escaped
        # the line-break repair pass.
        f"§99\nabove)\n\n"
        f"§2\n{_BODY_B}\n"
    )
    chunks = list(corpus_parse.split_by_section(text, _make_work("section"), tmp_path / "x.pdf"))
    assert [c.section for c in chunks] == ["§1", "§2"]


def test_split_by_section_repairs_crossref_linebreaks(tmp_path: Path):
    """Inline cross-refs like `(see\\n§ 6\\nabove)` get rejoined onto a
    single line so the §-marker is no longer at start-of-line. This
    prevents the real §1 body from being truncated by the spurious §6
    match."""
    text = (
        f"§1\n{_BODY_A} The drives are mentioned (see\n§ 6\nabove)\n"
        "for further determination, and the will is determined.\n\n"
        f"§2\n{_BODY_B}\n"
    )
    chunks = list(corpus_parse.split_by_section(text, _make_work("section"), tmp_path / "x.pdf"))
    assert [c.section for c in chunks] == ["§1", "§2"]
    # §1's body includes everything through the cross-ref repair point.
    assert "see § 6 above" in chunks[0].text  # repaired onto one line
    assert "§ 6" in chunks[0].text  # cross-ref preserved as content


# ---------- split_by_paragraph ----------


def test_split_by_paragraph_finds_pinkard_style_numbering(tmp_path: Path):
    text = "preface\n\n1. body of one\n2. body of two\n3. body of three\n"
    chunks = list(
        corpus_parse.split_by_paragraph(text, _make_work("paragraph"), tmp_path / "x.pdf")
    )
    assert [c.section for c in chunks] == ["¶1", "¶2", "¶3"]
    assert chunks[1].text == "body of two"


def test_split_by_paragraph_dedupes_repeated_numbers(tmp_path: Path):
    # Mis-extraction can repeat a number; we keep the first occurrence only.
    text = "1. real first\n2. real second\n2. spurious dup\n"
    chunks = list(
        corpus_parse.split_by_paragraph(text, _make_work("paragraph"), tmp_path / "x.pdf")
    )
    assert [c.section for c in chunks] == ["¶1", "¶2"]


def test_split_by_paragraph_returns_nothing_when_no_markers(tmp_path: Path):
    chunks = list(
        corpus_parse.split_by_paragraph(
            "no numbering here", _make_work("paragraph"), tmp_path / "x.pdf"
        )
    )
    assert chunks == []


def test_split_by_paragraph_honors_max_section_cap(tmp_path: Path):
    """Numbers above max_section are rejected as spurious (page numbers etc.)."""
    work = corpus_works.CorpusWork(
        code="x",
        title="Test",
        translator="T",
        edition_year="2000",
        filenames=("x.pdf",),
        fmt="pdf",
        locator="paragraph",
        max_section=10,
    )
    text = "1. real\n\n2. real\n\n9999. spurious page number\n\n3. real third\n"
    chunks = list(corpus_parse.split_by_paragraph(text, work, tmp_path / "x.pdf"))
    assert [c.section for c in chunks] == ["¶1", "¶2", "¶3"]


def test_split_by_section_honors_max_section_cap(tmp_path: Path):
    work = corpus_works.CorpusWork(
        code="x",
        title="Test",
        translator="T",
        edition_year="2000",
        filenames=("x.pdf",),
        fmt="pdf",
        locator="section",
        max_section=20,
    )
    text = f"§1\n{_BODY_A}\n\n§19\n{_BODY_B}\n\n§9999\n{_BODY_C}\n\n§20\n{_BODY_A}\n"
    chunks = list(corpus_parse.split_by_section(text, work, tmp_path / "x.pdf"))
    assert [c.section for c in chunks] == ["§1", "§19", "§20"]


def test_split_by_section_honors_min_section_floor(tmp_path: Path):
    """Partial-volume editions (e.g. Encyclopedia Part III: §§377-577) need a
    floor as well as a ceiling, since OCR noise can hit low-numbered §-shapes
    in front matter or at page boundaries."""
    work = corpus_works.CorpusWork(
        code="x",
        title="Test",
        translator="T",
        edition_year="2000",
        filenames=("x.pdf",),
        fmt="pdf",
        locator="section",
        min_section=377,
        max_section=577,
    )
    text = f"§40\n{_BODY_A}\n\n§377\n{_BODY_B}\n\n§578\n{_BODY_C}\n\n§500\n{_BODY_A}\n"
    chunks = list(corpus_parse.split_by_section(text, work, tmp_path / "x.pdf"))
    assert [c.section for c in chunks] == ["§377", "§500"]


# ---------- split_by_chapter ----------


def test_split_by_chapter_uses_heading_plus_paragraph_index(tmp_path: Path):
    text = (
        "preface text we keep\n\n"
        "CHAPTER ONE\n\n"
        "para a of chapter one\n\n"
        "para b of chapter one\n\n"
        "CHAPTER TWO\n\n"
        "para a of chapter two\n"
    )
    chunks = list(corpus_parse.split_by_chapter(text, _make_work("chapter"), tmp_path / "x.pdf"))
    sections = [c.section for c in chunks]
    # Heading labels are now title-cased rather than left in the source's caps.
    assert "Chapter One, ¶1" in sections
    assert "Chapter One, ¶2" in sections
    assert "Chapter Two, ¶1" in sections
    # Front matter is preserved with no heading (some translations leave the
    # major chapter heads outside _HEADING_RE's net, so dropping the leading
    # region would lose chapters worth of body text).
    assert "¶1" in sections  # unlabeled front-matter chunk
    assert any("preface text we keep" in c.text for c in chunks)


def test_split_by_chapter_drops_editorial_sections(tmp_path: Path):
    """Bodies under editor / translator headings ("Editorial Introduction",
    "Glossary", "Bibliography") must not be emitted as chunks — otherwise
    they get attributed to the work's author downstream."""
    text = (
        "EDITORIAL INTRODUCTION\n\n"
        "para of editor's intro that must not be attributed to Hegel\n\n"
        "more editor commentary\n\n"
        "CHAPTER ONE\n\n"
        "real chapter body, attributed to Hegel\n\n"
        "GLOSSARY\n\n"
        "abbreviation: meaning\n\n"
        "another glossary entry\n\n"
        "CHAPTER TWO\n\n"
        "second real chapter body\n"
    )
    chunks = list(corpus_parse.split_by_chapter(text, _make_work("chapter"), tmp_path / "x.pdf"))
    sections = [c.section for c in chunks]
    bodies = [c.text for c in chunks]
    assert "Chapter One, ¶1" in sections
    assert "Chapter Two, ¶1" in sections
    # None of the editorial bodies should survive.
    assert not any("editor" in b.lower() for b in bodies)
    assert not any("glossary" in b.lower() for b in bodies)
    assert not any("abbreviation: meaning" in b for b in bodies)
    # And no chunk should carry an editorial heading as its locator.
    assert not any("Editorial" in s for s in sections)
    assert not any("Glossary" in s for s in sections)


def test_split_by_chapter_drops_ocr_garbled_editorial_headings(tmp_path: Path):
    """OCR mangles "Editorial Introduction" into many letter-spaced forms;
    the editorial filter normalizes them away before matching."""
    text = "EDITORIAL INTR O DUCTION\n\neditor's commentary text\n\nCHAPTER ONE\n\nHegel body\n"
    chunks = list(corpus_parse.split_by_chapter(text, _make_work("chapter"), tmp_path / "x.pdf"))
    assert all("editor" not in c.text.lower() for c in chunks)
    assert any(c.section == "Chapter One, ¶1" for c in chunks)


def test_split_by_chapter_drops_bibliography_blurb_bodies(tmp_path: Path):
    """A sub-heading like "A. General Works" or "II. Studies" looks like a
    normal chapter to the splitter, so editorial-heading filtering can't
    catch it. The content-based filter recognises the body's bibliographic
    shape (repeated `SURNAME, FIRSTNAME. Title. City, Year.`) and drops
    it before emit."""
    text = (
        "A. GENERAL WORKS\n\n"
        "CAIRD, EDWARD. Hegel. Philadelphia, 1883. Concise and clear, "
        "confined to an outline. CROCE, BENEDETTO. What Is Living and What "
        "Is Dead in the Philosophy of Hegel. London, 1925. A forceful "
        "statement. MURE, G. R. G. An Introduction to Hegel. Oxford, 1940.\n\n"
        "CHAPTER ONE\n\n"
        "real Hegel paragraph here\n"
    )
    chunks = list(corpus_parse.split_by_chapter(text, _make_work("chapter"), tmp_path / "x.pdf"))
    bodies = [c.text for c in chunks]
    assert not any("CAIRD" in b for b in bodies)
    assert not any("CROCE" in b for b in bodies)
    assert any("real Hegel paragraph" in b for b in bodies)


def test_split_by_chapter_honors_per_work_skip_headings(tmp_path: Path):
    """`CorpusWork.skip_headings` drops a specific edition's translator/editor
    preface that the global filter intentionally keeps (Hegel writes his
    own prefaces in PhG, PR, etc., so "Preface" can't be globally banned)."""
    work = corpus_works.CorpusWork(
        code="x",
        title="Test CorpusWork",
        translator="T",
        edition_year="2000",
        filenames=("x.pdf",),
        fmt="pdf",
        locator="chapter",
        skip_headings=("Preface",),
    )
    text = (
        "PREFACE\n\n"
        "editor preface body — must not be attributed to Hegel\n\n"
        "CHAPTER ONE\n\n"
        "real Hegel paragraph\n"
    )
    chunks = list(corpus_parse.split_by_chapter(text, work, tmp_path / "x.pdf"))
    bodies = [c.text for c in chunks]
    assert not any("editor preface" in b for b in bodies)
    assert any("real Hegel paragraph" in b for b in bodies)


def test_split_by_chapter_skip_headings_default_keeps_preface(tmp_path: Path):
    """Without `skip_headings`, a "Preface" chapter is preserved — Hegel
    has plenty of his own, and this is the safety net for the per-work
    opt-in design."""
    text = "PREFACE\n\nHegel's own preface body\n\nCHAPTER ONE\n\nmain chapter body\n"
    chunks = list(corpus_parse.split_by_chapter(text, _make_work("chapter"), tmp_path / "x.pdf"))
    assert any("Hegel's own preface body" in c.text for c in chunks)


def test_bibliographical_note_heading_is_treated_as_editorial(tmp_path: Path):
    """Variants of "Bibliographical Note" must be dropped — the older list
    only matched `bibliography`, which isn't a substring of `bibliographical`."""
    assert corpus_parse._is_editorial_heading("Bibliographical Note") is True
    assert (
        corpus_parse._is_editorial_heading("Bibliographical Note II. Some Books About Hegel")
        is True
    )
    assert corpus_parse._is_editorial_heading("Further Reading") is True
    assert corpus_parse._is_editorial_heading("Selected Bibliography") is True
    assert corpus_parse._is_editorial_heading("In Memoriam Henry Silton Harris") is True


def test_split_by_chapter_falls_back_to_paragraph_only_when_no_headings(tmp_path: Path):
    text = "para one\n\npara two\n\npara three"
    chunks = list(corpus_parse.split_by_chapter(text, _make_work("chapter"), tmp_path / "x.pdf"))
    assert [c.section for c in chunks] == ["¶1", "¶2", "¶3"]


def test_split_by_chapter_merges_wrapped_heading_continuations(tmp_path: Path):
    """A long ALL-CAPS heading that PDF extraction wraps onto multiple lines
    should arrive at the chunker as a single label."""
    text = (
        "front matter\n\n"
        "FIRST HEADING WHICH WRAPS ACROSS\n"
        "TWO PRINTED LINES\n\n"
        "para of chapter one\n\n"
        "SECOND CHAPTER\n\n"
        "para of chapter two\n"
    )
    chunks = list(corpus_parse.split_by_chapter(text, _make_work("chapter"), tmp_path / "x.pdf"))
    sections = [c.section for c in chunks]
    # The wrapped heading is treated as one label, not two separate ones.
    assert "First Heading Which Wraps Across Two Printed Lines, ¶1" in sections
    assert "Second Chapter, ¶1" in sections
    # No fragment-as-its-own-heading.
    assert not any(s == "Two Printed Lines, ¶1" for s in sections if "First" not in s)


def test_merge_continuation_headings_caps_at_four_lines():
    import re as _re

    # Use multi-letter tokens that aren't Roman numerals so neither the
    # letter-space sanitizer nor the title-case Roman preservation perturbs
    # the synthetic merged label — we're exercising the cap, not cleanup.
    text = "AAA\nBBB\nFOO\nBAR\nQUX\nZZZ\n"
    matches = list(_re.finditer(r"(?m)^([A-Z]{3})$", text))
    merged = corpus_parse._merge_continuation_headings(text, matches)
    # Cap is 4: first chunk is 5 lines (the start + 4 merge attempts), then ZZZ separate.
    assert len(merged) == 2
    assert merged[0][2] == "Aaa Bbb Foo Bar Qux"
    assert merged[1][2] == "Zzz"


def test_merge_continuation_headings_skips_duplicate_text():
    """zeno.org sometimes prints a chapter title twice in adjacent positions
    (breadcrumb + heading). The merge logic should skip the duplicate so we
    don't produce "Foo Foo"-shaped labels."""
    import re as _re

    text = "VIII. Das absolute Wissen\nVIII. Das absolute Wissen\nreal chapter body\n"
    matches = list(_re.finditer(r"(?m)^([IVX]+\.[^\n]+)$", text))
    merged = corpus_parse._merge_continuation_headings(text, matches)
    assert len(merged) == 1
    assert merged[0][2] == "VIII. Das absolute Wissen"


# ---------- emit / chunk shape ----------


def test_emit_returns_none_for_empty_text(tmp_path: Path):
    work = _make_work("section")
    assert corpus_parse._emit(work, tmp_path / "x.pdf", "§1", "   \n  \n") is None


def test_emit_populates_corpus_author_translator(tmp_path: Path):
    work = _make_work("section")
    chunk = corpus_parse._emit(work, tmp_path / "x.pdf", "§1", "real text")
    assert chunk is not None
    assert chunk.corpus == "hegel"
    assert chunk.author == "Hegel"
    assert chunk.lang == "eng"
    assert chunk.translator == "T"
    assert chunk.edition_year == "2000"
    assert chunk.work == "Test CorpusWork"


def test_emit_chunk_id_is_stable(tmp_path: Path):
    work = _make_work("section")
    a = corpus_parse._emit(work, tmp_path / "x.pdf", "§1", "same body text")
    b = corpus_parse._emit(work, tmp_path / "x.pdf", "§1", "same body text")
    assert a is not None and b is not None
    assert a.chunk_id == b.chunk_id


def test_emit_propagates_work_lang_to_chunk(tmp_path: Path):
    """German originals declare lang='deu'; emitted chunks must carry it."""
    work_de = corpus_works.CorpusWork(
        code="x_de",
        title="Test",
        translator="(Original)",
        edition_year="1820",
        filenames=("x.html",),
        fmt="html",
        locator="section",
        lang="deu",
    )
    chunk = corpus_parse._emit(work_de, tmp_path / "x.html", "§1", "body")
    assert chunk is not None
    assert chunk.lang == "deu"
    # English work entries (default) still come out as 'en'.
    work_en = _make_work("section")
    en_chunk = corpus_parse._emit(work_en, tmp_path / "x.pdf", "§1", "body")
    assert en_chunk is not None
    assert en_chunk.lang == "eng"


def test_emit_chunk_id_changes_when_lang_changes(tmp_path: Path):
    """Same text in two languages must produce distinct chunk_ids — otherwise
    a German §1 would silently overwrite the English §1 in the store."""
    work_en = _make_work("section")
    work_de = corpus_works.CorpusWork(
        code="x_de",
        title="Test CorpusWork",
        translator="T",
        edition_year="2000",
        filenames=("x.pdf",),
        fmt="pdf",
        locator="section",
        lang="deu",
    )
    a = corpus_parse._emit(work_en, tmp_path / "x.pdf", "§1", "body")
    b = corpus_parse._emit(work_de, tmp_path / "x.pdf", "§1", "body")
    assert a is not None and b is not None
    assert a.chunk_id != b.chunk_id


def test_extract_html_reads_text_and_strips_nav_chrome(tmp_path: Path):
    """`extract_html` should drop nav / footer / mw-editsection elements and
    keep the .mw-parser-output (or whole body) text."""
    sample = """<!doctype html>
<html><head><title>x</title></head><body>
<nav class="navigation-not-searchable">junk nav</nav>
<div class="mw-parser-output">
  <h2>Heading</h2>
  <p>real body text here.</p>
  <span class="mw-editsection">[edit]</span>
  <p>second paragraph.</p>
</div>
<footer>page footer</footer>
</body></html>
"""
    p = tmp_path / "sample.html"
    p.write_text(sample, encoding="utf-8")
    text = corpus_parse.extract_html(p)
    assert "real body text here" in text
    assert "second paragraph" in text
    assert "junk nav" not in text
    assert "page footer" not in text
    assert "[edit]" not in text


def test_extract_html_handles_zeno_org_layout(tmp_path: Path):
    """zeno.org uses `#zenoCOText` for body and `.zenoCOHeader`, etc. for
    chrome. Concatenated dumps produced by the German downloader have many
    `#zenoCOText` blocks separated by site chrome."""
    sample = """<!doctype html>
<html><body>
<div class="zenoSF">search box</div>
<div id="zenoTF">top frame</div>
<div class="zenoCOHeader">chapter heading chrome</div>
<div class="zenoCOHeadline">site headline chrome</div>
<div id="zenoCOText">
  <p>first chapter body fragment.</p>
</div>
<div class="zenoCOFooterLine">previous / next nav</div>
<div class="adsbygoogle">advertising</div>
<div id="zenoCOText">
  <p>second chapter body fragment.</p>
</div>
</body></html>
"""
    p = tmp_path / "zeno.html"
    p.write_text(sample, encoding="utf-8")
    text = corpus_parse.extract_html(p)
    assert "first chapter body fragment" in text
    assert "second chapter body fragment" in text
    assert "search box" not in text
    assert "top frame" not in text
    assert "chapter heading chrome" not in text
    assert "previous / next nav" not in text
    assert "advertising" not in text


def test_german_works_have_lang_de():
    """All four major German entries in hegel_works should declare lang='deu'."""
    codes = {"phg_de", "pr_de", "enz_de", "sol_de"}
    found = {w.code for w in hegel_works.WORKS if w.lang == "deu"}
    assert codes <= found, f"missing German lang on: {codes - found}"


def test_derive_zeno_heading_strips_root_and_decodes():
    """URL paths → readable chapter labels."""
    root = "/Philosophie/M/Hegel,+Georg+Wilhelm+Friedrich/Ph%C3%A4nomenologie+des+Geistes"
    h = corpus_parse._derive_zeno_heading(
        root + "/A.+Bewu%C3%9Ftsein/I.+Die+sinnliche+Gewi%C3%9Fheit",
        root,
    )
    assert h == "A. Bewußtsein › I. Die sinnliche Gewißheit"
    # Root → empty heading
    assert corpus_parse._derive_zeno_heading(root, root) == ""


def test_split_zeno_pages_emits_clean_chapter_labels(tmp_path: Path):
    """Each ZENO_PAGE marker should produce a chunk-block whose `book`
    field is the chapter path tail, with paragraphs split inside."""
    html = (
        "<!-- ZENO_PAGE: /Philosophie/M/Hegel,+Georg+Wilhelm+Friedrich/Test+Werk -->\n"
        '<div id="zenoCOText">root landing — drop me\n\nor keep, doesn\'t matter</div>\n\n'
        "<!-- ZENO_PAGE: /Philosophie/M/Hegel,+Georg+Wilhelm+Friedrich/Test+Werk/Vorrede -->\n"
        '<div id="zenoCOText"><p>preface paragraph one.</p><p>preface paragraph two.</p></div>\n\n'
        "<!-- ZENO_PAGE: /Philosophie/M/Hegel,+Georg+Wilhelm+Friedrich/Test+Werk/A.+Bewu%C3%9Ftsein -->\n"
        '<div id="zenoCOText"><p>chapter A body paragraph.</p></div>\n'
    )
    p = tmp_path / "test.html"
    p.write_text(html, encoding="utf-8")
    work = corpus_works.CorpusWork(
        code="t_de",
        title="Test Werk",
        translator="(Original)",
        edition_year="1820",
        filenames=("test.html",),
        fmt="html",
        locator="chapter",
        lang="deu",
    )
    chunks = list(corpus_parse.split_zeno_pages(html, work, p))
    # Ensure proper umlaut decoding in headings.
    headings = {c.book for c in chunks if c.book}
    assert "Vorrede" in headings
    assert "A. Bewußtsein" in headings
    assert all(c.lang == "deu" for c in chunks)
    # Chapter sections look like "<heading>, ¶<idx>" or "¶<idx>" (root).
    sections = [c.section for c in chunks]
    assert any(s.startswith("Vorrede,") for s in sections)
    assert any(s.startswith("A. Bewußtsein,") for s in sections)


def test_split_zeno_pages_returns_nothing_when_no_markers(tmp_path: Path):
    chunks = list(
        corpus_parse.split_zeno_pages(
            "<p>plain html no markers</p>", _make_work("chapter"), tmp_path / "x.html"
        )
    )
    assert chunks == []


def test_kant_works_table_declares_kant_corpus_and_author():
    """Kant entries must override the HegelWork defaults so chunks land in
    the Kant corpus rather than getting silently filed under Hegel."""
    from minerva.authors import kant_works

    assert len(kant_works.WORKS) >= 10
    for w in kant_works.WORKS:
        assert w.corpus == "kant", f"{w.code!r} corpus={w.corpus!r}"
        assert w.author == "Kant", f"{w.code!r} author={w.author!r}"
        # The German originals are 'deu'; the Cambridge English Critique
        # PDFs (krv_en, kpv_en, ku_en) are 'eng'. Both are valid.
        assert w.lang in ("deu", "eng"), f"{w.code!r} lang={w.lang!r}"


def test_kant_works_has_english_critique_entries():
    """The three Critiques plus the Gregor omnibus's constituent
    works must be wired up. KrV and KU have their own standalone
    PDFs; KpV and the rest live inside `practical_philosophy_gregor.pdf`
    as page ranges (see kant_works.py for the full bookmark map)."""
    from minerva.authors import kant_works

    en_codes = {w.code for w in kant_works.WORKS if w.lang == "eng"}
    # Standalone Critique PDFs. Each has its own pages range to trim
    # publisher / editor front matter from the start and back-matter
    # apparatus (Editorial Notes, Glossary, Index) from the end.
    for code in ("krv_en", "ku_en"):
        assert code in en_codes
        w = next(x for x in kant_works.WORKS if x.code == code)
        assert w.fmt == "pdf"
        assert w.filenames == (f"{code}.pdf",)
        assert w.pages is not None and w.pages[1] >= w.pages[0]
    # Gregor omnibus entries share one filename and each declares a
    # `pages` range.
    omnibus_codes = {
        "schulz_review_en",
        "aufklaerung_en",
        "book_publication_en",
        "gms_en",
        "hufeland_review_en",
        "ulrich_review_en",
        "kpv_en",
        "theory_practice_en",
        "perpetual_peace_en",
        "metaphysics_morals_en",
        "right_to_lie_en",
        "turning_out_books_en",
    }
    assert omnibus_codes <= en_codes
    for code in omnibus_codes:
        w = next(x for x in kant_works.WORKS if x.code == code)
        assert w.filenames == ("practical_philosophy_gregor.pdf",)
        assert w.pages is not None and w.pages[1] >= w.pages[0]


def test_kant_find_works_returns_all_matches_for_omnibus():
    """The Gregor PDF is claimed by 12 Works; find_works must return
    all of them (find_work returns only the first, for legacy callers)."""
    from minerva.authors import kant_works

    matches = kant_works.find_works("practical_philosophy_gregor.pdf")
    assert len(matches) == 12
    # Each one has a pages range, and ranges don't overlap.
    ranges = sorted((w.pages[0], w.pages[1], w.code) for w in matches)
    from itertools import pairwise

    for (_a_start, a_end, a_code), (b_start, _b_end, b_code) in pairwise(ranges):
        assert a_end < b_start, f"overlap between {a_code} and {b_code}"


def test_kant_find_work_resolves_canonical_filenames():
    from minerva.authors import kant_works

    krv = kant_works.find_work("krv_de.html")
    assert krv is not None
    assert krv.code == "krv_de"
    assert krv.title == "Kritik der reinen Vernunft"


def test_emit_uses_work_corpus_and_author(tmp_path: Path):
    """Generalized HegelWork should produce chunks with the work's own
    corpus/author, not the Hegel hardcoded defaults."""
    from minerva.authors import kant_works

    krv = kant_works.WORKS[0]
    chunk = corpus_parse._emit(krv, tmp_path / "krv.html", "Vorrede, ¶1", "body")
    assert chunk is not None
    assert chunk.corpus == "kant"
    assert chunk.author == "Kant"
    assert chunk.work == "Kritik der reinen Vernunft"
    assert chunk.lang == "deu"


# ---------- find_work dispatch ----------


def test_find_work_matches_canonical_filename():
    w = hegel_works.find_work("phenomenology_of_spirit_inwood.pdf")
    assert w is not None
    assert w.code == "phg"
    assert w.translator == "Inwood"


def test_phg_inwood_and_pinkard_are_distinct_works():
    inwood = hegel_works.find_work(
        "georg-wilhelm-friedrich-hegel-the-phenomenology-of-spirit-translated-by-michael-inwood.pdf"
    )
    pinkard = hegel_works.find_work(
        "g-w-f-hegel-the-phenomenology-of-spirit-translated-by-terry-pinkard-1.pdf"
    )
    assert inwood is not None and pinkard is not None
    assert inwood.code == "phg" and pinkard.code == "phg_pinkard"
    assert inwood.title != pinkard.title  # surface-disambiguated in citations
    assert inwood.translator == "Inwood"
    assert pinkard.translator == "Pinkard"


def test_find_work_is_case_insensitive():
    w = hegel_works.find_work(
        "ELEMENTS OF THE PHILOSOPHY OF RIGHT (CAM - GEORG WILHELM FRIEDRICH HEGEL.EPUB"
    )
    assert w is not None
    assert w.code == "pr"


def test_find_work_returns_none_for_unknown_file():
    assert hegel_works.find_work("totally_unrelated.pdf") is None


def test_find_work_supports_alias_filenames():
    # `enz_logic` declares multiple candidate filenames so the user can rename freely.
    aliased = hegel_works.find_work("encyclopedia_of_the_philosophical_sciences.pdf")
    assert aliased is not None
    assert aliased.code == "enz_logic"


def test_enz_parts_have_distinct_max_sections():
    """Encyclopedia Logic ends at §244; Philosophy of Mind runs §377-577."""
    logic = hegel_works.find_work("encyclopedia_of_the_philosophical_sciences.pdf")
    mind = hegel_works.find_work("g-w-f-hegel-philosophy-of-mind-1.pdf")
    assert logic is not None and mind is not None
    assert logic.code == "enz_logic" and mind.code == "enz_mind"
    assert logic.max_section == 244
    assert mind.max_section == 577


# ---------- parse_dir dispatch ----------


def test_parse_dir_skips_unknown_files(tmp_path: Path, capsys):
    # An unknown file should be skipped with a warning, not crash the iterator.
    (tmp_path / "totally_unknown.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    chunks = list(corpus_parse.parse_dir(tmp_path, hegel_works.find_work, label="hegel"))
    assert chunks == []
    captured = capsys.readouterr()
    assert "skipping unknown file" in captured.out


def _multiwork_fixtures() -> tuple[corpus_works.CorpusWork, corpus_works.CorpusWork]:
    def mk(code: str, title: str) -> corpus_works.CorpusWork:
        return corpus_works.CorpusWork(
            code=code,
            title=title,
            translator="Tester",
            edition_year="2026",
            filenames=("omnibus.txt",),
            fmt="txt",
            locator="chapter",
            corpus="kant",
            author="Kant",
        )

    return mk("first", "First Treatise"), mk("second", "Second Treatise")


def test_parse_dir_dispatches_all_works_claiming_a_file(tmp_path: Path):
    """Regression: multi-work files must produce chunks for EVERY claiming
    work. The old reflective `find_works` discovery keyed off
    `find_work.__module__`, which is `minerva.corpus_works` for every
    `make_find_work` closure — so it never fired and 11 of the 12 Gregor
    omnibus Kant works were silently skipped."""
    first, second = _multiwork_fixtures()
    works = (first, second)
    (tmp_path / "omnibus.txt").write_text(
        "A reasonably substantial paragraph of invented prose, long enough "
        "that the paragraph splitter keeps it as a real body chunk rather "
        "than discarding it as front-matter noise or a stray heading line.\n",
        encoding="utf-8",
    )
    find_work = corpus_works.make_find_work(works)

    def find_works(filename: str) -> list[corpus_works.CorpusWork]:
        return [w for w in works if filename in w.filenames]

    chunks = list(corpus_parse.parse_dir(tmp_path, find_work, label="kant", find_works=find_works))
    titles = {c.work for c in chunks}
    assert titles == {"First Treatise", "Second Treatise"}


def test_registry_corpus_label_passes_find_works_to_parse_dir(monkeypatch, tmp_path: Path):
    """The ingest registry must hand the author module's `find_works` to
    `corpus.parse_dir` explicitly — reflective discovery cannot work."""
    from minerva.authors import kant_works
    from minerva.ingest import registry as ingest_registry

    captured: dict[str, object] = {}

    def fake_parse_dir(directory, find_work, *, label, find_works=None):
        captured["find_work"] = find_work
        captured["find_works"] = find_works
        return iter(())

    monkeypatch.setattr(corpus_parse, "parse_dir", fake_parse_dir)
    parse = ingest_registry._corpus_label("kant", "kant_works")
    list(parse(tmp_path))
    assert captured["find_work"] is kant_works.find_work
    assert captured["find_works"] is kant_works.find_works


# ---------- letter-free chunk filter ----------


def test_emit_drops_letter_free_paragraphs(tmp_path: Path):
    """Aphorism-number lines, bare section markers, separators, and OCR
    glyph soup must not become chunks (they were ~6,500 strong before
    the 2026-06-10 cleanup round)."""
    work = _make_work("chapter")
    for junk in ("1", "2.", "§ 9", "----", "■", "• •", "[129]", "+20"):
        assert corpus_parse._emit(work, tmp_path / "x.pdf", "¶1", junk) is None, junk


def test_emit_keeps_short_but_real_text(tmp_path: Path):
    work = _make_work("chapter")
    for real in ("Ha!", "Eis", "ὁ", "von", "Über"):
        chunk = corpus_parse._emit(work, tmp_path / "x.pdf", "¶1", real)
        assert chunk is not None, real


def test_dropping_junk_paragraph_does_not_renumber_survivors(tmp_path: Path):
    """¶ indices are assigned before the filter, so removing a junk
    paragraph must not change the section labels — and therefore the
    content-hashed chunk_ids — of the surviving paragraphs."""
    work = _make_work("chapter")
    body_a = "A real paragraph of invented prose that is long enough to keep."
    body_b = "Another real paragraph of invented prose that also survives."

    chunks = list(
        corpus_parse._split_chapter_block(
            work, tmp_path / "x.pdf", "Vorrede", f"1\n\n{body_a}\n\n2\n\n{body_b}"
        )
    )
    # The junk lines still consume ¶1 and ¶3 — survivors keep the same
    # ¶ index (and so the same content-hashed chunk_id) they had before
    # the filter existed.
    assert [c.section for c in chunks] == ["Vorrede, ¶2", "Vorrede, ¶4"]
    assert [c.text for c in chunks] == [body_a, body_b]


# ---------- oversized paragraphs (#176) ----------

# Jones's 1776 Brutus runs Cicero's dialogue continuously: 251,812 characters
# across 66 blank-line breaks, so one "paragraph" reaches 33,241 chars while
# the same file's Orator half (205 breaks in 206,726 chars) is fine. Opt-in
# per work, because the same splitter serves Hegel's §244, which #385 says
# must NOT be split into ten index chunks.


def _capped_work(cap: int) -> corpus_works.CorpusWork:
    return corpus_works.CorpusWork(
        code="x",
        title="Test CorpusWork",
        translator="T",
        edition_year="2000",
        filenames=("x.txt",),
        fmt="txt",
        locator="chapter",
        max_paragraph_chars=cap,
    )


def _turn(speaker_line: str, filler: int) -> str:
    return f'"{speaker_line} {"word " * filler}end."--'


def test_an_oversized_paragraph_splits_at_speech_turns(tmp_path: Path):
    para = _turn("Upon my word, cried Atticus,", 60) + _turn("As I have been speaking,", 60)
    text = f"CHAPTER ONE\n\n{para}\n"
    chunks = list(corpus_parse.split_by_chapter(text, _capped_work(400), tmp_path / "x.txt"))
    assert len(chunks) > 1
    assert all(len(c.text) <= 400 for c in chunks)


def test_split_pieces_carry_sub_locators_and_do_not_renumber_what_follows(tmp_path: Path):
    """`section` feeds `chunk_id`, so a split must not shift the paragraphs
    after it — that would churn every id downstream of the fix."""

    para = _turn("First speaker,", 60) + _turn("Second speaker,", 60)
    text = f"CHAPTER ONE\n\n{para}\n\nA short second paragraph.\n"
    chunks = list(corpus_parse.split_by_chapter(text, _capped_work(400), tmp_path / "x.txt"))
    sections = [c.section for c in chunks]
    assert sections[0] == "Chapter One, ¶1.1"
    assert sections[1] == "Chapter One, ¶1.2"
    assert sections[-1] == "Chapter One, ¶2"


def test_a_paragraph_within_budget_keeps_its_bare_locator(tmp_path: Path):
    """The churn guard: a paragraph under the cap is emitted exactly as
    before, so its chunk_id — which hashes `section` and `text[:120]` —
    does not move."""

    text = "CHAPTER ONE\n\nA paragraph that is comfortably within budget.\n"
    capped = list(corpus_parse.split_by_chapter(text, _capped_work(400), tmp_path / "x.txt"))
    plain = list(corpus_parse.split_by_chapter(text, _make_work("chapter"), tmp_path / "x.txt"))
    assert [c.section for c in capped] == ["Chapter One, ¶1"]
    assert [c.chunk_id for c in capped] == [c.chunk_id for c in plain]


def test_a_work_without_a_cap_never_splits_a_paragraph(tmp_path: Path):
    """#385's pin. Hegel's §244 is 118,716 chars of which ~1,300 are Hegel;
    splitting it would yield ten index chunks instead of one, so works that
    have not opted in keep whole paragraphs however long."""

    para = _turn("First speaker,", 200) + _turn("Second speaker,", 200)
    text = f"CHAPTER ONE\n\n{para}\n"
    chunks = list(corpus_parse.split_by_chapter(text, _make_work("chapter"), tmp_path / "x.txt"))
    assert len(chunks) == 1
    assert len(chunks[0].text) > 400


def test_an_oversized_paragraph_without_speech_turns_splits_at_sentences(tmp_path: Path):
    """Brutus is dialogue, but two of its ten oversized paragraphs carry no
    turn marker at all — a speech-only rule would leave those whole."""

    para = " ".join(f"Sentence number {i} runs on for a while here." for i in range(40))
    text = f"CHAPTER ONE\n\n{para}\n"
    chunks = list(corpus_parse.split_by_chapter(text, _capped_work(400), tmp_path / "x.txt"))
    assert len(chunks) > 1
    assert all(len(c.text) <= 400 for c in chunks)


def test_no_text_is_lost_when_a_paragraph_splits(tmp_path: Path):
    para = _turn("First speaker,", 60) + _turn("Second speaker,", 60)
    text = f"CHAPTER ONE\n\n{para}\n"
    chunks = list(corpus_parse.split_by_chapter(text, _capped_work(400), tmp_path / "x.txt"))
    squash = lambda s: "".join(s.split())  # noqa: E731 — whitespace-blind comparison
    assert squash("".join(c.text for c in chunks)) == squash(para)


def test_a_single_speech_turn_over_the_cap_splits_at_sentences(tmp_path: Path):
    """Turn boundaries alone leave one 9,070-char piece in the real Brutus:
    Cicero's longest uninterrupted answer is itself over the cap, so an
    oversized turn splits again at its sentence ends."""

    monologue = " ".join(f"Sentence number {i} runs on for a while here." for i in range(40))
    para = f'"{monologue}"--"A short reply."--'
    text = f"CHAPTER ONE\n\n{para}\n"
    chunks = list(corpus_parse.split_by_chapter(text, _capped_work(400), tmp_path / "x.txt"))
    assert all(len(c.text) <= 400 for c in chunks), [len(c.text) for c in chunks]
