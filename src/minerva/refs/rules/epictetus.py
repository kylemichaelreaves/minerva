"""Rules that fire on Epictetus chunks.

Epictetus's *Discourses* + *Enchiridion* engage a tight cluster of
Stoic and Socratic predecessors:

  * **Socrates** — Epictetus's hero, cited constantly as the
    paradigm of the philosophical life. Strong rule.
  * **Diogenes** of Sinope (the Cynic) — Epictetus's secondary
    paradigm of philosophical sufficiency.
  * **Chrysippus** — chief Stoic theorist (out-of-corpus target,
    central to Stoic logic and ethics references).
  * **Zeno** of Citium — Stoa's founder.
  * **Plato** — referenced via Socratic dialogues.

All language-gated to Greek + English.
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule

RULES = (
    # Socrates — Epictetus's central exemplar. Strong rule.
    StrongMentionRule(
        name="epictetus_socrates",
        target_author="Socrates",
        target_work="",
        forms=(
            "Σωκράτης",
            "Σωκράτη",
            "Σωκράτους",
            "Σωκράτει",
            "Socrates",
            "Socratic",
        ),
        confidence=0.93,
        langs=("grc", "eng"),
        note=(
            "Epictetus's paradigmatic philosopher; Socrates appears "
            "as model of the Stoic sage throughout the Discourses."
        ),
    ),

    # Diogenes the Cynic — secondary paradigm.
    AuthorMentionRule(
        name="epictetus_diogenes",
        target_author="Diogenes",
        target_work="",
        forms=("Διογένης", "Διογένην", "Διογένους", "Diogenes"),
        confidence=0.85,
        langs=("grc", "eng"),
        note="Diogenes of Sinope (Cynic). Out-of-corpus target.",
    ),

    # Chrysippus — central Stoic.
    AuthorMentionRule(
        name="epictetus_chrysippus",
        target_author="Chrysippus",
        target_work="",
        forms=("Χρύσιππος", "Χρύσιππον", "Χρυσίππου", "Chrysippus"),
        confidence=0.9,
        langs=("grc", "eng"),
        note="Chrysippus of Soli. Out-of-corpus target.",
    ),

    # Zeno of Citium — Stoa founder.
    AuthorMentionRule(
        name="epictetus_zeno",
        target_author="Zeno",
        target_work="",
        forms=("Ζήνων", "Ζήνωνα", "Ζήνωνος", "Zeno"),
        confidence=0.85,
        langs=("grc", "eng"),
        note="Zeno of Citium. Out-of-corpus target.",
    ),

    # Plato — Epictetus references through the Socratic dialogues.
    AuthorMentionRule(
        name="epictetus_plato",
        target_author="Plato",
        target_work="",
        forms=("Πλάτων", "Πλάτωνα", "Πλάτωνος", "Plato"),
        confidence=0.75,
        langs=("grc", "eng"),
    ),
)
