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
    # The `works.author` values this corpus is made of. Empty means the
    # corpus id *is* the author, lowercased — true for the 33
    # single-author corpora. The other seven need it spelled out: the
    # id is a slug (`marcus_aurelius`, `kjv`) or covers several authors
    # (`presocratic`), and retrieval filters on `LOWER(works.author)`.
    authors: tuple[str, ...] = ()


# Keywords are whole-word tokens matched by ``agent.detect_corpus``.
# Deliberately omitted: "bible", "scripture", "testament" (ambiguous
# across biblical corpora), bare "hebrew" (ambiguous), "meditations"
# only routes to Marcus Aurelius when unqualified.
# BEGIN CORPORA
CORPORA: tuple[CorpusEntry, ...] = (
    # Keywords are whole-word tokens matched by ``agent.detect_corpus``.
    # Include the author's name in every language a reader is likely to ask
    # in, plus the German genitive: "Plato's" tokenizes to {plato, s} and
    # matches, but "Platons" is one token and needs its own entry (#169).
    # Deliberately omitted: "bible", "scripture", "testament" (ambiguous
    # across biblical corpora), bare "hebrew" (ambiguous), "meditations"
    # only routes to Marcus Aurelius when unqualified.
    CorpusEntry(
        'plato',
        'grc',
        'stephanus',
        'P',
        (
        'plato',
        'platonic',
        'platon',
        'platons',
        'platos',
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
        'aristoteles',
        'aristote',
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
        'hegels',
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
        'kants',
    ),
    ),
    # Friedrich Schiller (1759-1805) — aesthetic-philosophy essays (Über die
    # ästhetische Erziehung des Menschen, 1795, + companions). dominant_code lowercase
    # 'l' (Schi-l-ler) — uppercase L is Locke, S/s are Spinoza/Sophocles.
    CorpusEntry(
        'schiller',
        'deu',
        'paragraph',
        'l',
        (
        'schiller',
        'schillerian',
        'schillers',
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
        'homers',
        'homeros',
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
        'aischylos',
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
        'sophokles',
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
        'cartesius',
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
        'spinozas',
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
        'pascals',
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
        'humes',
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
        'lockes',
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
        'rousseaus',
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
        'augustinus',
        'augustin',
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
        'aquin',
        'aquino',
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
        'nietzsches',
    ),
    ),
    # 'C' — Cicero's natural initial. (Hume claimed 'I' first; the
    # two collided on 'I' until the dominant-code uniqueness check landed.)
    CorpusEntry(
        'cicero',
        'lat',
        'paragraph',
        'C',
        (
        'cicero',
        'ciceronian',
        'ciceros',
        'cicéron',
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
        'lukrez',
        'lucrèce',
    ),
    ),
    CorpusEntry(
        'epictetus',
        'grc',
        'paragraph',
        'X',
        (
        'epictetus',
        'epiktet',
        'epiktets',
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
        'aurel',
        'aurels',
    ),
        (
        'Marcus Aurelius',
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
        'septuaginta',
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
        (
        'New Testament',
    ),
    ),
    CorpusEntry(
        'vulgate',
        'lat',
        'bcv',
        'V',
        (
        'vulgate',
        'vulgata',
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
        (
        'Luther Bibel 1912',
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
        (
        'Luther Bibel 1545',
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
        (
        'King James Bible',
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
        (
        'Anaxagoras',
        'Anaximenes',
        'Diogenes of Apollonia',
        'Empedocles',
        'Heraclitus',
        'Melissus',
        'Parmenides',
        'Xenophanes',
        'Zeno of Elea',
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
        (
        'Hebrew Bible',
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
    # Nietzsche's 1867 dissertation. Lowercase 't' (rendered 'τ' in the
    # UI) follows the tragedians' lowercase-Greek-verse convention;
    # uppercase 'T' belongs to Aquinas.
    CorpusEntry(
        'theognis',
        'grc',
        'paragraph',
        't',
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
        'origène',
    ),
    ),
    # source for Nietzsche's Frankish-conquest / blond-beast material
    # (Genealogie I.5/I.11). Core ingest covers the *Histoire de
    # l'ancien gouvernement de la France*, *Essai sur la noblesse*,
    # *Lettres sur les anciens parlemens* (Fr + the rare 1739 English
    # Dryden translation). Boulainvilliers is in-corpus; Tacitus /
    # Caesar / Gregory-of-Tours (his historical sources) resolve
    # via out-of-corpus reference_targets rows for now. dominant_code
    # 'v' (Boulain-Villiers) — 'B' belongs to Hobbes, lowercase 'b'
    # to the Luther 1912 Bible.
    CorpusEntry(
        'boulainvilliers',
        'fra',
        'paragraph',
        'v',
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
    # dominant_code 'o' (gObineau) — 'G' belongs to the Septuagint,
    # lowercase 'g' to the KJV.
    CorpusEntry(
        'gobineau',
        'fra',
        'paragraph',
        'o',
        (
        'gobineau',
        'comte de gobineau',
        "essai sur l'inégalité",
        'gobineaus',
    ),
    ),
    # Ernest Renan (1823-1892) — *Vie de Jésus* (1863), *L'Antéchrist*
    # (1877), *Histoire du peuple d'Israël* (1887-93, 5 vols). Direct
    # target of Nietzsche's *Der Antichrist*; the priestly-class
    # material in the Histoire is the source for GM I.7-8 slave-
    # morality genealogy. dominant_code lowercase 'r' — uppercase
    # 'R' belongs to Rousseau.
    CorpusEntry(
        'renan',
        'fra',
        'paragraph',
        'r',
        (
        'renan',
        'ernest renan',
        'vie de jésus',
        "l'antéchrist",
        'antéchrist',
        "histoire du peuple d'israël",
        'renans',
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


def corpus_authors(corpus: str | None) -> tuple[str, ...]:
    """The lowercased ``works.author`` values that make up *corpus*.

    Retrieval filters on ``LOWER(works.author)`` (that is what the
    ``chunks_full.corpus`` column is), while every other layer — CLI
    ``--corpus``, ``detect_corpus``, the manifest — speaks in corpus
    ids. For most corpora those coincide. For the seven where they do
    not, filtering on the id matched nothing at all: naming Marcus
    Aurelius or the Torah in chat scoped retrieval to zero chunks and
    the agent abstained (#174).

    Returns ``()`` for ``None``/``"any"``, i.e. no filtering.
    """

    if corpus in {None, "any"}:
        return ()
    e = _BY_ID.get(corpus)
    if e is None:
        # Unknown id — treat it as an author name, which is what a
        # caller passing a raw `works.author` value means.
        return (corpus.lower(),)
    return tuple(a.lower() for a in e.authors) or (e.id,)


def corpus_for_author(author: str | None) -> str | None:
    """The corpus id a ``works.author`` value belongs to, or ``None``.

    The inverse of :func:`corpus_authors`. Needed by the work-title
    fallback in ``agent.detect_corpus``: resolving a title gives a
    ``works`` row, and a ``works.author`` is not a corpus id for the
    seven corpora whose id is a slug or covers several authors (#174).
    Comparison is on the lowercased author name, which is the form
    ``corpus_authors`` returns and ``chunks_full.corpus`` stores.
    """

    if not author:
        return None
    return _CORPUS_BY_AUTHOR.get(author.strip().lower())


def build_corpus_by_author() -> dict[str, str]:
    out: dict[str, str] = {}
    for e in CORPORA:
        for author in e.authors or (e.id,):
            out[author.lower()] = e.id
    return out


def build_author_keywords() -> dict[str, str]:
    out: dict[str, str] = {}
    for e in CORPORA:
        for kw in e.keywords:
            out[kw] = e.id
    return out


AUTHOR_KEYWORDS: dict[str, str] = build_author_keywords()

_CORPUS_BY_AUTHOR: dict[str, str] = build_corpus_by_author()

CORPUS_TO_DOMINANT: dict[str, str] = {e.id: e.dominant_code for e in CORPORA}


def validate_keywords() -> None:
    """Raise if two corpora claim the same keyword.

    Must iterate ``CORPORA`` — ``AUTHOR_KEYWORDS`` has already collapsed
    duplicates by dict overwrite, so checking it can never find one.
    """

    seen: dict[str, str] = {}
    for e in CORPORA:
        for kw in e.keywords:
            if kw in seen and seen[kw] != e.id:
                raise ValueError(f"keyword {kw!r} maps to both {seen[kw]!r} and {e.id!r}")
            seen[kw] = e.id


def validate_dominant_codes() -> None:
    """Raise if two corpora share a dominant glyph — the glyph renders
    in the citation gutter, so a collision makes it ambiguous."""

    seen: dict[str, str] = {}
    for e in CORPORA:
        if e.dominant_code in seen:
            raise ValueError(
                f"dominant_code {e.dominant_code!r} used by both "
                f"{seen[e.dominant_code]!r} and {e.id!r}"
            )
        seen[e.dominant_code] = e.id


validate_keywords()
validate_dominant_codes()
