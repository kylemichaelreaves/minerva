"""Unit tests for the structure-aware Spinoza *Ethica* parser.

Hermetic: builds tiny per-Part HTML fixtures in tmp_path that reproduce
the awkward shapes of the real thelatinlibrary.com source. Locks the
behaviours that were genuine bugs during the re-source:

  * unclosed ``<p>`` tags (Parts II–V) must parse flat via lxml, not
    nest 200-deep and duplicate text;
  * Scholia / Explicationes are typed ``block_type='remark'``, the rest
    body — all still Spinoza's own words;
  * a proposition splits into P / Dem. / Schol. (and Schol. 2 for the
    double scholium);
  * Part I has no DEFINITIONES/AXIOMATA headers — def-then-axiom is
    inferred from the numbering reset;
  * "PROPOSITIO" whose body contains the substring "fatio" is NOT
    swallowed by the PRÆFATIO branch (the Part IV regression);
  * singular "AXIOMA: …" is a labelled axiom, and Part II's
    physical-digression axioms (after props begin) are tagged "(Lem.)"
    so they don't collide with the main axioms.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from minerva.corpus.split_spinoza_ethica import split_spinoza_ethica
from minerva.corpus_works import CorpusWork


def _work() -> CorpusWork:
    return CorpusWork(
        code="ethica",
        title="Ethica",
        translator="(Original)",
        edition_year="1677",
        filenames=(),
        fmt="html",
        locator="spinoza_ethica",
        lang="lat",
        corpus="spinoza",
        author="Spinoza",
    )


def _parse(tmp_path: Path, name: str, html: str):
    p = tmp_path / name
    p.write_text(html, encoding="latin-1")
    return list(split_spinoza_ethica(p, _work()))


def _by_section(chunks):
    return {c.section: c for c in chunks}


# Part I: well-formed, no DEFINITIONES/AXIOMATA headers, a proposition
# with demonstration + a DOUBLE scholium, and an EXPLICATIO on a def.
_PART1 = """\
<html><body>
<center>SPINOZAE ETHICA</center>
<p>I . Per causam sui intelligo id cujus essentia involvit existentiam.</p>
<p>II . Per substantiam intelligo id quod in se est.</p>
<p>EXPLICATIO : Dico substantiam quia per se concipitur.</p>
<p>I . Omnia quae sunt vel in se vel in alio sunt.</p>
<p>II . Id quod per aliud non potest concipi per se concipi debet.</p>
<p>PROPOSITIO I : Substantia prior est natura suis affectionibus.</p>
<p>DEMONSTRATIO : Patet ex definitione 3 et 5.</p>
<p>SCHOLIUM : Prima ratio scholii.</p>
<p>SCHOLIUM : Secunda ratio scholii.</p>
<p>The Latin Library</p>
</body></html>
"""

# Part IV: unclosed <p> tags (no </p>), a PRAEFATIO, a singular
# "AXIOMA:", and a PROPOSITIO whose body contains "fatio" (the bug).
_PART4 = """\
<html><body>
<center>PARS QUARTA<p>DE SERVITUTE HUMANA</center>
<p>PRAEFATIO : Humanam impotentiam voco servitutem.
<p>I. Per bonum id intelligam quod certo scimus nobis esse utile.
<p>AXIOMA: Nulla res singularis in rerum natura datur qua potentior.
<p>PROPOSITIO I : Nihil quod idea falsa positivum habet tollitur satisfactio veri.
<p>DEMONSTRATIO : Falsitas in sola privatione consistit.
<p>SCHOLIUM : Intelligitur haec propositio clarius.
</body></html>
"""

# Part II tail: a physical-digression axiom that appears AFTER a
# proposition has begun — must be tagged "(Lem.)".
_PART2 = """\
<html><body>
<p>AXIOMATA</p>
<p>I. Hominis essentia non involvit necessariam existentiam.</p>
<p>PROPOSITIO I : Cogitatio attributum Dei est.</p>
<p>DEMONSTRATIO : Patet.</p>
<p>AXIOMA I : Omnia corpora vel moventur vel quiescunt.</p>
<p>AXIOMA II : Unumquodque corpus jam tardius jam celerius movetur.</p>
</body></html>
"""


# Arabic-numbered labels. `_LABEL_RE`'s number group is
# ``([IVXLC]+|\d+)?`` — it accepts either — and feeding the arabic
# branch to a Roman converter is what the module's own copy got wrong
# (#509): every digit is outside the Roman alphabet, so "14" read as 0.
_PART_ARABIC = """\
<html><body>
<p>DEFINITIO 3 : Per corpus intelligo modum.</p>
<p>PROPOSITIO 14 : Praeter Deum nulla dari potest substantia.</p>
<p>DEMONSTRATIO : Patet ex propositione praecedenti.</p>
</body></html>
"""


def test_arabic_numbered_labels_are_read_as_numbers(tmp_path: Path):
    # #509: the local `_roman_to_int` returned 0 for any arabic label,
    # so these became "E I, Def. 0" and "E I, P0".
    by = _by_section(_parse(tmp_path, "ethica_ll_1.html", _PART_ARABIC))
    assert "E I, Def. 3" in by, sorted(by)
    assert "E I, P14" in by, sorted(by)
    assert "E I, P14 Dem." in by, sorted(by)
    assert by["E I, P14"].text.startswith("Praeter Deum")


def test_part1_defs_then_axioms_inferred(tmp_path: Path):
    by = _by_section(_parse(tmp_path, "ethica_ll_1.html", _PART1))
    # Definitions, then the numbering reset flips to axioms.
    assert "E I, Def. 1" in by
    assert "E I, Def. 2" in by
    assert "E I, Ax. 1" in by
    assert "E I, Ax. 2" in by
    assert by["E I, Def. 1"].text.startswith("Per causam sui")
    assert by["E I, Ax. 1"].text.startswith("Omnia quae sunt")


def test_explicatio_anchored_to_definition_as_remark(tmp_path: Path):
    by = _by_section(_parse(tmp_path, "ethica_ll_1.html", _PART1))
    assert "E I, Def. 2 Expl." in by
    assert by["E I, Def. 2 Expl."].block_type == "remark"


def test_proposition_splits_into_apparatus_with_double_scholium(tmp_path: Path):
    by = _by_section(_parse(tmp_path, "ethica_ll_1.html", _PART1))
    assert "E I, P1" in by and by["E I, P1"].block_type is None
    assert "E I, P1 Dem." in by and by["E I, P1 Dem."].block_type is None
    # Double scholium → Schol. and Schol. 2, both typed remark.
    assert by["E I, P1 Schol."].block_type == "remark"
    assert by["E I, P1 Schol. 2"].block_type == "remark"
    assert "Prima ratio" in by["E I, P1 Schol."].text
    assert "Secunda ratio" in by["E I, P1 Schol. 2"].text


def test_site_chrome_stripped(tmp_path: Path):
    chunks = _parse(tmp_path, "ethica_ll_1.html", _PART1)
    assert all("Latin Library" not in c.text for c in chunks)


def test_part4_unclosed_p_does_not_duplicate(tmp_path: Path):
    # With unclosed <p>, a naive html.parser nests them and every chunk
    # balloons. lxml keeps them flat — assert no chunk is absurdly long.
    chunks = _parse(tmp_path, "ethica_ll_4.html", _PART4)
    assert all(len(c.text) < 400 for c in chunks)


def test_part4_proposition_with_fatio_not_swallowed_by_praefatio(tmp_path: Path):
    by = _by_section(_parse(tmp_path, "ethica_ll_4.html", _PART4))
    assert "E IV, Praef." in by
    # The proposition body contains "satisfactio" (substring "fatio") —
    # it must still be captured as a proposition, not appended to Praef.
    assert "E IV, P1" in by
    assert "satisfactio" in by["E IV, P1"].text
    assert "satisfactio" not in by["E IV, Praef."].text


def test_part4_singular_axioma_is_labelled_axiom(tmp_path: Path):
    by = _by_section(_parse(tmp_path, "ethica_ll_4.html", _PART4))
    assert "E IV, Ax. 1" in by
    assert by["E IV, Ax. 1"].text.startswith("Nulla res singularis")


def test_part2_digression_axioms_tagged_lem(tmp_path: Path):
    by = _by_section(_parse(tmp_path, "ethica_ll_2.html", _PART2))
    # Main axiom precedes the proposition → plain.
    assert "E II, Ax. 1" in by
    assert by["E II, Ax. 1"].text.startswith("Hominis essentia")
    # Digression axioms come after the proposition → tagged, no collision.
    assert "E II, Ax. 1 (Lem.)" in by
    assert "E II, Ax. 2 (Lem.)" in by
    assert by["E II, Ax. 1 (Lem.)"].text.startswith("Omnia corpora")


def test_no_duplicate_sections_or_ids(tmp_path: Path):
    chunks = (
        _parse(tmp_path, "ethica_ll_1.html", _PART1)
        + _parse(tmp_path, "ethica_ll_2.html", _PART2)
        + _parse(tmp_path, "ethica_ll_4.html", _PART4)
    )
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    # within a single part, section strings are unique
    p1 = _parse(tmp_path, "ethica_ll_1.html", _PART1)
    secs = Counter(c.section for c in p1)
    assert all(v == 1 for v in secs.values()), secs


def test_a_missing_lxml_builder_raises_instead_of_falling_back_silently(tmp_path, monkeypatch):
    """#497: the fallback caught bare `Exception` and switched to
    `html.parser`, which the file's own comment says yields 90 KB
    pseudo-paragraphs on Parts II-V because they never close their
    `<p>` tags. Measured on the real sources:

        ethica_ll_2  lxml max=3422   html.parser max= 90420
        ethica_ll_3  lxml max=6771   html.parser max=116783
        ethica_ll_4  lxml max=4312   html.parser max=118273

    `lxml` is declared only under the `hegel` extra, so an install that
    omits it took the lossy branch and said nothing. The module already
    raises `IngestDepsMissing` for a missing `beautifulsoup4` fifteen
    lines above; a dependency whose absence silently corrupts the output
    deserves at least the same.
    """

    import bs4

    from minerva.corpus.split_spinoza_ethica import split_spinoza_ethica
    from minerva.corpus_extract import IngestDepsMissing

    real = bs4.BeautifulSoup

    def no_lxml(markup, features=None, *args, **kwargs):
        if features == "lxml":
            raise bs4.FeatureNotFound("lxml not installed")
        return real(markup, features, *args, **kwargs)

    monkeypatch.setattr(bs4, "BeautifulSoup", no_lxml)

    src = tmp_path / "ethica_ll_2.html"
    src.write_text("<html><body><p>PROPOSITIO I<p>Demonstratio.</body></html>", encoding="latin-1")
    work = _work()

    with pytest.raises(IngestDepsMissing, match="lxml"):
        list(split_spinoza_ethica(src, work))
