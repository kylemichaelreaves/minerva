"""Unit tests for the eKGWB Nachlass splitter (`corpus/split_ekgwb`).

Feeds a minimal eKGWB-shaped HTML fixture (the real saved pages from
nietzschesource.org have the same div1/head/txt_block structure) and
asserts: one chunk per fragment, canonical NF- sigla, editorial
apparatus stripped, and a group `book` label derived from the header.
"""

from __future__ import annotations

from pathlib import Path

from minerva.authors.nietzsche_works import find_work
from minerva.corpus.split_ekgwb import split_ekgwb
from minerva.corpus_works import CorpusWork

# Mirrors the eKGWB markup: a page header carrying "[25 = W I 1. Frühjahr
# 1884]", then div1 fragment blocks each with a `.head` siglum, body
# `.p` paragraphs, and a `.footnotes` apparatus block that must be dropped.
_FIXTURE = """
<html><body>
<div class="divided">
 <div class="txt_block">
  <div class="header_text">[25 = W I 1. Frühjahr 1884]</div>
  <div class="div1"><div class="head">25[1]</div>
    <div class="p">Die ewige Wiederkunft. Eine Wahrsagung.</div>
    <div class="footnotes">Erratum: stoßen lies: stossen. Nach KGW/KGB.</div>
  </div>
  <div class="div1"><div class="head">25[2]</div>
    <div class="p">Meine Aufgaben: <span class="tooltip_corrige">corr</span>Selbst-Erlösung.</div>
  </div>
  <div class="div1"><div class="head">25[3]</div>
    <div class="p">„Das Paradies ist unter dem Schatten der Schwerter.“</div>
  </div>
 </div>
</div>
</body></html>
"""


def _work() -> CorpusWork:
    return CorpusWork(
        code="nachlass_kgw_1884_25",
        title="Nachgelassene Fragmente (KGW)",
        translator="(Original)",
        edition_year="1884",
        filenames=("nachlass_kgw_1884_25.html",),
        fmt="html",
        locator="ekgwb",
        lang="deu",
        corpus="nietzsche",
        author="Nietzsche",
        citation_system="paragraph",
    )


def test_split_ekgwb_one_chunk_per_fragment() -> None:
    chunks = list(split_ekgwb(_FIXTURE, _work(), Path("nachlass_kgw_1884_25.html")))
    assert [c.section for c in chunks] == [
        "NF-1884,25[1]",
        "NF-1884,25[2]",
        "NF-1884,25[3]",
    ]
    assert chunks[0].text.startswith("Die ewige Wiederkunft")
    assert all(c.book == "Nachgelassene Fragmente 1884 (Gruppe 25)" for c in chunks)
    assert all(c.lang == "deu" and c.author == "Nietzsche" for c in chunks)


def test_split_ekgwb_strips_apparatus() -> None:
    chunks = list(split_ekgwb(_FIXTURE, _work(), Path("nachlass_kgw_1884_25.html")))
    joined = "\n".join(c.text for c in chunks)
    # Editorial apparatus / correction tooltips are dropped.
    assert "Erratum" not in joined
    assert "KGW/KGB" not in joined
    assert "corr" not in joined
    # The siglum label itself isn't duplicated into the body.
    assert "25[1]" not in chunks[0].text


def test_split_ekgwb_skips_fragments_emit_drops() -> None:
    # A fragment whose body is letter-free (a bare separator) is dropped by
    # `_emit`; the splitter must skip it rather than yield None.
    fixture = """
    <html><body>
    <div class="divided">
     <div class="txt_block">
      <div class="header_text">[25 = W I 1. Frühjahr 1884]</div>
      <div class="div1"><div class="head">25[1]</div>
        <div class="p">----</div>
      </div>
      <div class="div1"><div class="head">25[2]</div>
        <div class="p">Die ewige Wiederkunft. Eine Wahrsagung.</div>
      </div>
     </div>
    </div>
    </body></html>
    """
    chunks = list(split_ekgwb(fixture, _work(), Path("nachlass_kgw_1884_25.html")))
    assert [c.section for c in chunks] == ["NF-1884,25[2]"]


def test_split_ekgwb_types_title_draft_fragments_as_signature() -> None:
    # #291: a fragment that IS a draft book-title line ending in his own
    # name ranks over Nietzsche's actual philosophy on any query
    # containing "Nietzsche" unless typed and capped like apparatus.
    fixture = """
    <html><body>
    <div class="divided">
     <div class="txt_block">
      <div class="header_text">[25 = W I 1. Frühjahr 1884]</div>
      <div class="div1"><div class="head">25[1]</div>
        <div class="p">Die ewige Wiederkunft. Eine Wahrsagung.</div>
      </div>
      <div class="div1"><div class="head">25[2]</div>
        <div class="p">Der Spiegel. Versuch einer Selbstabschätzung. Von Friedrich Nietzsche.</div>
      </div>
     </div>
    </div>
    </body></html>
    """
    chunks = list(split_ekgwb(fixture, _work(), Path("nachlass_kgw_1884_25.html")))
    assert chunks[0].block_type is None
    assert chunks[1].block_type == "signature"


def test_find_work_recognises_dropped_notebook() -> None:
    # Drop-and-go: a not-yet-listed notebook filename still resolves.
    w = find_work("nachlass_kgw_1888_14.html")
    assert w is not None
    assert w.locator == "ekgwb"
    assert w.title == "Nachgelassene Fragmente (KGW)"
    # Constant across notebooks: one edition per (work, language).
    assert w.edition_year == "1869-1889"
    assert find_work("not_a_match.html") is None
