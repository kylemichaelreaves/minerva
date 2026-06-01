"""Per-work configuration for Aquinas ingest.

Six Latin works land from `perseus/download_aquinas.py`, all sourced
from corpusthomisticum.org (Enrique Alarcón's Leonine-based scholarly
edition):

  • Summa Theologiae (4 Pars: I, I-II, II-II, III). Canonical citation
    `ST <Pars>, q. <N>, a. <M>` (e.g. `ST I, q. 2, a. 3`). One chunk
    per article — the article body inlines all sub-sections
    (`[arg. 1]…`, `[s. c.]…`, `[co.]…`, `[ad 1]…`) so the chunk reads
    like the original. Question prooemia (article = 0) become their
    own chunk labelled `ST <Pars>, q. <N>, pr.`. The Supplementum is
    NOT included — Corpus Thomisticum carries only authentic Thomas,
    and the Supplementum is a posthumous compilation.
  • Summa contra Gentiles (4 Libri). Canonical citation
    `SCG <Liber>, cap. <N>`. One chunk per chapter; the n.-numbered
    paragraphs inside each chapter are inlined as `[n. K]` labels.
  • Four Aristotle commentaries — Sententia libri Ethicorum (Nicomachean
    Ethics, 10 books), Sententia libri Metaphysicae (12 books + prooemium),
    In libros Physicorum (8 books), Sentencia libri De anima (3 books).
    Canonical citation `Sent. <work>, lib. <L>, lect. <M>`; one chunk
    per lectio, with `[n. K]` labels inlined for sub-paragraphs.

All six ingest via the `aquinas` locator (see `corpus/split_aquinas.py`),
which consumes `[ST.<p>.<q>.<a>]`, `[SCG.<lib>.<cap>]`, and
`[SENT_<W>.<lib>.<lect>]` marker shapes (W ∈ {ETH, MET, PHY, AN}).

NOT in this pass: the opuscula (De ente et essentia, De principiis
naturae, Compendium theologiae, De unitate intellectus, …) and the
remaining Aristotle commentaries whose source pages have continuations
by other authors (Politicorum — Petrus de Alvernia; Peri Hermeneias —
Cajetan) or thinner coverage (De caelo, De gen. et corruptione, De
sensu, Posterior Analytics). Add by extending this WORKS tuple plus
the marker regex in `split_aquinas.py`.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

WORKS: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="summa_theologiae",
        title="Summa Theologiae",
        translator="(Original)",
        edition_year="1265-1273",
        filenames=("summa_theologiae.txt",),
        fmt="txt",
        locator="aquinas",
        lang="lat",
        corpus="aquinas",
        author="Aquinas",
        citation_system="aquinas",
    ),
    CorpusWork(
        code="contra_gentiles",
        title="Summa contra Gentiles",
        translator="(Original)",
        edition_year="1259-1265",
        filenames=("contra_gentiles.txt",),
        fmt="txt",
        locator="aquinas",
        lang="lat",
        corpus="aquinas",
        author="Aquinas",
        citation_system="aquinas",
    ),
    CorpusWork(
        code="sententia_ethicorum",
        title="Sententia libri Ethicorum",
        translator="(Original)",
        edition_year="1271-1272",
        filenames=("sententia_ethicorum.txt",),
        fmt="txt",
        locator="aquinas",
        lang="lat",
        corpus="aquinas",
        author="Aquinas",
        citation_system="aquinas",
    ),
    CorpusWork(
        code="sententia_metaphysicae",
        title="Sententia libri Metaphysicae",
        translator="(Original)",
        edition_year="1270-1272",
        filenames=("sententia_metaphysicae.txt",),
        fmt="txt",
        locator="aquinas",
        lang="lat",
        corpus="aquinas",
        author="Aquinas",
        citation_system="aquinas",
    ),
    CorpusWork(
        code="in_physicorum",
        title="In libros Physicorum",
        translator="(Original)",
        edition_year="1268-1269",
        filenames=("in_physicorum.txt",),
        fmt="txt",
        locator="aquinas",
        lang="lat",
        corpus="aquinas",
        author="Aquinas",
        citation_system="aquinas",
    ),
    CorpusWork(
        code="sentencia_de_anima",
        title="Sentencia libri De anima",
        translator="(Original)",
        edition_year="1267-1268",
        filenames=("sentencia_de_anima.txt",),
        fmt="txt",
        locator="aquinas",
        lang="lat",
        corpus="aquinas",
        author="Aquinas",
        citation_system="aquinas",
    ),
)


find_work = make_find_work(WORKS)
