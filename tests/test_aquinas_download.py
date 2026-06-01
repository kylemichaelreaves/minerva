"""Offline tests for ``perseus/download_aquinas.py`` citation parsing.

No network — exercises the regex harvest + ST/SCG grouping logic that
``split_aquinas.py`` depends on.
"""

from __future__ import annotations

import sys
from pathlib import Path

perseus_dir = Path(__file__).resolve().parents[1] / "perseus"
sys.path.insert(0, str(perseus_dir))
import download_aquinas as aq  # noqa: E402


_SAMPLE_ST_HTML = """
<P TITLE="I q. 1 pr."><A NAME="28232"><SPAN CLASS="ref">[28232] I q. 1 pr. </SPAN></A>Question prologue.</P>
<P TITLE="I q. 1 a. 1 arg. 1"><A NAME="28233"><SPAN CLASS="ref">[28233] I q. 1 a. 1 arg. 1 </SPAN></A>First objection.</P>
<P TITLE="I q. 1 a. 1 co."><A NAME="28236"><SPAN CLASS="ref">[28236] I q. 1 a. 1 co. </SPAN></A>Corpus of the article.</P>
"""

_SAMPLE_SCG_HTML = """
<P TITLE="Contra Gentiles, lib. 1 cap. 1 n. 1"><A NAME="23489"><SPAN CLASS="ref">[23489] Contra Gentiles, lib. 1 cap. 1 n. 1 </SPAN></A>Para one.</P>
<P TITLE="Contra Gentiles, lib. 1 cap. 1 n. 2"><A NAME="23490"><SPAN CLASS="ref">[23490] Contra Gentiles, lib. 1 cap. 1 n. 2 </SPAN></A>Para two.</P>
"""


def test_parse_st_locator_article():
    loc = aq._parse_st_locator("I q. 1 a. 1 arg. 1")
    assert loc == (1, 1, 1, "arg. 1")


def test_parse_st_locator_question_prologue():
    loc = aq._parse_st_locator("I q. 1 pr.")
    assert loc == (1, 1, 0, None)


def test_cite_to_st_title_normalizes_ordf():
    title = aq._cite_to_st_title("I&ordf; q. 2 a. 3 co.")
    assert title == "I q. 2 a. 3 co."
    loc = aq._parse_st_locator(title)
    assert loc == (1, 2, 3, "co.")


def test_iter_blocks_strips_html():
    blocks = list(aq._iter_blocks(_SAMPLE_ST_HTML))
    assert len(blocks) == 3
    assert blocks[1].body == "First objection."


def test_st_grouping_merges_subsections(monkeypatch):
    """Two sub-sections under one article become one marker + inline labels."""

    def fake_fetch_page(slug: str) -> str:
        del slug
        return _SAMPLE_ST_HTML

    monkeypatch.setattr(aq, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(aq, "time", type("T", (), {"sleep": staticmethod(lambda _: None)})())

    chunks = aq._extract_st(("sth1001.html",))
    assert len(chunks) == 2
    assert chunks[0][0] == "[ST.1.1.0]"
    assert chunks[1][0] == "[ST.1.1.1]"
    assert "[arg. 1]" in chunks[1][1]
    assert "Corpus of the article." in chunks[1][1]


def test_scg_grouping_by_chapter(monkeypatch):
    def fake_fetch_page(slug: str) -> str:
        del slug
        return _SAMPLE_SCG_HTML

    monkeypatch.setattr(aq, "_fetch_page", fake_fetch_page)
    monkeypatch.setattr(aq, "time", type("T", (), {"sleep": staticmethod(lambda _: None)})())

    chunks = aq._extract_scg(("scg1001.html",))
    assert len(chunks) == 1
    assert chunks[0][0] == "[SCG.1.1]"
    assert "[n. 1]" in chunks[0][1]
    assert "[n. 2]" in chunks[0][1]
