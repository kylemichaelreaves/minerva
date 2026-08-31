"""Hermetic tests for the Das Kapital MEW splitter.

Fixtures mirror the mlwerke.de page anatomy (verified against the
Wayback capture of me23_049.htm): nav header + source-note ``<SMALL>``,
centered heading block, body ``<P>`` paragraphs with inline MEW page
anchors (``<A NAME="S49">&lt;49&gt;</A>``) and footnote calls
(``<A NAME="Z1"><A HREF="#M1">(1)</A></A>``), then ``<HR>`` +
"Fußnoten" + ``<A NAME="Mn">`` note bodies with ``<=`` backlinks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minerva.corpus.split_kapital_mew import split_kapital_mew
from minerva.corpus_works import CorpusWork

pytest.importorskip("bs4", reason="Kapital MEW splitter needs beautifulsoup4")

_WORK = CorpusWork(
    code="kapital_bd1",
    title="Das Kapital, Band I",
    translator="(Original)",
    edition_year="1867",
    filenames=(),
    fmt="html",
    locator="kapital_mew",
    lang="deu",
    corpus="marx",
    author="Marx",
)

_PAGE = """<HTML><HEAD>
<TITLE>Ware und Geld - 1. Die Ware</TITLE>
</HEAD><BODY>
<P ALIGN="CENTER"><A HREF="me23_041.htm">Zur vierten Auflage</A> | <A HREF="me23_000.htm">Inhalt</A> | <A HREF="me23_099.htm">2. Kapitel</A></P>
<SMALL>Seitenzahlen verweisen auf: Karl Marx - Friedrich Engels - Werke, Band 23, Berlin/DDR 1968</SMALL>
<P ALIGN="CENTER">ERSTES KAPITEL <BR><FONT SIZE="+2">Die Ware</FONT></P>
<B><P><A NAME="S49">&lt;49&gt;</A></B> Der Reichtum der Gesellschaften erscheint als eine "ungeheure Warensammlung"<A NAME="Z1"><A HREF="#M1">(1)</A></A>, die einzelne Ware als seine Elementarform.</P>
<P>Die Ware ist zun&auml;chst ein &auml;u&szlig;erer <A NAME="S50"><B>&lt;50&gt;</B></A> Gegenstand.</P>
<P><HR></P>
<P>Fu&szlig;noten</P>
<P><A NAME="M1">(1)</A> <I>Karl Marx</I>, "Zur Kritik der Politischen &Ouml;konomie", Berlin 1859, pag. 3. <A HREF="#Z1">&lt;=</A></P>
</BODY></HTML>"""


def _split(tmp_path: Path, name: str = "me23_049.htm", html: str = _PAGE) -> list:
    p = tmp_path / name
    p.write_text(html, encoding="utf-8")
    return list(split_kapital_mew(p, _WORK))


def test_paragraphs_with_mew_page_numbers(tmp_path: Path) -> None:
    chunks = _split(tmp_path)
    body = [c for c in chunks if c.block_type is None]
    assert len(body) == 2
    # The book label comes from the in-page KAPITEL head, not the
    # <TITLE> — Band II's titles carry only the Abschnitt, so the
    # head is the authoritative chapter label everywhere.
    assert body[0].section == "Erstes Kapitel: Die Ware, ¶ 1"
    assert body[0].book == "Erstes Kapitel: Die Ware"
    assert body[0].page == "49"  # MEW 23, S. 49 — the citable locator
    assert body[0].text.startswith("Der Reichtum der Gesellschaften")
    # Footnote call marker "(1)" stays in the text; the page marker
    # "<49>" does not.
    assert "(1)" in body[0].text
    assert "<49>" not in body[0].text
    # Second paragraph starts on p. 49 but contains the S50 anchor —
    # the page attr reflects where the paragraph's marker sits.
    assert body[1].page == "50"
    assert "<50>" not in body[1].text


def test_marx_footnotes_become_remark_chunks(tmp_path: Path) -> None:
    chunks = _split(tmp_path)
    notes = [c for c in chunks if c.block_type == "remark"]
    assert len(notes) == 1
    n = notes[0]
    assert n.section == "Erstes Kapitel: Die Ware, Fn. (1)"
    assert n.text.startswith('(1) Karl Marx, "Zur Kritik')
    # The <= backlink arrow is stripped.
    assert "<=" not in n.text
    # Attribution stays Marx (that's why these are 'remark', not
    # 'note' — the retrieval layer credits 'note' to an editor).
    assert n.author == "Marx"


def test_header_chrome_is_stripped(tmp_path: Path) -> None:
    chunks = _split(tmp_path)
    joined = " ".join(c.text for c in chunks)
    assert "Seitenzahlen verweisen" not in joined
    assert "Inhalt" not in joined
    assert "ERSTES KAPITEL" not in joined  # centered heads aren't chunks


def test_source_note_is_stripped_when_it_sits_inside_a_paragraph(
    tmp_path: Path,
) -> None:
    """The note is not always in ``<SMALL>`` (#298).

    Verbatim from ``me25_627.htm``: 17 Band III files open the note with
    ``<FONT SIZE=2><P>`` and close the font *before* the ``</P>``, so it
    is a real paragraph as far as the body loop is concerned and the
    ``<small>``-only strip cannot see it. Those 17, plus one stale row
    from a different source, are the 18 corpus chunks that led with a
    bibliographic note — and at 100-plus characters it clears every
    length floor in the retrieval path.
    """

    html = _PAGE.replace(
        "<SMALL>Seitenzahlen verweisen auf: Karl Marx - Friedrich Engels - "
        "Werke, Band 23, Berlin/DDR 1968</SMALL>",
        "<FONT SIZE=2><P>Seitenzahlen verweisen auf: Karl Marx - Friedrich "
        'Engels - Werke, Band 25, "Das Kapital", Bd. III, Sechster '
        "Abschnitt, S. 627 - 652<BR>\nDietz Verlag, Berlin/DDR 1983</FONT> </P>",
    )
    chunks = _split(tmp_path, name="me25_627.htm", html=html)
    joined = " ".join(c.text for c in chunks)
    assert "Seitenzahlen verweisen" not in joined
    assert "Dietz Verlag" not in joined
    # And the body survives — the strip must not eat the page.
    assert any(c.text.startswith("Der Reichtum der Gesellschaften") for c in chunks)


def test_a_paragraph_merely_mentioning_the_note_is_kept(tmp_path: Path) -> None:
    """The match is anchored to the start of the paragraph. Marx's own
    prose discusses page references, and a substring rule would delete
    it."""

    html = _PAGE.replace(
        "Der Reichtum der Gesellschaften",
        "Die Seitenzahlen verweisen auf eine Ausgabe, die Der Reichtum der Gesellschaften",
    )
    chunks = _split(tmp_path, html=html)
    assert any("Der Reichtum der Gesellschaften" in c.text for c in chunks)


def test_volume_from_filename(tmp_path: Path) -> None:
    chunks = _split(tmp_path, name="me25_033.htm")
    assert all(c.work == "Das Kapital, Band III" for c in chunks)


def test_toc_file_yields_nothing(tmp_path: Path) -> None:
    assert _split(tmp_path, name="me23_000.htm") == []


def test_single_part_title_used_whole(tmp_path: Path) -> None:
    # A preface page: single-part <TITLE>, no KAPITEL head — the
    # title is the label (until a Vorwort head refines it).
    html = _PAGE.replace(
        "<TITLE>Ware und Geld - 1. Die Ware</TITLE>",
        "<TITLE>Vorwort zur ersten Auflage</TITLE>",
    ).replace(
        '<P ALIGN="CENTER">ERSTES KAPITEL <BR><FONT SIZE="+2">Die Ware</FONT></P>',
        "",
    )
    chunks = _split(tmp_path, html=html)
    assert chunks[0].book == "Vorwort zur ersten Auflage"


def test_kapitel_head_with_footnote_call_is_cleaned(tmp_path: Path) -> None:
    html = _PAGE.replace(
        'ERSTES KAPITEL <BR><FONT SIZE="+2">Die Ware</FONT>',
        'ACHTZEHNTES KAPITEL <BR><FONT SIZE="+2">(34) Einleitung</FONT>',
    )
    chunks = _split(tmp_path, html=html)
    assert chunks[0].book == "Achtzehntes Kapitel: Einleitung"
