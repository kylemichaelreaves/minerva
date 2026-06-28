"""Per-work configuration for Spinoza ingest.

Four Latin works land from the `perseus/download_spinoza*.py`
downloaders:

  • Ethica (5 Pars; geometric structure with Defs / Axs / Posts /
    Props + Appendix). Posthumously published 1677. Re-sourced from
    thelatinlibrary.com (five per-Part HTML files, ``ethica_ll_<N>.html``)
    whose inline PROPOSITIO / DEMONSTRATIO / SCHOLIUM / COROLLARIUM labels
    let ``split_spinoza_ethica`` split each proposition into its apparatus
    and type the Scholia as ``block_type='remark'`` — unlike the old flat
    ``ethica.txt``, which fused statement + demonstration + scholium into
    one chunk per proposition.
  • Tractatus de Intellectus Emendatione (TIE) — unfinished;
    posthumous 1677. ~110 numbered paragraphs.
  • Tractatus Politicus (TP) — unfinished; posthumous 1677.
    11 Caputs with Roman-numeral-numbered articles.
  • Tractatus Theologico-Politicus (TTP) — anonymously published 1670.
    Praefatio + 20 Caputs; the most biblically-engaged work in
    Spinoza's canon (~30% biblical exegesis). Numbering is
    paragraph-index-within-chapter, not Bruder/Gebhardt (see
    perseus/download_spinoza_ttp.py for the rationale).

TIE / TP / TTP ingest via the `spinoza` locator (see
`corpus/split_spinoza.py`), which consumes the
`[TIE.<nnn>]` / `[TP.<c>.<nnn>]` / `[TTP.<c>.<nnn>]` marker format the
downloaders emit. The Ethica uses its own `spinoza_ethica` locator
(see `corpus/split_spinoza_ethica.py`).

The Epistolae and Korte Verhandeling are still NOT in this pass.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="ethica",
        title="Ethica",
        translator="(Original)",
        edition_year="1677",
        filenames=(
            "ethica_ll_1.html",
            "ethica_ll_2.html",
            "ethica_ll_3.html",
            "ethica_ll_4.html",
            "ethica_ll_5.html",
        ),
        fmt="html",
        locator="spinoza_ethica",
        lang="lat",
        corpus="spinoza",
        author="Spinoza",
    ),
    CorpusWork(
        code="tie",
        title="Tractatus de Intellectus Emendatione",
        translator="(Original)",
        edition_year="1677",
        filenames=("tie.txt",),
        fmt="txt",
        locator="spinoza",
        lang="lat",
        corpus="spinoza",
        author="Spinoza",
    ),
    CorpusWork(
        code="tp",
        title="Tractatus Politicus",
        translator="(Original)",
        edition_year="1677",
        filenames=("tp.txt",),
        fmt="txt",
        locator="spinoza",
        lang="lat",
        corpus="spinoza",
        author="Spinoza",
    ),
    CorpusWork(
        code="ttp",
        title="Tractatus Theologico-Politicus",
        translator="(Original)",
        edition_year="1670",
        filenames=("ttp.txt",),
        fmt="txt",
        locator="spinoza",
        lang="lat",
        corpus="spinoza",
        author="Spinoza",
    ),
)


find_work = make_find_work(WORKS)
