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


# ── OCR-mangled Google Books watermark (#401) ─────────────────────────

# The Gans appendix is a Google Books scan: the watermark lands on 104 page
# breaks, and `_clean_ocr` strips the well-formed ones. Eight chunks survive
# it in the live corpus because the OCR mangles the word differently each
# time — measured in `pr_de_zusaetze.txt`.

_OCR_VARIANTS = (
    "Digitized by Googk",  # already handled; the pin
    "Digitized by Google",
    "Digitized by VjOOQIC",
    "Digitized by VjOOQ IC",
    "Digitized by Go^k",
    "Digitized by Goos.",
    "Digitized by Ggjogk",
)


def test_every_ocr_variant_of_the_watermark_is_stripped(tmp_path: Path):
    zusaetze = "Zusätze.\n" + "".join(
        f"{i}. Zusatz zu § {i}. (Thema.) Vor dem Umbruch {v} nach dem Umbruch.\n"
        for i, v in enumerate(_OCR_VARIANTS, 1)
    )
    (tmp_path / "pr_de.html").write_text(
        "".join(f"<h4>§ {i}</h4>\n<p class=\"zenoPLm4n0\">Hauptsatz {i}.</p>\n" for i in range(1, 8)),
        encoding="utf-8",
    )
    (tmp_path / "pr_de_zusaetze.txt").write_text(zusaetze, encoding="utf-8")
    chunks = list(split_hegel_pr_de(tmp_path / "pr_de.html", _work()))
    additions = [c.text for c in chunks if c.block_type == "addition"]
    assert len(additions) == len(_OCR_VARIANTS)
    for text in additions:
        assert "Digitized" not in text, text
        assert "VjOOQ" not in text, text
    # And the prose either side of the watermark survives, joined.
    assert all("Vor dem Umbruch" in t and "nach dem Umbruch" in t for t in additions)


def test_back_matter_after_the_last_addition_is_not_glued_onto_it(tmp_path: Path):
    """The appendix ends with the editor's textual notes, a name index, a
    subject index, the printer's colophon and a library circulation slip.
    All of it landed in the last Zusatz: `§339 Zusatz` measured 16,498
    characters of which 501 — 3% — are Hegel, which is #385's shape."""

    zusaetze = (
        "Zusätze.\n"
        "1. Zusatz zu § 1. (Thema.) Der höhere Prätor ist der Weltgeist.\n"
        "Zur Feststellung des Textes. Die Ausgabe von Gans folgt der Handschrift.\n"
        "Namenregister. Aristoteles 119f., 137. Spinoza 68.\n"
        "Sachregister. A. Aberglauben 68. Zwölftafelgesetz 22 f.\n"
        "Druck von C. Grombach in Leipzig.\n"
        "STANFORD UNIVERSITY LIBRARIES All books are subject to recall. DATE DUE\n"
    )
    (tmp_path / "pr_de.html").write_text(
        '<h4>§ 1</h4>\n<p class="zenoPLm4n0">Hauptsatz eins.</p>\n', encoding="utf-8"
    )
    (tmp_path / "pr_de_zusaetze.txt").write_text(zusaetze, encoding="utf-8")
    chunks = list(split_hegel_pr_de(tmp_path / "pr_de.html", _work()))
    addition = next(c.text for c in chunks if c.block_type == "addition")
    assert addition == "(Thema.) Der höhere Prätor ist der Weltgeist."
    for leaked in ("Namenregister", "Sachregister", "Grombach", "STANFORD", "DATE DUE"):
        assert leaked not in addition
