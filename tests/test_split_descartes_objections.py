"""Hermetic tests for the Descartes Objections & Réponses splitter.

Fixtures are minimal Parsoid-shaped HTML mirroring the fr.wikisource
transcriptions (Clerselier tr., Cousin ed.). The load-bearing behavior
is **attribution**: the Objections are by other authors — objector
paragraphs must come out ``block_type='objection'`` with the objector
in ``speaker``, while Descartes' replies stay untyped. This is the
misattribution trap the remediation plan flags for this corpus
(mirror of the editorial-note work in PRs #24–#26).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from minerva.corpus.split_descartes_objections import split_descartes_objections
from minerva.corpus_works import CorpusWork

pytest.importorskip("bs4", reason="objections splitter needs beautifulsoup4")

_WORK = CorpusWork(
    code="objections",
    title="Objections et Réponses",
    translator="Clerselier (éd. Cousin)",
    edition_year="1647",
    filenames=("objections_obj1.html",),
    fmt="html",
    locator="descartes_objections",
    lang="fra",
    corpus="descartes",
    author="Descartes",
)


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(
        f"<html><head><style>.x{{}}</style></head><body>{body}</body></html>",
        encoding="utf-8",
    )
    return p


def test_objection_paragraphs_carry_objector_voice(tmp_path: Path) -> None:
    body = """
      <table class="headertemplate"><tr><td>Œuvres de Descartes, Levrault, 1824</td></tr></table>
      <p>Aussitôt que j’ai reconnu le désir que vous aviez.</p>
      <p>Je pense, donc je suis ; voire même je suis la pensée.</p>
    """
    chunks = list(split_descartes_objections(_write(tmp_path, "objections_obj1.html", body), _WORK))
    assert len(chunks) == 2
    assert all(c.block_type == "objection" for c in chunks)
    assert all(c.speaker == "Caterus" for c in chunks)
    assert chunks[0].section == "Obj. I, ¶ 1"
    assert chunks[0].book == "Premières objections (Caterus)"
    # The wikisource header chrome never leaks into chunk text.
    assert "Levrault" not in " ".join(c.text for c in chunks)


def test_replies_are_descartes_untyped(tmp_path: Path) -> None:
    body = "<p>Je n’ai pas eu peu de satisfaction de lire vos objections.</p>"
    chunks = list(split_descartes_objections(_write(tmp_path, "objections_rep1.html", body), _WORK))
    assert len(chunks) == 1
    assert chunks[0].block_type is None
    assert chunks[0].speaker is None
    assert chunks[0].section == "Rép. I, ¶ 1"


def test_hobbes_interleave_flips_voice_on_headings(tmp_path: Path) -> None:
    # obj3 shape: centered-div OBJECTION/RÉPONSE headings alternate the
    # voice between Hobbes and Descartes within one page.
    body = """
      <div style="text-align:center;clear:both;"><span style="font-size:125%">OBJECTION I</span><sup>re</sup>.</div>
      <p>Il paroît assez qu’il n’y a point de critérium.</p>
      <div style="text-align:center;"><span>RÉPONSE.</span></div>
      <p>Les raisons de douter ici reçues pour vraies.</p>
      <div style="text-align:center;"><span>OBJECTION II.</span></div>
      <div style="text-align:center;"><span>SUR LA SECONDE MÉDITATION.</span></div>
      <p>Je suis une chose qui pense : c’est fort bien dit.</p>
    """
    chunks = list(split_descartes_objections(_write(tmp_path, "objections_obj3.html", body), _WORK))
    voices = [(c.section, c.block_type, c.speaker) for c in chunks]
    assert voices == [
        ("Obj. III, ¶ 1", "objection", "Hobbes"),
        ("Obj. III, ¶ 2", None, None),
        ("Obj. III, ¶ 3", "objection", "Hobbes"),
    ]
    # A topic heading (SUR LA SECONDE MÉDITATION) must not flip the voice.


def test_obj6_addition_de_descartes_is_his_voice(tmp_path: Path) -> None:
    body = """
      <p>Première difficulté proposée par divers théologiens.</p>
      <h3>ADDITION DE DESCARTES.</h3>
      <p>Pour la clarté je réponds ici par avance.</p>
      <h3>DES PHILOSOPHES ET GÉOMÈTRES</h3>
      <h3>À M. DESCARTES.</h3>
      <p>Seconde batterie de difficultés.</p>
    """
    chunks = list(split_descartes_objections(_write(tmp_path, "objections_obj6.html", body), _WORK))
    assert [(c.block_type, c.speaker) for c in chunks] == [
        ("objection", "divers théologiens et philosophes"),
        (None, None),
        ("objection", "divers théologiens et philosophes"),
    ]


def test_footnotes_and_pagenums_stripped(tmp_path: Path) -> None:
    body = """
      <p>Un texte<sup class="mw-ref reference"><a>[1]</a></sup> avec
      <span class="ws-pagenum" id="353" title="Page:x.djvu/359">353</span> du bruit.</p>
      <ol class="references"><li>Note de Cousin.</li></ol>
    """
    chunks = list(split_descartes_objections(_write(tmp_path, "objections_obj2.html", body), _WORK))
    assert len(chunks) == 1
    assert chunks[0].text == "Un texte avec du bruit."
    assert chunks[0].speaker == "Mersenne"


def test_unknown_filename_yields_nothing(tmp_path: Path) -> None:
    chunks = list(
        split_descartes_objections(_write(tmp_path, "objections_obj9.html", "<p>x</p>"), _WORK)
    )
    assert chunks == []
