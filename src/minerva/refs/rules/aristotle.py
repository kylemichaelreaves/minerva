"""Rules that fire on Aristotle chunks.

Aristotle's outbound citations cluster on a handful of predecessors:
Plato (his teacher — pervasive, especially in Metaphysics, NE,
Politics), Homer (Poetics is built around Homeric examples;
Rhetoric and Politics cite him too), and the Presocratics
(Heraclitus, Parmenides, Empedocles, Anaxagoras, Pythagoras).
Hesiod, Solon, and various tragedians appear occasionally.

Many citations are bare names; the Poetics in particular drops
character names from Homer (Achilles, Odysseus) and the tragedians
(Oedipus) as shorthand for the works they appear in. A character-
name-as-work-cite rule is possible but high-noise; for now we stick
to named-author rules and let the LLM stage label the references
the embed-verify pass surfaces.
"""

from __future__ import annotations

from . import AuthorMentionRule, _figures

RULES = (
    # ── Homer ─────────────────────────────────────────────────────
    AuthorMentionRule(
        name="aristotle_homer_grc",
        target_author="Homer",
        target_work="",
        forms=_figures.HOMER_GRC,
        confidence=0.75,
        langs=("grc",),
        note=(
            "Aristotle's Poetics is built around Homer; Rhetoric, "
            "Politics, and NE cite him repeatedly. High confidence "
            "because the named-author convention in Aristotle is "
            "consistent."
        ),
    ),
    AuthorMentionRule(
        name="aristotle_homer_eng",
        target_author="Homer",
        target_work="",
        forms=_figures.HOMER_ENG,
        confidence=0.75,
        langs=("eng",),
    ),
    # ── Plato ─────────────────────────────────────────────────────
    AuthorMentionRule(
        name="aristotle_plato_grc",
        target_author="Plato",
        target_work="",
        forms=("Πλάτων", "Πλάτωνος", "Πλάτωνα", "Πλάτωνι"),
        confidence=0.75,
        langs=("grc",),
        note=(
            "Aristotle constantly engages Plato — usually critically. "
            "Metaphysics A.9, Lambda; NE I.6; Politics II.1-5."
        ),
    ),
    AuthorMentionRule(
        name="aristotle_plato_eng",
        target_author="Plato",
        target_work="",
        forms=("Plato", "Plato's", "Platonic", "Platonist", "Platonists"),
        confidence=0.75,
        langs=("eng",),
    ),
    # ── Hesiod ────────────────────────────────────────────────────
    AuthorMentionRule(
        name="aristotle_hesiod_grc",
        target_author="Hesiod",
        target_work="",
        forms=_figures.HESIOD_GRC,
        confidence=0.65,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="aristotle_hesiod_eng",
        target_author="Hesiod",
        target_work="",
        forms=_figures.HESIOD_ENG,
        confidence=0.65,
        langs=("eng",),
    ),
    # ── Heraclitus ────────────────────────────────────────────────
    AuthorMentionRule(
        name="aristotle_heraclitus_grc",
        target_author="Heraclitus",
        target_work="",
        forms=_figures.HERACLITUS_GRC,
        confidence=0.7,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="aristotle_heraclitus_eng",
        target_author="Heraclitus",
        target_work="",
        forms=_figures.HERACLITUS_ENG,
        confidence=0.7,
        langs=("eng",),
    ),
    # ── Parmenides ────────────────────────────────────────────────
    AuthorMentionRule(
        name="aristotle_parmenides_grc",
        target_author="Parmenides",
        target_work="",
        forms=_figures.PARMENIDES_GRC,
        confidence=0.7,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="aristotle_parmenides_eng",
        target_author="Parmenides",
        target_work="",
        forms=("Parmenides", "Parmenidean"),
        confidence=0.7,
        langs=("eng",),
    ),
    # ── Empedocles ────────────────────────────────────────────────
    AuthorMentionRule(
        name="aristotle_empedocles_grc",
        target_author="Empedocles",
        target_work="",
        forms=("Ἐμπεδοκλῆς", "Ἐμπεδοκλέους", "Ἐμπεδοκλέα", "Ἐμπεδοκλεῖ"),
        confidence=0.7,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="aristotle_empedocles_eng",
        target_author="Empedocles",
        target_work="",
        forms=("Empedocles",),
        confidence=0.7,
        langs=("eng",),
    ),
    # ── Anaxagoras ────────────────────────────────────────────────
    AuthorMentionRule(
        name="aristotle_anaxagoras_grc",
        target_author="Anaxagoras",
        target_work="",
        forms=_figures.ANAXAGORAS_GRC,
        confidence=0.7,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="aristotle_anaxagoras_eng",
        target_author="Anaxagoras",
        target_work="",
        forms=_figures.ANAXAGORAS_ENG,
        confidence=0.7,
        langs=("eng",),
    ),
    # ── Pythagoras / Pythagoreans ─────────────────────────────────
    AuthorMentionRule(
        name="aristotle_pythagoras_grc",
        target_author="Pythagoras",
        target_work="",
        forms=_figures.PYTHAGORAS_GRC,
        confidence=0.65,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="aristotle_pythagoras_eng",
        target_author="Pythagoras",
        target_work="",
        forms=_figures.PYTHAGORAS_ENG,
        confidence=0.65,
        langs=("eng",),
    ),
    # ── Democritus ────────────────────────────────────────────────
    AuthorMentionRule(
        name="aristotle_democritus_grc",
        target_author="Democritus",
        target_work="",
        forms=("Δημόκριτος", "Δημοκρίτου", "Δημόκριτον", "Δημοκρίτῳ"),
        confidence=0.7,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="aristotle_democritus_eng",
        target_author="Democritus",
        target_work="",
        forms=("Democritus", "Democritean"),
        confidence=0.7,
        langs=("eng",),
    ),
    # ── Aeschylus (Poetics, Politics) ─────────────────────────────
    # Aristotle names Aeschylus as a structural innovator in the
    # Poetics 1449a — "two actors instead of one, primary role to
    # the dialogue".
    AuthorMentionRule(
        name="aristotle_aeschylus_grc",
        target_author="Aeschylus",
        target_work="",
        forms=_figures.AESCHYLUS_GRC,
        confidence=0.75,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="aristotle_aeschylus_eng",
        target_author="Aeschylus",
        target_work="",
        forms=_figures.AESCHYLUS_ENG,
        confidence=0.75,
        langs=("eng",),
    ),
    # ── Sophocles (Poetics — Oedipus is THE tragic exemplar) ──────
    AuthorMentionRule(
        name="aristotle_sophocles_grc",
        target_author="Sophocles",
        target_work="",
        forms=_figures.SOPHOCLES_GRC,
        confidence=0.8,
        langs=("grc",),
        note=(
            "Sophocles is Aristotle's preferred tragedian — the Poetics "
            "returns to Oedipus Tyrannus as the paradigm of well-formed "
            "tragedy. Higher confidence than the other tragedians."
        ),
    ),
    AuthorMentionRule(
        name="aristotle_sophocles_eng",
        target_author="Sophocles",
        target_work="",
        forms=_figures.SOPHOCLES_ENG,
        confidence=0.8,
        langs=("eng",),
    ),
    # ── Euripides ──────────────────────────────────────────────────
    # Aristotle calls Euripides "the most tragic of poets" (Poetics
    # 1453a) despite his structural complaints — heavy citation.
    AuthorMentionRule(
        name="aristotle_euripides_grc",
        target_author="Euripides",
        target_work="",
        forms=_figures.EURIPIDES_GRC,
        confidence=0.75,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="aristotle_euripides_eng",
        target_author="Euripides",
        target_work="",
        forms=_figures.EURIPIDES_ENG,
        confidence=0.75,
        langs=("eng",),
    ),
    # Theognis — NE IX.9 (1170a) quotes the "ἀνδρὸς γνωμη" proverb
    # often attributed to Theognis; other elegiac quotations recur in
    # the ethical works.
    AuthorMentionRule(
        name="aristotle_theognis",
        target_author="Theognis",
        target_work="",
        forms=_figures.THEOGNIS_GRC,
        confidence=0.88,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="aristotle_theognis_eng",
        target_author="Theognis",
        target_work="",
        forms=_figures.THEOGNIS_ENG,
        confidence=0.85,
        langs=("eng",),
    ),
    # Aesop — *Rhetoric* II.20 (1393b8) names Aesop as paradigmatic
    # source of rhetorical *paradeigma* (example by fable). The
    # *Meteorologica* and *Historia Animalium* also cite Aesopic
    # natural-history fables, but those are weak rule territory.
    AuthorMentionRule(
        name="aristotle_aesop",
        target_author="Aesop",
        target_work="",
        forms=("Αἴσωπος", "Αἰσώπου", "Αἰσώπῳ", "Αἴσωπον"),
        confidence=0.88,
        langs=("grc",),
        note="Rhetoric II.20 (1393b8): Aesop as paradigm of fable-as-example.",
    ),
    AuthorMentionRule(
        name="aristotle_aesop_eng",
        target_author="Aesop",
        target_work="",
        forms=("Aesop", "Aesopic"),
        confidence=0.85,
        langs=("eng",),
    ),
)
