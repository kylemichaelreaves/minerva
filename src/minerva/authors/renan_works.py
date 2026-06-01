"""Per-work configuration for Ernest Renan ingest.

Seven CorpusWork entries spanning the two work-clusters Nietzsche
engages most directly:

* *Vie de Jésus* (1863) — vol 1 of *Histoire des origines du
  christianisme*; the book that made Renan a household name and
  scandalised the Catholic establishment by treating Jesus as a
  historical figure. Nietzsche cites it in *Der Antichrist* and GM.
* *L'Antéchrist* (1877) — vol 4 of *Origines*; Nietzsche's *Der
  Antichrist* is in part a polemical response. The shared title is
  not a coincidence.
* *Histoire du peuple d'Israël* (1887-1893, 5 vols) — Renan's late
  great work. Vol 1 covers patriarchal origins, vol 2 the monarchy,
  vol 3 the kingdoms, vol 4 the prophets, vol 5 the priestly /
  postexilic period. The priestly-class material in vols 4-5 is
  the proximate source for the slave-morality genealogy in GM I.7-8
  and *Der Antichrist*'s critique of Judaism-as-priest-religion.

Citation system: ``paragraph``. The standard scholarly citation for
the Origines is volume + chapter (``L'Antéchrist, ch. 7``); for the
Histoire du peuple d'Israël it's the same shape with volume = book
of the multi-vol set.

See ``add-gobineau-renan-plan`` memory for source manifest and the
bidirectional refs audit (Nietzsche → Renan rule in
``refs/rules/nietzsche.py``).
"""

from __future__ import annotations

from ..corpus_works import CorpusWork, make_find_work


def _renan_work(code: str, title: str, year: str, filename: str) -> CorpusWork:
    return CorpusWork(
        code=code,
        title=title,
        translator="(Original)",
        edition_year=year,
        filenames=(filename,),
        fmt="txt",
        locator="chapter",
        lang="fra",
        corpus="renan",
        author="Renan",
        citation_system="paragraph",
    )


WORKS: tuple[CorpusWork, ...] = (
    _renan_work(
        "vie_de_jesus_fra",
        "Vie de Jésus",
        "1863",
        "vie_de_jesus_fra.txt",
    ),
    _renan_work(
        "antechrist_fra",
        "L'Antéchrist",
        "1877",
        "antechrist_fra.txt",
    ),
    # Histoire du peuple d'Israël — 5-volume set. Each volume is a
    # separate CorpusWork so chapter chunks have a stable work
    # identity; volumes ran 1887, 1889, 1889, 1889, 1893.
    _renan_work(
        "peuple_israel_vol1_fra",
        "Histoire du peuple d'Israël, vol. 1",
        "1887",
        "peuple_israel_vol1_fra.txt",
    ),
    _renan_work(
        "peuple_israel_vol2_fra",
        "Histoire du peuple d'Israël, vol. 2",
        "1889",
        "peuple_israel_vol2_fra.txt",
    ),
    _renan_work(
        "peuple_israel_vol3_fra",
        "Histoire du peuple d'Israël, vol. 3",
        "1889",
        "peuple_israel_vol3_fra.txt",
    ),
    _renan_work(
        "peuple_israel_vol4_fra",
        "Histoire du peuple d'Israël, vol. 4",
        "1889",
        "peuple_israel_vol4_fra.txt",
    ),
    _renan_work(
        "peuple_israel_vol5_fra",
        "Histoire du peuple d'Israël, vol. 5",
        "1893",
        "peuple_israel_vol5_fra.txt",
    ),
)


find_work = make_find_work(WORKS)
