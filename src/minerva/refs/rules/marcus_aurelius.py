"""Rules that fire on Marcus Aurelius chunks.

The *Meditations* names a small set of philosophical exemplars,
mostly Stoic + Socratic:

  * **Epictetus** — Marcus Aurelius's explicit philosophical
    teacher; the Meditations open with thanks to Rusticus for
    introducing him to Epictetus. Strong rule.
  * **Socrates** — recurring paradigm of the philosophical life.
  * **Heraclitus** — Marcus cites Heraclitus's fragments
    repeatedly on flux and the logos.
  * **Chrysippus** — Stoic theorist (out-of-corpus).
  * **Plato** — referenced occasionally.
  * **Pythagoras** — referenced in Meditations VI.47.

All rules language-gated Greek + English.
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule, _figures

RULES = (
    # Epictetus — explicit teacher. Strong rule.
    StrongMentionRule(
        name="marcus_aurelius_epictetus",
        target_author="Epictetus",
        target_work="",
        forms=(
            "Ἐπίκτητος",
            "Ἐπίκτητον",
            "Ἐπικτήτου",
            "Ἐπικτήτῳ",
            "Epictetus",
        ),
        confidence=0.95,
        langs=("grc", "eng"),
        note=(
            "Marcus Aurelius's explicit philosophical teacher. "
            "Meditations I.7 thanks Rusticus for introducing him to "
            "Epictetus's writings."
        ),
    ),
    # Socrates — recurring exemplar.
    StrongMentionRule(
        name="marcus_aurelius_socrates",
        target_author="Socrates",
        target_work="",
        forms=_figures.SOCRATES_GRC_ENG,
        confidence=0.9,
        langs=("grc", "eng"),
    ),
    # Heraclitus — cited on flux and logos.
    AuthorMentionRule(
        name="marcus_aurelius_heraclitus",
        target_author="Heraclitus",
        target_work="",
        forms=(
            "Ἡράκλειτος",
            "Ἡράκλειτον",
            "Ἡρακλείτου",
            "Heraclitus",
            "Heraclitean",
        ),
        confidence=0.88,
        langs=("grc", "eng"),
    ),
    # Chrysippus — out-of-corpus Stoic.
    AuthorMentionRule(
        name="marcus_aurelius_chrysippus",
        target_author="Chrysippus",
        target_work="",
        forms=_figures.CHRYSIPPUS_GRC_ENG,
        confidence=0.85,
        langs=("grc", "eng"),
    ),
    # Plato — referenced occasionally.
    AuthorMentionRule(
        name="marcus_aurelius_plato",
        target_author="Plato",
        target_work="",
        forms=_figures.PLATO_GRC_ENG,
        confidence=0.75,
        langs=("grc", "eng"),
    ),
    # Pythagoras — referenced in Meditations VI.47.
    AuthorMentionRule(
        name="marcus_aurelius_pythagoras",
        target_author="Pythagoras",
        target_work="",
        forms=("Πυθαγόρας", "Πυθαγόραν", "Πυθαγόρου", "Πυθαγόρειοι", "Pythagoras"),
        confidence=0.7,
        langs=("grc", "eng"),
    ),
)
