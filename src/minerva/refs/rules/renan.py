"""Rules that fire on Renan chunks.

Renan's corpus (Vie de Jésus, L'Antéchrist, Histoire du peuple
d'Israël) is source-critical history — densely referenced. Counts
below are LIKE-matches over the ingested chunks (2026-07 audit):

* **Scripture** — ~1,265 chunks carry cite-syntax references in the
  19th-c French convention ("Matth., xxvi, 39" / "Luc, xxiii, 34":
  comma after the book, chapter in lowercase Roman). The dedicated
  ``ScriptureCiteRuleFrRoman`` handles that shape; the plain FR rule
  is included too for the Arabic-numeral cites of the Psalms etc.
* **Josephus (200)** and **Philo (133)** — his two constant ancient
  sources for Second-Temple history. Out-of-corpus targets: the rows
  land in ``reference_targets`` for the ReferenceCard, not chunks.
* **Origen (29)** / **Celsus (9)** — the Contra Celsum pair; both
  route to the in-corpus Origen host text.
* Classical mentions: Plato (24), Seneca (23, out-of-corpus),
  Cicero (15), Marcus Aurelius (11 — the subject of his last
  Origines volume), Aristotle (7), Augustine (7).
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule
from .scripture_cite import ScriptureCiteRuleFr, ScriptureCiteRuleFrRoman

RULES = (
    # ── Scripture → Sacy. Renan's dominant citation target by far.
    ScriptureCiteRuleFrRoman(name="renan_scripture_cite_fr_roman"),
    ScriptureCiteRuleFr(name="renan_scripture_cite_fr"),
    # Josephus — Renan's constant source for the Herodian / Roman
    # period; cited by name on nearly every other page of the later
    # Histoire volumes and L'Antéchrist. Out-of-corpus target.
    StrongMentionRule(
        name="renan_josephe",
        target_author="Josephus",
        target_work="",
        forms=("Josèphe", "Josephe", "Flavius Josèphe", "Josephus"),
        confidence=0.9,
        langs=("fra",),
        note="Antiquités judaïques / Guerre des Juifs — Renan's primary "
        "extra-biblical source for Second-Temple history.",
    ),
    # Philo of Alexandria — the Hellenistic-Judaism interlocutor.
    StrongMentionRule(
        name="renan_philon",
        target_author="Philo",
        target_work="",
        forms=("Philon",),
        confidence=0.88,
        langs=("fra",),
        note="Almost always Philo of Alexandria in Renan's period "
        "writing (not the mechanician of Byzantium).",
    ),
    # Origen — host of the Contra Celsum; Renan's L'Antéchrist and
    # Marc-Aurèle discuss him repeatedly.
    AuthorMentionRule(
        name="renan_origene",
        target_author="Origen",
        target_work="",
        forms=("Origène", "origéniste"),
        confidence=0.8,
        langs=("fra",),
    ),
    # Spinoza — the Tractatus is the founding text of the biblical
    # criticism Renan practices; named with reverence throughout.
    AuthorMentionRule(
        name="renan_spinoza",
        target_author="Spinoza",
        target_work="Tractatus Theologico-Politicus",
        forms=("Spinoza", "Spinosa", "spinoziste"),
        confidence=0.8,
        langs=("fra",),
    ),
    # D. F. Strauss — Das Leben Jesu (1835) is the German
    # higher-criticism predecessor the Vie de Jésus answers.
    # Out-of-corpus target.
    AuthorMentionRule(
        name="renan_strauss",
        target_author="Strauss",
        target_work="Das Leben Jesu",
        forms=("Strauss", "Strausz", "M. Strauss"),
        confidence=0.78,
        langs=("fra",),
        note="D. F. Strauss's Das Leben Jesu (1835) is the German "
        "higher-criticism predecessor of Renan's Vie de Jésus.",
    ),
    # Celsus — the Alēthēs Logos survives inside Origen's reply;
    # route to the in-corpus host author the way nietzsche/origen
    # rules do.
    AuthorMentionRule(
        name="renan_celse",
        target_author="Origen",
        target_work="Contra Celsum",
        forms=("Celse",),
        confidence=0.7,
        langs=("fra",),
        note="Celsus's text is lost; Origen's Contra Celsum is the in-corpus host.",
    ),
    AuthorMentionRule(
        name="renan_platon",
        target_author="Plato",
        target_work="",
        forms=("Platon", "platonicien", "platonicienne", "platonisme"),
        confidence=0.7,
        langs=("fra",),
    ),
    # Seneca — out-of-corpus; L'Antéchrist pairs him with Paul.
    AuthorMentionRule(
        name="renan_seneque",
        target_author="Seneca",
        target_work="",
        forms=("Sénèque", "Seneque"),
        confidence=0.75,
        langs=("fra",),
    ),
    AuthorMentionRule(
        name="renan_ciceron",
        target_author="Cicero",
        target_work="",
        forms=("Cicéron", "Ciceron"),
        confidence=0.8,
        langs=("fra",),
    ),
    # Marcus Aurelius — the terminus of the Origines du christianisme.
    StrongMentionRule(
        name="renan_marc_aurele",
        target_author="Marcus Aurelius",
        target_work="",
        forms=("Marc-Aurèle", "Marc Aurèle"),
        confidence=0.9,
        langs=("fra",),
    ),
    AuthorMentionRule(
        name="renan_aristote",
        target_author="Aristotle",
        target_work="",
        forms=("Aristote", "aristotélicien", "aristotélisme"),
        confidence=0.7,
        langs=("fra",),
    ),
    AuthorMentionRule(
        name="renan_augustin",
        target_author="Augustine",
        target_work="",
        forms=("saint Augustin", "Augustin", "augustinien"),
        confidence=0.6,
        langs=("fra",),
        note="Lower confidence: 'Augustin' unqualified can be a modern "
        "given name in Renan's period references.",
    ),
    AuthorMentionRule(
        name="renan_epictete",
        target_author="Epictetus",
        target_work="",
        forms=("Épictète", "Epictète"),
        confidence=0.85,
        langs=("fra",),
    ),
)
