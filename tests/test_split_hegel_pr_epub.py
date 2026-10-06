"""Unit tests for the structure-aware Hegel Philosophy of Right EPUB parser.

Uses a tiny synthetic EPUB (a zip of XHTML files mimicking the Cambridge
edition's markup) so the test is hermetic — no dependency on the real
data file. Locks the typed-chunk contract: main / remark / addition per §,
multi-paragraph block merging, footnote skipping, Preface capture,
back-matter exclusion, and strictly-increasing § acceptance.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from minerva.corpus.split_hegel_pr_epub import split_hegel_pr_epub
from minerva.corpus_works import CorpusWork

_BODY = """\
<h4>§ 1</h4>
<p class="noindent">Main text of section one.</p>
<p class="blockquote">Remark paragraph of section one.</p>
<p class="blockquote">Remark continues here.</p>
<p class="noindentt">Addition (H). Addition begins.</p>
<p class="noindent">Addition continues in a second paragraph.</p>
<h4>§ 2</h4>
<p class="noindent">Section two main only.</p>
<p class="footnote">12 This footnote must be skipped.</p>
<h6>§ 1 (see above)</h6>
<p class="noindent">Cross-reference body that belongs to section two.</p>
"""

_FRONT = """\
<h1>Preface</h1>
<p class="noindent">Preface paragraph with the owl of Minerva.</p>
"""

_BACK = """\
<h1>Editorial notes</h1>
<h5>§ 1</h5>
<p class="noindent">Endnote text that must be excluded.</p>
"""


def _make_epub(tmp: Path) -> Path:
    p = tmp / "pr.epub"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("text/part0001.html", _FRONT)
        z.writestr("text/part0002.html", _BODY)
        z.writestr("text/part0003.html", _BACK)
    return p


def _work() -> CorpusWork:
    return CorpusWork(
        corpus="hegel",
        author="Hegel",
        code="pr",
        title="Elements of the Philosophy of Right",
        translator="Wood / Nisbet",
        edition_year="1991",
        filenames=("pr.epub",),
        fmt="epub",
        locator="pr_structured",
        front_matter_headings=("Preface",),
    )


def _parse(tmp_path: Path):
    return list(split_hegel_pr_epub(_make_epub(tmp_path), _work()))


def test_typed_blocks_per_section(tmp_path: Path):
    chunks = _parse(tmp_path)
    by = {(c.section, c.block_type): c.text for c in chunks}

    assert by[("§1", None)] == "Main text of section one."
    # Consecutive blockquote paragraphs merge into one remark chunk.
    assert by[("§1 Remark", "remark")] == (
        "Remark paragraph of section one.\n\nRemark continues here."
    )
    # The "Addition" trigger paragraph plus its noindent continuation merge
    # into one addition chunk (mode carries past the first line).
    assert by[("§1 Addition", "addition")] == (
        "Addition (H). Addition begins.\n\nAddition continues in a second paragraph."
    )


def test_footnote_skipped(tmp_path: Path):
    text = " ".join(c.text for c in _parse(tmp_path))
    assert "footnote must be skipped" not in text


def test_preface_captured_as_book(tmp_path: Path):
    chunks = _parse(tmp_path)
    pref = [c for c in chunks if c.book == "Preface"]
    assert len(pref) == 1
    assert pref[0].block_type is None
    assert pref[0].section == "Preface, ¶1"
    assert "owl of Minerva" in pref[0].text


def test_back_matter_excluded(tmp_path: Path):
    text = " ".join(c.text for c in _parse(tmp_path))
    assert "Endnote text" not in text


def test_strictly_increasing_sections(tmp_path: Path):
    chunks = _parse(tmp_path)
    # The backward "§ 1 (see above)" heading inside section two is a
    # spurious cross-reference: it must NOT reopen §1, and its body
    # attaches to §2 instead.
    s2 = [c for c in chunks if c.section.startswith("§2")]
    s2_text = " ".join(c.text for c in s2)
    assert "Cross-reference body that belongs to section two" in s2_text
    # §1 main is unchanged (not overwritten by the cross-ref body).
    s1_main = [c for c in chunks if c.section == "§1" and c.block_type is None]
    assert len(s1_main) == 1
    assert s1_main[0].text == "Main text of section one."


def test_block_type_values(tmp_path: Path):
    kinds = {c.block_type for c in _parse(tmp_path)}
    assert kinds == {None, "remark", "addition"}
