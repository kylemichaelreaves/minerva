"""Rules that fire on Schiller chunks.

Schiller's aesthetic essays are a sustained dialogue with Kant's third
Critique — the Aesthetic Education letters develop Kantian autonomy and
aesthetic judgment toward an account of freedom through art. Plato (the
Ideal, the Republic on education), Aristotle (the Poetics, in the tragedy
essays), and Homer (the archetypal "naive" poet of *Über naive und
sentimentalische Dichtung*) are named openly. Schiller is German-only, so
every rule gates on ``langs=("deu",)``.
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule
from .scripture_cite import default_scripture_rules

RULES = (
    *default_scripture_rules("schiller"),
    # Kant — the dominant interlocutor. The Ästhetische Briefe are
    # built on the Critique of Judgment; Schiller names Kant openly
    # and pervasively. Strong rule.
    StrongMentionRule(
        name="schiller_kant",
        target_author="Kant",
        target_work="",
        forms=("Kant", "Kants", "Kantisch", "Kantische", "Kantischen", "kantisch"),
        confidence=0.9,
        langs=("deu",),
        note=(
            "Schiller's aesthetic philosophy is a direct development of "
            "Kant's third Critique; the Aesthetic Education letters and "
            "Über Anmut und Würde engage Kant by name throughout."
        ),
    ),
    AuthorMentionRule(
        name="schiller_plato",
        target_author="Plato",
        target_work="",
        forms=("Plato", "Platon", "Platons", "Platonisch", "Platonische", "Platonischen"),
        confidence=0.65,
        langs=("deu",),
        note=(
            "Schiller invokes the Platonic Idea of beauty and the "
            "Republic's account of education in the aesthetic state."
        ),
    ),
    AuthorMentionRule(
        name="schiller_aristotle",
        target_author="Aristotle",
        target_work="",
        forms=("Aristoteles", "Aristotelisch", "Aristotelische", "Aristotelischen"),
        confidence=0.65,
        langs=("deu",),
        note=(
            "The tragedy essays (Über die tragische Kunst, Über das "
            "Pathetische) engage Aristotle's Poetics on pity, fear, "
            "and catharsis."
        ),
    ),
    AuthorMentionRule(
        name="schiller_homer",
        target_author="Homer",
        target_work="",
        forms=("Homer", "Homers", "Homerisch", "Homerische", "Homerischen"),
        confidence=0.6,
        langs=("deu",),
        note=(
            "Homer is the archetypal 'naive' poet in Über naive und "
            "sentimentalische Dichtung — Schiller's central example."
        ),
    ),
    AuthorMentionRule(
        name="schiller_rousseau",
        target_author="Rousseau",
        target_work="",
        forms=("Rousseau", "Rousseaus", "Rousseausche", "Rousseauschen"),
        confidence=0.6,
        langs=("deu",),
        note=(
            "Rousseau is Schiller's foil on nature vs. culture; the "
            "naive/sentimental distinction reworks Rousseau's lament "
            "for lost naturalness."
        ),
    ),
    # Goethe — Schiller's closest collaborator; named in the
    # naive/sentimental essay and Über epische und dramatische
    # Dichtung. Out-of-corpus target.
    AuthorMentionRule(
        name="schiller_goethe",
        target_author="Goethe",
        target_work="",
        forms=("Goethe", "Goethes", "Goethisch", "Goethesche", "Goetheschen"),
        confidence=0.6,
        langs=("deu",),
        note="Schiller's collaborator; out-of-corpus target.",
    ),
)
