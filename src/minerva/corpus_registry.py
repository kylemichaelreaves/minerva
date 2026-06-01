"""Single source of truth for per-corpus metadata.

Drives chat auto-routing (``AUTHOR_KEYWORDS``), migration helpers
(``citation_system_for_corpus``, ``original_language_for_corpus``),
citation dominant glyphs, and CLI ``--corpus`` choices.
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class CorpusEntry:
    id: str
    original_lang: str
    citation_system: str
    dominant_code: str
    keywords: tuple[str, ...] = ()


# Keywords are whole-word tokens matched by ``agent.detect_corpus``.
# Deliberately omitted: "bible", "scripture", "testament" (ambiguous
# across biblical corpora), bare "hebrew" (ambiguous), "meditations"
# only routes to Marcus Aurelius when unqualified.
# BEGIN CORPORA
CORPORA: tuple[CorpusEntry, ...] = (
    # Keywords are whole-word tokens matched by ``agent.detect_corpus``.
    # Deliberately omitted: "bible", "scripture", "testament" (ambiguous
    # across biblical corpora), bare "hebrew" (ambiguous), "meditations"
    # only routes to Marcus Aurelius when unqualified.
    # BEGIN CORPORA
    CorpusEntry(
        'plato',
        'grc',
        'stephanus',
        'P',
        (
        'plato',
        'platonic',
    ),
    ),
    CorpusEntry(
        'aristotle',
        'grc',
        'bekker',
        'A',
        (
        'aristotle',
        'aristotelian',
    ),
    ),
    CorpusEntry(
        'hegel',
        'deu',
        'paragraph',
        'H',
        (
        'hegel',
        'hegelian',
    ),
    ),
    CorpusEntry(
        'kant',
        'deu',
        'paragraph',
        'K',
        (
        'kant',
        'kantian',
    ),
    ),
    CorpusEntry(
        'homer',
        'grc',
        'paragraph',
        'O',
        (
        'homer',
        'homeric',
    ),
    ),
    CorpusEntry(
        'aeschylus',
        'grc',
        'paragraph',
        'a',
        (
        'aeschylus',
        'aeschylean',
    ),
    ),
    # Lowercase initials for the tragedians — uppercase A/S/E are
    # already taken by Aristotle / Spinoza / Lucretius. The dominant
    # glyph still reads as the author's initial; lowercase signals
    # "verse drama" without colliding with the prose canon.
    CorpusEntry(
        'sophocles',
        'grc',
        'paragraph',
        's',
        (
        'sophocles',
        'sophoclean',
    ),
    ),
    CorpusEntry(
        'euripides',
        'grc',
        'paragraph',
        'e',
        (
        'euripides',
        'euripidean',
    ),
    ),
    CorpusEntry(
        'descartes',
        'lat',
        'paragraph',
        'D',
        (
        'descartes',
        'cartesian',
    ),
    ),
    CorpusEntry(
        'spinoza',
        'lat',
        'paragraph',
        'S',
        (
        'spinoza',
        'spinozist',
        'spinozistic',
    ),
    ),
    CorpusEntry(
        'hobbes',
        'lat',
        'paragraph',
        'B',
        (
        'hobbes',
        'hobbesian',
    ),
    ),
    CorpusEntry(
        'pascal',
        'fra',
        'paragraph',
        'F',
        (
        'pascal',
        'pascalian',
    ),
    ),
    CorpusEntry(
        'hume',
        'eng',
        'paragraph',
        'I',
        (
        'hume',
        'humean',
    ),
    ),
    CorpusEntry(
        'locke',
        'eng',
        'paragraph',
        'L',
        (
        'locke',
        'lockean',
    ),
    ),
    CorpusEntry(
        'rousseau',
        'fra',
        'paragraph',
        'R',
        (
        'rousseau',
        'rousseauist',
    ),
    ),
    CorpusEntry(
        'augustine',
        'lat',
        'augustine',
        'U',
        (
        'augustine',
        'augustinian',
    ),
    ),
    CorpusEntry(
        'aquinas',
        'lat',
        'aquinas',
        'T',
        (
        'aquinas',
        'thomist',
        'thomistic',
    ),
    ),
    CorpusEntry(
        'marx',
        'deu',
        'paragraph',
        'M',
        (
        'marx',
        'marxist',
        'marxian',
    ),
    ),
    CorpusEntry(
        'nietzsche',
        'deu',
        'paragraph',
        'N',
        (
        'nietzsche',
        'nietzschean',
    ),
    ),
    CorpusEntry(
        'cicero',
        'lat',
        'paragraph',
        'I',
        (
        'cicero',
        'ciceronian',
    ),
    ),
    CorpusEntry(
        'lucretius',
        'lat',
        'paragraph',
        'E',
        (
        'lucretius',
        'lucretian',
    ),
    ),
    CorpusEntry(
        'epictetus',
        'grc',
        'paragraph',
        'X',
        (
        'epictetus',
    ),
    ),
    CorpusEntry(
        'marcus_aurelius',
        'grc',
        'paragraph',
        'Y',
        (
        'marcus',
        'aurelius',
        'meditations',
    ),
    ),
    CorpusEntry(
        'septuagint',
        'grc',
        'bcv',
        'G',
        (
        'septuagint',
        'lxx',
    ),
    ),
    CorpusEntry(
        'new_testament',
        'grc',
        'bcv',
        'W',
        (
        'gospel',
        'gospels',
        'evangelist',
        'pauline',
    ),
    ),
    CorpusEntry(
        'vulgate',
        'lat',
        'bcv',
        'V',
        (
        'vulgate',
    ),
    ),
    CorpusEntry(
        'luther_1912',
        'deu',
        'bcv',
        'b',
        (
        'lutherbibel',
        'lutherbible',
    ),
    ),
    CorpusEntry(
        'luther_1545',
        'deu',
        'bcv',
        'c',
        (
        'luther1545',
        'lutherletztehand',
        'fruhneuhochdeutsch',
    ),
    ),
    CorpusEntry(
        'kjv',
        'eng',
        'bcv',
        'g',
        (
        'kjv',
        'authorized',
        'authorised',
        'kingjames',
    ),
    ),
    CorpusEntry(
        'sacy',
        'fra',
        'bcv',
        'h',
        (
        'sacy',
        'portroyal',
        'lemaistre',
    ),
    ),
    CorpusEntry(
        'presocratic',
        'grc',
        'diels_kranz',
        'Z',
        (
        'presocratic',
        'presocratics',
        'vorsokratiker',
        'diels',
        'heraclitus',
        'heraclitean',
        'parmenides',
        'eleatic',
        'empedocles',
        'empedoclean',
        'anaxagoras',
        'anaximander',
        'anaximenes',
        'xenophanes',
        'zeno',
        'melissus',
        'thales',
        'pythagoras',
        'pythagorean',
    ),
    ),
    CorpusEntry(
        'hebrew_mt',
        'heb',
        'bcv',
        'J',
        (
        'tanakh',
        'torah',
        'masoretic',
    ),
    ),
    CorpusEntry(
        'quran',
        'ara',
        'surah_ayah',
        'Q',
        (
        'quran',
        'koran',
        'surah',
        'surahs',
        'quranic',
        'koranic',
    ),
    ),
    # Theognis of Megara — aristocratic elegist; subject of
    # Nietzsche's 1867 dissertation. dominant_code "T" is unused.
    CorpusEntry(
        'theognis',
        'grc',
        'paragraph',
        'T',
        (
        'theognis',
        'theognidea',
        'theognidean',
    ),
    ),
    # Aesop — pre-philosophical fabulist; source of the "Hic Rhodus,
    # hic salta" / "Hier ist die Rose" Hegel/Marx reference. The
    # ingest covers Babrius (grc) and Phaedrus (lat) verse traditions;
    # original_lang="grc" reflects the Aesopic tradition's origin
    # while Phaedrus chunks remain lang-tagged "lat" at the chunk
    # level. dominant_code "Æ" matches the typographic convention.
    CorpusEntry(
        'aesop',
        'grc',
        'paragraph',
        'Æ',
        (
        'aesop',
        'aesopic',
        'aesopian',
        'babrius',
        'phaedrus',
        'fable',
        'fables',
    ),
    ),
    # Origen — *Contra Celsum* host-text for Celsus's lost *Alēthēs
    # Logos*. Celsus himself stays as an out-of-corpus reference
    # target (no CorpusEntry; just a reference_targets row created
    # via the origen_celsus rule in refs/rules/origen.py).
    CorpusEntry(
        'origen',
        'grc',
        'paragraph',
        'Ω',
        (
        'origen',
        'origenes',
        'origenist',
        'origenistic',
        'contra celsum',
    ),
    ),
    # source for Nietzsche's Frankish-conquest / blond-beast material
    # (Genealogie I.5/I.11). Core ingest covers the *Histoire de
    # l'ancien gouvernement de la France*, *Essai sur la noblesse*,
    # *Lettres sur les anciens parlemens* (Fr + the rare 1739 English
    # Dryden translation). Boulainvilliers is in-corpus; Tacitus /
    # Caesar / Gregory-of-Tours (his historical sources) resolve
    # via out-of-corpus reference_targets rows for now.
    CorpusEntry(
        'boulainvilliers',
        'fra',
        'paragraph',
        'B',
        (
        'boulainvilliers',
        'boulainviller',
        'boulainvillier',
        'henri boulainvilliers',
    ),
    ),
    # Arthur de Gobineau (1816-1882) — *Essai sur l'inégalité des
    # races humaines* (1853-55). The racial-determinism reformulation
    # of Boulainvilliers's Frankish thesis that Nietzsche absorbs.
    CorpusEntry(
        'gobineau',
        'fra',
        'paragraph',
        'G',
        (
        'gobineau',
        'comte de gobineau',
        "essai sur l'inégalité",
    ),
    ),
    # Ernest Renan (1823-1892) — *Vie de Jésus* (1863), *L'Antéchrist*
    # (1877), *Histoire du peuple d'Israël* (1887-93, 5 vols). Direct
    # target of Nietzsche's *Der Antichrist*; the priestly-class
    # material in the Histoire is the source for GM I.7-8 slave-
    # morality genealogy.
    CorpusEntry(
        'renan',
        'fra',
        'paragraph',
        'R',
        (
        'renan',
        'ernest renan',
        'vie de jésus',
        "l'antéchrist",
        'antéchrist',
        "histoire du peuple d'israël",
    ),
    ),
)
# END CORPORA

_BY_ID: dict[str, CorpusEntry] = {e.id: e for e in CORPORA}


def corpus_ids() -> tuple[str, ...]:
    return tuple(e.id for e in CORPORA)


def entry_for(corpus: str) -> CorpusEntry | None:
    return _BY_ID.get(corpus)


def citation_system_for_corpus(corpus: str) -> str:
    e = _BY_ID.get(corpus)
    return e.citation_system if e else "paragraph"


def original_language_for_corpus(corpus: str) -> str:
    e = _BY_ID.get(corpus)
    return e.original_lang if e else "eng"


def dominant_for_corpus(corpus: str) -> str | None:
    e = _BY_ID.get(corpus)
    return e.dominant_code if e else None


def build_author_keywords() -> dict[str, str]:
    out: dict[str, str] = {}
    for e in CORPORA:
        for kw in e.keywords:
            out[kw] = e.id
    return out


AUTHOR_KEYWORDS: dict[str, str] = build_author_keywords()

CORPUS_TO_DOMINANT: dict[str, str] = {e.id: e.dominant_code for e in CORPORA}


def validate_keywords() -> None:
    """Raise if two corpora claim the same keyword."""

    seen: dict[str, str] = {}
    for kw, corpus in AUTHOR_KEYWORDS.items():
        if kw in seen and seen[kw] != corpus:
            raise ValueError(f"keyword {kw!r} maps to both {seen[kw]!r} and {corpus!r}")
        seen[kw] = corpus


validate_keywords()
