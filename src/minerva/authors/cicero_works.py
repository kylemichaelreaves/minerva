"""Per-work configuration for Cicero ingest.

23 CorpusWork entries: 16 Latin works (from la.wikisource.org)
plus 7 English PG volumes (mostly Yonge / Miller / Shuckburgh /
Jones / Featherstonhaugh). Several PG volumes bundle multiple
works (Yonge's Academica + De Finibus + Tusculans in one; Miller
gives De Officiis bilingually). We treat each PG volume as a single
CorpusWork rather than splitting them at ingest time — the chunk
title metadata still tracks which sub-work each passage is from
via the section locator, and the simpler ingestion is worth the
slight composite-title cosmetic loss.

Latin coverage: all 16 selected philosophical + rhetorical works.
English coverage: 9 of 16 works (the others are Latin-only in this
round because PG doesn't host a PD English translation):
  * have English: De Officiis, De Re Publica, De Finibus, Tusculans,
    De Amicitia, De Senectute, Academica, Brutus, Orator
  * Latin-only: De Legibus, De Natura Deorum, De Divinatione,
    De Fato, De Oratore, Topica, De Inventione

These 7 Latin-only works will still be searchable via German/Latin
embedding similarity and the Aquinas/Augustine/Hobbes/Locke/Hume
rule mentions of Cicero will resolve to the Latin chunks
appropriately.
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work

_LATIN: tuple[CorpusWork, ...] = (
    CorpusWork(
        code="de_inventione_lat",
        title="De Inventione",
        translator="(Original)",
        edition_year="88 BCE",
        filenames=("de_inventione_lat.txt",),
        fmt="txt",
        locator="chapter",
        lang="lat",
        corpus="cicero",
        author="Cicero",
    ),
    CorpusWork(
        code="de_oratore_lat",
        title="De Oratore",
        translator="(Original)",
        edition_year="55 BCE",
        filenames=("de_oratore_lat.txt",),
        fmt="txt",
        locator="chapter",
        lang="lat",
        corpus="cicero",
        author="Cicero",
    ),
    CorpusWork(
        code="de_re_publica_lat",
        title="De Re Publica",
        translator="(Original)",
        edition_year="51 BCE",
        filenames=("de_re_publica_lat.txt",),
        fmt="txt",
        locator="chapter",
        lang="lat",
        corpus="cicero",
        author="Cicero",
    ),
    CorpusWork(
        code="de_legibus_lat",
        title="De Legibus",
        translator="(Original)",
        edition_year="52 BCE",
        filenames=("de_legibus_lat.txt",),
        fmt="txt",
        locator="chapter",
        lang="lat",
        corpus="cicero",
        author="Cicero",
    ),
    CorpusWork(
        code="brutus_lat",
        title="Brutus",
        translator="(Original)",
        edition_year="46 BCE",
        filenames=("brutus_lat.txt",),
        fmt="txt",
        locator="chapter",
        lang="lat",
        corpus="cicero",
        author="Cicero",
    ),
    CorpusWork(
        code="orator_lat",
        title="Orator",
        translator="(Original)",
        edition_year="46 BCE",
        filenames=("orator_lat.txt",),
        fmt="txt",
        locator="chapter",
        lang="lat",
        corpus="cicero",
        author="Cicero",
    ),
    # Academica Latin omitted — fragmentary in manuscript tradition;
    # la.wikisource has no transcription. English Academica still
    # ships via PG 14970 (bilingual; we use the English half).
    CorpusWork(
        code="de_finibus_lat",
        title="De Finibus Bonorum et Malorum",
        translator="(Original)",
        edition_year="45 BCE",
        filenames=("de_finibus_lat.txt",),
        fmt="txt",
        locator="chapter",
        lang="lat",
        corpus="cicero",
        author="Cicero",
    ),
    CorpusWork(
        code="de_natura_deorum_lat",
        title="De Natura Deorum",
        translator="(Original)",
        edition_year="45 BCE",
        filenames=("de_natura_deorum_lat.txt",),
        fmt="txt",
        locator="chapter",
        lang="lat",
        corpus="cicero",
        author="Cicero",
    ),
    CorpusWork(
        code="tusculans_lat",
        title="Tusculanae Disputationes",
        translator="(Original)",
        edition_year="45 BCE",
        filenames=("tusculans_lat.txt",),
        fmt="txt",
        locator="chapter",
        lang="lat",
        corpus="cicero",
        author="Cicero",
    ),
    CorpusWork(
        code="de_officiis_lat",
        title="De Officiis",
        translator="(Original)",
        edition_year="44 BCE",
        filenames=("de_officiis_lat.txt",),
        fmt="txt",
        locator="chapter",
        lang="lat",
        corpus="cicero",
        author="Cicero",
    ),
    CorpusWork(
        code="de_amicitia_lat",
        title="Laelius de Amicitia",
        translator="(Original)",
        edition_year="44 BCE",
        filenames=("de_amicitia_lat.txt",),
        fmt="txt",
        locator="chapter",
        lang="lat",
        corpus="cicero",
        author="Cicero",
    ),
    CorpusWork(
        code="de_senectute_lat",
        title="Cato Maior de Senectute",
        translator="(Original)",
        edition_year="44 BCE",
        filenames=("de_senectute_lat.txt",),
        fmt="txt",
        locator="chapter",
        lang="lat",
        corpus="cicero",
        author="Cicero",
    ),
    CorpusWork(
        code="de_divinatione_lat",
        title="De Divinatione",
        translator="(Original)",
        edition_year="44 BCE",
        filenames=("de_divinatione_lat.txt",),
        fmt="txt",
        locator="chapter",
        lang="lat",
        corpus="cicero",
        author="Cicero",
    ),
    CorpusWork(
        code="de_fato_lat",
        title="De Fato",
        translator="(Original)",
        edition_year="44 BCE",
        filenames=("de_fato_lat.txt",),
        fmt="txt",
        locator="chapter",
        lang="lat",
        corpus="cicero",
        author="Cicero",
    ),
    CorpusWork(
        code="topica_lat",
        title="Topica",
        translator="(Original)",
        edition_year="44 BCE",
        filenames=("topica_lat.txt",),
        fmt="txt",
        locator="chapter",
        lang="lat",
        corpus="cicero",
        author="Cicero",
    ),
)

_ENGLISH: tuple[CorpusWork, ...] = (
    # PG 47001 — Walter Miller, Loeb-style bilingual (1913). We use
    # the English half; the Latin we already have via la.wikisource.
    CorpusWork(
        code="de_officiis_en",
        title="De Officiis",
        translator="Walter Miller",
        edition_year="1913",
        filenames=("de_officiis_en.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="cicero",
        author="Cicero",
    ),
    # PG 54161 — Featherstonhaugh.
    CorpusWork(
        code="de_re_publica_en",
        title="De Re Publica",
        translator="George William Featherstonhaugh",
        edition_year="1829",
        filenames=("de_re_publica_en.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="cicero",
        author="Cicero",
    ),
    # PG 14988 — Yonge, Tusculans standalone.
    CorpusWork(
        code="tusculans_en",
        title="Tusculan Disputations",
        translator="Charles Duke Yonge",
        edition_year="1877",
        filenames=("tusculans_en.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="cicero",
        author="Cicero",
    ),
    # PG 29247 — Yonge combined: Academic Questions + De Finibus +
    # Tusculans + Sketch of Greek Philosophers. Treated as one
    # CorpusWork; Tusculans is dup-ingested via PG 14988 above and
    # this composite (acceptable redundancy — chunks dedupe by
    # text hash at the chunk_id level).
    CorpusWork(
        code="academic_finibus_tusculans_en",
        title="Academic Questions, De Finibus, Tusculans (Yonge)",
        translator="Charles Duke Yonge",
        edition_year="1877",
        filenames=("academic_finibus_tusculans_en.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="cicero",
        author="Cicero",
    ),
    # PG 2808 — Shuckburgh, Treatises on Friendship and Old Age
    # (De Amicitia + De Senectute).
    CorpusWork(
        code="amicitia_senectute_en",
        title="Treatises on Friendship and Old Age",
        translator="Evelyn S. Shuckburgh",
        edition_year="1909",
        filenames=("amicitia_senectute_en.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="cicero",
        author="Cicero",
    ),
    # PG 9776 — E. Jones, Brutus + Orator.
    CorpusWork(
        code="brutus_orator_en",
        title="Brutus and Orator",
        translator="E. Jones",
        edition_year="1776",
        filenames=("brutus_orator_en.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="cicero",
        author="Cicero",
    ),
    # PG 14970 — Academica bilingual English+Latin. We use English
    # half via this entry; Latin is the la.wikisource version above.
    CorpusWork(
        code="academica_en",
        title="Academica",
        translator="(uncredited)",
        edition_year="1880",
        filenames=("academica_en.txt",),
        fmt="txt",
        locator="chapter",
        lang="eng",
        corpus="cicero",
        author="Cicero",
    ),
)

WORKS: tuple[CorpusWork, ...] = _LATIN + _ENGLISH

find_work = make_find_work(WORKS)
