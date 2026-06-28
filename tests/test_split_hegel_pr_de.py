"""Unit tests for the German Hegel Philosophy of Right parser.

Hermetic: builds a tiny zeno-shaped HTML + a Gans-shaped Zusätze sibling
file in tmp_path. Locks: accumulate-by-§-number (handles duplicate
out-of-order TOC headings), first-para-main / rest-Remark, page-marker
stripping, ad-cruft skipping, Vorrede capture, and Addition splicing.
"""

from __future__ import annotations

from pathlib import Path

from minerva.corpus.split_hegel_pr_de import split_hegel_pr_de
from minerva.corpus_works import CorpusWork

_HTML = """\
<h2>Vorrede</h2>
<p class="zenoPLm4n0">Vorrede mit der Eule der Minerva.</p>
<h4>§ 1</h4>
<p class="zenoPLm4n0">[29] Hauptsatz eins.</p>
<p class="zenoPLm4n0">Anmerkung zu eins.</p>
<p class="empf">Buchempfehlung</p>
<h5>§ 2</h5>
<p class="zenoPLm4n0">Hauptsatz zwei ohne Anmerkung.</p>
<h6>§ 1</h6>
"""

_ZUSAETZE = """\
Zusätze.
1. Zusatz zu § 1. (Thema eins.) Zusatztext eins.
2. Zusatz zu § 2. (Thema zwei.) Zusatztext zwei.
"""


def _work() -> CorpusWork:
    return CorpusWork(
        code="pr_de",
        title="Grundlinien der Philosophie des Rechts",
        translator="(Original)",
        edition_year="1820",
        filenames=("pr_de.html",),
        fmt="html",
        locator="pr_de_structured",
        lang="deu",
        front_matter_headings=("Vorrede",),
    )


def _parse(tmp_path: Path):
    (tmp_path / "pr_de.html").write_text(_HTML, encoding="utf-8")
    (tmp_path / "pr_de_zusaetze.txt").write_text(_ZUSAETZE, encoding="utf-8")
    return list(split_hegel_pr_de(tmp_path / "pr_de.html", _work()))


def _by(chunks):
    out: dict[tuple[str, object], str] = {}
    for c in chunks:
        out[(c.section, c.block_type)] = c.text
    return out


def test_main_and_remark_split(tmp_path: Path):
    by = _by(_parse(tmp_path))
    # First paragraph = main (page marker [29] stripped); rest = Remark.
    assert by[("§1", None)] == "Hauptsatz eins."
    assert by[("§1 Anmerkung", "remark")] == "Anmerkung zu eins."


def test_section_without_remark(tmp_path: Path):
    by = _by(_parse(tmp_path))
    assert by[("§2", None)] == "Hauptsatz zwei ohne Anmerkung."
    assert ("§2 Anmerkung", "remark") not in by


def test_additions_spliced_and_cleaned(tmp_path: Path):
    by = _by(_parse(tmp_path))
    # Leading "Zusatz zu § N." header is consumed; topic parenthetical kept.
    assert by[("§1 Zusatz", "addition")] == "(Thema eins.) Zusatztext eins."
    assert by[("§2 Zusatz", "addition")] == "(Thema zwei.) Zusatztext zwei."


def test_vorrede_front_matter(tmp_path: Path):
    chunks = _parse(tmp_path)
    vor = [c for c in chunks if c.book == "Vorrede"]
    assert len(vor) == 1
    assert vor[0].section == "Vorrede, ¶1"
    assert "Eule der Minerva" in vor[0].text


def test_cruft_skipped_and_no_duplicates(tmp_path: Path):
    chunks = _parse(tmp_path)
    text = " ".join(c.text for c in chunks)
    assert "Buchempfehlung" not in text
    # The duplicate out-of-order <h6>§ 1</h6> (no prose) must not create a
    # second §1 main chunk.
    s1_main = [c for c in chunks if c.section == "§1" and c.block_type is None]
    assert len(s1_main) == 1
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_emitted_in_numeric_order(tmp_path: Path):
    chunks = [c for c in _parse(tmp_path) if c.book is None]
    import re

    nums = [int(re.match(r"§(\d+)", c.section).group(1)) for c in chunks]
    assert nums == sorted(nums)
