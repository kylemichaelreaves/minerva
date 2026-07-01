"""Hermetic tests for the Aquinas splitter's disputatio sub-splitting
(2026-07 block-structure remediation, item 4).

Each ST article used to be ONE chunk with `[arg. 1]…[s. c.]…[co.]…
[ad 1]…` labels inlined (avg ~3.5k chars); the dialectic is now split
into separate citable chunks with scholarly locator suffixes. Fixtures
lock each behavior and each source quirk we hit:

* the canonical article shape (objections → sed contra → corpus →
  replies) with `', arg. N' / ', s. c.' / ', co.' / ', ad N'` labels
* `[ad arg.]` (one reply answering all objections) and numbered
  `[s. c. N]` variants
* articles genuinely missing a part (ST I q. 74 a. 3 has no `[co.]`) —
  tolerated, not an error
* articulus-unicus questions (I q. 71–72, II-II q. 48/80/128/143):
  the whole disputatio sits inside the question-prooemium block
  `[ST.p.q.0]`, so sub-parts must cite at the *question* level
  ('ST I, q. 71, co.'), with prooemium text keeping ', pr.'
* the corpusthomisticum.org page-footer chrome ("© 20xx Fundación
  Tomás de Aquino … OCLC nr. …") is stripped
* SCG chapters and prooemia without sub-markers stay single chunks
"""

from __future__ import annotations

from pathlib import Path

from minerva.corpus.split_aquinas import split_aquinas
from minerva.corpus_works import CorpusWork

_ST_WORK = CorpusWork(
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
)

_SCG_WORK = CorpusWork(
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
)


def _split(text: str, work: CorpusWork = _ST_WORK) -> list:
    return list(split_aquinas(text, work, Path(work.filenames[0])))


def test_article_splits_into_disputatio_parts() -> None:
    text = """[ST.1.2.3]

[arg. 1] Videtur quod Deus non sit. [arg. 2] Praeterea, quod potest
compleri per pauciora principia. [s. c.] Sed contra est quod dicitur
Exodi III. [co.] Respondeo dicendum quod Deum esse quinque viis
probari potest. [ad 1] Ad primum ergo dicendum. [ad 2] Ad secundum
dicendum.
"""
    chunks = _split(text)
    assert [c.section for c in chunks] == [
        "ST I, q. 2, a. 3, arg. 1",
        "ST I, q. 2, a. 3, arg. 2",
        "ST I, q. 2, a. 3, s. c.",
        "ST I, q. 2, a. 3, co.",
        "ST I, q. 2, a. 3, ad 1",
        "ST I, q. 2, a. 3, ad 2",
    ]
    co = chunks[3]
    assert co.text == "Respondeo dicendum quod Deum esse quinque viis probari potest."
    assert co.book == "ST I"
    # The dialectic is Aquinas's own voice — no block_type, no
    # attribution change.
    assert all(c.block_type is None for c in chunks)
    assert all(c.author == "Aquinas" for c in chunks)


def test_ad_arg_and_numbered_sed_contra_labels() -> None:
    text = """[ST.2.5.1]

[arg. 1] Videtur quod non. [s. c. 1] Sed contra primum. [s. c. 2]
Sed contra secundum. [co.] Respondeo. [ad arg.] Ad argumenta ergo
dicendum.
"""
    chunks = _split(text)
    assert [c.section for c in chunks] == [
        "ST I-II, q. 5, a. 1, arg. 1",
        "ST I-II, q. 5, a. 1, s. c. 1",
        "ST I-II, q. 5, a. 1, s. c. 2",
        "ST I-II, q. 5, a. 1, co.",
        "ST I-II, q. 5, a. 1, ad arg.",
    ]


def test_article_missing_corpus_is_tolerated() -> None:
    # ST I q. 74 a. 3 shape: replies follow the objections directly.
    text = """[ST.1.74.3]

[arg. 1] Videtur quod inconvenienter. [arg. 2] Praeterea. [ad 1]
Dicendum quod Moyses. [ad 2] Ad secundum.
"""
    chunks = _split(text)
    assert [c.section.rsplit(", ", 1)[1] for c in chunks] == [
        "arg. 1",
        "arg. 2",
        "ad 1",
        "ad 2",
    ]


def test_articulus_unicus_cites_at_question_level() -> None:
    # I q. 71 shape: the whole disputatio inside [ST.1.71.0], with the
    # question prooemium under an explicit [pr.] marker.
    text = """[ST.1.71.0]

[pr.] Deinde considerandum est de opere quintae diei. [arg. 1]
Videtur quod inconvenienter. [s. c.] Sed contra sufficit auctoritas
Scripturae. [co.] Respondeo dicendum quod. [ad 1] Ad primum ergo.
"""
    chunks = _split(text)
    assert [c.section for c in chunks] == [
        "ST I, q. 71, pr.",
        "ST I, q. 71, arg. 1",
        "ST I, q. 71, s. c.",
        "ST I, q. 71, co.",
        "ST I, q. 71, ad 1",
    ]


def test_prooemium_without_markers_stays_single_chunk() -> None:
    text = """[ST.1.2.0]

Quia igitur principalis intentio huius sacrae doctrinae est Dei
cognitionem tradere.

[ST.1.0.0]

Quia Catholicae veritatis doctor non solum provectos debet instruere.
"""
    chunks = _split(text)
    assert [c.section for c in chunks] == ["ST I, q. 2, pr.", "ST I, pr."]


def test_chrome_footer_is_stripped() -> None:
    text = """[ST.1.1.1]

[arg. 1] Videtur quod praeter philosophicas disciplinas. [co.]
Respondeo dicendum. © 2019 Fundación Tomás de Aquino quoad hanc
editionemIura omnia asservanturOCLC nr. 49644264 [ad 1] Ad primum.
"""
    chunks = _split(text)
    assert len(chunks) == 3
    assert "Fundación" not in " ".join(c.text for c in chunks)
    assert "OCLC" not in " ".join(c.text for c in chunks)
    assert chunks[1].text == "Respondeo dicendum."


def test_scg_chapters_are_not_sub_split() -> None:
    # SCG has no disputatio structure; [n. K] paragraph labels stay
    # inlined in a single chapter chunk.
    text = """[SCG.1.13]

[n. 1] Ostenso igitur quod non est vanum. [n. 2] Ad probandum autem
Deum esse.
"""
    chunks = _split(text, _SCG_WORK)
    assert len(chunks) == 1
    assert chunks[0].section == "SCG I, cap. 13"
    assert "[n. 1]" in chunks[0].text
