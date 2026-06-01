"""Chronological ordering for the Reader sidebar.

The Read tab lists every (author, work, lang) tuple in the corpus.
Alphabetical order puts Anaxagoras before Plato and Genesis between
Galatians and Habakkuk — confusing for a corpus organized around the
history of thought.

This module specifies the canonical chronological order so the
ordering can be enforced at one well-known place (the
``_handle_works_list`` handler) rather than re-derived in the
frontend.

``AUTHOR_ORDINAL`` is a hand-maintained table: lower integer = earlier
in history. Gaps in the integer sequence are intentional so future
additions can slot in without renumbering. Authors not present in
this table sort to the end via ``DEFAULT_AUTHOR_ORDINAL``.

Within an author, individual works are ordered by:

* ``BCV_BOOK_ORDINAL`` for biblical books (Genesis → Revelation) —
  see ``locations._BCV_BOOKS`` for the canonical sequence.
* The work title alphabetically for everyone else (a sane fallback;
  philosophical corpora rarely have a strong "canonical work order"
  beyond ordering by composition date, which we don't track per-work
  yet).

Within an author / work, languages are ordered Greek → Latin →
German → French → English by ``LANG_ORDINAL``. The original-language
edition typically sorts first, with translations following.
"""

from __future__ import annotations

# Lower = earlier. Spacing of 10 between entries leaves room to slot
# new authors without renumbering existing ones.
# BEGIN AUTHOR_ORDINAL
AUTHOR_ORDINAL: dict[str, int] = {
    # Vulgate) stay clustered at their own dates below.
    'Hebrew Bible': 50,
    'Homer': 100,
    # philosophers in the formal sense.
    'Theognis': 150,
    'Aesop': 170,
    'Thales': 200,
    'Anaximander': 210,
    'Anaximenes': 220,
    'Pythagoras': 230,
    'Xenophanes': 240,
    'Heraclitus': 250,
    'Parmenides': 260,
    'Zeno of Elea': 270,
    'Empedocles': 280,
    'Anaxagoras': 290,
    'Melissus': 300,
    'Diogenes of Apollonia': 310,
    # in scholarship is Sophocles → Euripides by reputation).
    'Aeschylus': 340,
    'Sophocles': 350,
    'Euripides': 360,
    'Plato': 400,
    'Aristotle': 410,
    'Lucretius': 420,
    'Cicero': 430,
    'Epictetus': 460,
    'Marcus Aurelius': 470,
    # succeed is at ordinal 50.
    'Septuagint': 500,
    'New Testament': 510,
    'Vulgate': 520,
    # quotations.
    'Origen': 580,
    'Augustine': 600,
    # will land between Quran and Aquinas at ordinals 660–680.
    'Quran': 650,
    'Aquinas': 700,
    # philosophers cite.
    'Luther Bibel 1545': 720,
    'Luther Bibel 1912': 730,
    'King James Bible': 740,
    'Sacy': 750,
    'Descartes': 800,
    'Hobbes': 810,
    'Pascal': 820,
    'Spinoza': 830,
    'Locke': 840,
    # Locke (1632-1704) and Hume (1711-1776) by birth year.
    'Boulainvilliers': 845,
    'Hume': 850,
    'Rousseau': 860,
    'Kant': 900,
    'Hegel': 910,
    # by publication year of the Essai.
    'Gobineau': 915,
    # the slave-morality genealogy in GM I.7-8.
    'Renan': 920,
    # the ≥5-unit gap policy after inserting Gobineau + Renan.
    'Marx': 925,
    'Nietzsche': 935,
}
# END AUTHOR_ORDINAL

DEFAULT_AUTHOR_ORDINAL = 9999

# Language sort: source language first, then conventional translations.
# Used to put a Greek edition before its German / English renderings.
LANG_ORDINAL: dict[str, int] = {
    "grc": 0,
    "lat": 1,
    "deu": 2,
    "fra": 3,
    "eng": 4,
}

DEFAULT_LANG_ORDINAL = 99


def author_sort_key(author: str) -> int:
    return AUTHOR_ORDINAL.get(author, DEFAULT_AUTHOR_ORDINAL)


def lang_sort_key(lang: str) -> int:
    return LANG_ORDINAL.get(lang, DEFAULT_LANG_ORDINAL)
