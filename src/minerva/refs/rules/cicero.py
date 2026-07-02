"""Rules that fire on Cicero chunks.

Cicero's philosophical works are doxographic — they explicitly
catalogue the views of his Greek predecessors. The cluster:

  * **Plato** — Cicero's most-cited philosophical authority,
    especially in De Re Publica (Cicero's De Re Publica is a
    deliberate response to Plato's). Strong rule.
  * **Aristotle** — frequently named.
  * **Socrates** — Tusculans Bk I + V are full of Socratic exempla.
  * **Carneades** — the New Academy skeptic Cicero defers to.
  * **Panaetius** — Stoic source for De Officiis.
  * **Epicurus** — explicit polemical target in De Finibus + De
    Natura Deorum.
  * **Stoics / Zeno / Chrysippus** — frequently cited collectively.
  * **Pythagoras** — name appears in De Re Publica + Tusculans.

All rules language-gated to Latin + English.
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule

RULES = (
    # Plato — Cicero's most-cited philosophical authority. Strong
    # rule because the form is unambiguous.
    StrongMentionRule(
        name="cicero_plato",
        target_author="Plato",
        target_work="",
        forms=(
            "Plato",
            "Platonis",
            "Platonem",
            "Platone",
            "Platonis",
            "Platonicus",
            "Platonici",
            "Platonic",
            "Platonist",
            "Platonists",
        ),
        confidence=0.92,
        langs=("lat", "eng"),
    ),
    AuthorMentionRule(
        name="cicero_aristotle",
        target_author="Aristotle",
        target_work="",
        forms=(
            "Aristoteles",
            "Aristotelis",
            "Aristotelem",
            "Aristotele",
            "Aristotle",
            "Aristotelian",
            "Peripatetic",
            "Peripatetics",
        ),
        confidence=0.85,
        langs=("lat", "eng"),
    ),
    # Socrates — recurring exemplar in Tusculans.
    StrongMentionRule(
        name="cicero_socrates",
        target_author="Socrates",
        target_work="",
        forms=("Socrates", "Socratis", "Socratem", "Socrate", "Socratic"),
        confidence=0.9,
        langs=("lat", "eng"),
    ),
    # Carneades — Cicero's New Academy authority on probability.
    # Out-of-corpus target.
    AuthorMentionRule(
        name="cicero_carneades",
        target_author="Carneades",
        target_work="",
        forms=("Carneades", "Carneadis", "Carneadem"),
        confidence=0.88,
        langs=("lat", "eng"),
        note=(
            "Carneades of Cyrene. Cicero's Academica defers to him on "
            "probability epistemology. Out-of-corpus."
        ),
    ),
    # Panaetius — Stoic basis for De Officiis. Out-of-corpus.
    AuthorMentionRule(
        name="cicero_panaetius",
        target_author="Panaetius",
        target_work="",
        forms=("Panaetius", "Panaeti", "Panaetium"),
        confidence=0.88,
        langs=("lat", "eng"),
        note=("Panaetius of Rhodes. De Officiis I-II adapts his Περὶ καθήκοντος. Out-of-corpus."),
    ),
    # Epicurus — explicit polemical target (De Finibus I-II + DND).
    StrongMentionRule(
        name="cicero_epicurus",
        target_author="Epicurus",
        target_work="",
        forms=(
            "Epicurus",
            "Epicuri",
            "Epicurum",
            "Epicuro",
            "Epicurus's",
            "Epicurean",
            "Epicureans",
        ),
        confidence=0.92,
        langs=("lat", "eng"),
        note="Out-of-corpus polemical target across the philosophical works.",
    ),
    # Democritus — atomism's founder; De Finibus, Tusculanae
    # Disputationes, and De Natura Deorum all name him as the
    # materialist ancestor behind the Epicurean physics Cicero attacks.
    StrongMentionRule(
        name="cicero_democritus",
        target_author="Democritus",
        target_work="",
        forms=("Democritus", "Democriti", "Democritum", "Democrito", "Democritean"),
        confidence=0.9,
        langs=("lat", "eng"),
        note=(
            "Cicero discusses Democritus in De Finibus, Tusculanae "
            "Disputationes, and De Natura Deorum. Out-of-corpus."
        ),
    ),
    # Zeno of Citium / Chrysippus / Stoics — collective Stoa reference.
    AuthorMentionRule(
        name="cicero_zeno",
        target_author="Zeno",
        target_work="",
        forms=("Zeno", "Zenonis", "Zenonem"),
        confidence=0.75,
        langs=("lat", "eng"),
        note=(
            "Zeno of Citium (Stoa founder). Cicero distinguishes by "
            "context; we accept all 'Zeno' mentions as the Stoic by "
            "default — Zeno of Elea (pre-Socratic) is rarely named "
            "in Cicero. Out-of-corpus."
        ),
    ),
    AuthorMentionRule(
        name="cicero_chrysippus",
        target_author="Chrysippus",
        target_work="",
        forms=("Chrysippus", "Chrysippi", "Chrysippum"),
        confidence=0.88,
        langs=("lat", "eng"),
        note="Out-of-corpus.",
    ),
    AuthorMentionRule(
        name="cicero_pythagoras",
        target_author="Pythagoras",
        target_work="",
        forms=("Pythagoras", "Pythagorae", "Pythagoram", "Pythagorean", "Pythagoreans"),
        confidence=0.85,
        langs=("lat", "eng"),
    ),
    # ── Tragedians (Tusculan Disputations cites verse extensively) ─
    # Cicero quotes Aeschylus / Sophocles / Euripides as moral
    # exempla in Tusc. Disp. Bk II–IV and De Officiis Bk I. The
    # Latin orthography drops the Greek aspirate and inflects with
    # standard Latin declensions.
    AuthorMentionRule(
        name="cicero_aeschylus",
        target_author="Aeschylus",
        target_work="",
        forms=("Aeschylus", "Aeschyli", "Aeschylum", "Aeschylo"),
        confidence=0.85,
        langs=("lat", "eng"),
    ),
    AuthorMentionRule(
        name="cicero_sophocles",
        target_author="Sophocles",
        target_work="",
        forms=("Sophocles", "Sophoclis", "Sophoclem", "Sophocle"),
        confidence=0.85,
        langs=("lat", "eng"),
    ),
    AuthorMentionRule(
        name="cicero_euripides",
        target_author="Euripides",
        target_work="",
        forms=("Euripides", "Euripidis", "Euripidem", "Euripide"),
        confidence=0.85,
        langs=("lat", "eng"),
    ),
)
