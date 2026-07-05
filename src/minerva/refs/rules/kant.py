"""Rules that fire on Kant chunks.

Kant's interlocutors are mostly named openly in the Critique's
historical-introduction passages: Plato (the B-edition transcendental
ideal), Leibniz / Wolff (Amphiboly chapter), Hume (the Prolegomena's
"problem"), Berkeley (the Refutation of Idealism). The corpus has
both German originals and English Cambridge editions.
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule
from .scripture_cite import default_scripture_rules

RULES = (
    *default_scripture_rules("kant"),
    AuthorMentionRule(
        name="kant_plato",
        target_author="Plato",
        target_work="",
        forms=(
            "Plato",
            "Platon",
            "Platons",
            "Platonic",
            "Platonische",
            "Platonischen",
            "Platonism",
        ),
        confidence=0.7,
        langs=("deu", "eng"),
        note=(
            "Kant's B-edition transcendental ideal (B370 ff.) frames "
            "the Critique against the Platonic Ideas. The most "
            "explicit Kant-on-Plato moment in the corpus."
        ),
    ),
    AuthorMentionRule(
        name="kant_aristotle",
        target_author="Aristotle",
        target_work="",
        forms=(
            "Aristotle",
            "Aristoteles",
            "Aristotelian",
            "Aristotelische",
            "Aristotelischen",
        ),
        confidence=0.6,
        langs=("deu", "eng"),
        note=(
            "Kant's Metaphysical Deduction lifts the categories from Aristotle by name (A80/B106)."
        ),
    ),
    AuthorMentionRule(
        name="kant_leibniz",
        target_author="Leibniz",  # out-of-corpus
        target_work="",
        forms=("Leibniz", "Leibnizens", "Leibnitian", "Leibnizsche", "Leibnizschen"),
        confidence=0.7,
        langs=("deu", "eng"),
        note=(
            "Kant's Amphiboly chapter (A260/B316) is structurally a "
            "polemic against Leibniz. Out-of-corpus."
        ),
    ),
    AuthorMentionRule(
        name="kant_hume",
        target_author="Hume",
        target_work="",
        forms=("Hume", "Humes", "Humean", "Humesche", "Humeschen"),
        confidence=0.75,
        langs=("deu", "eng"),
        note=(
            "Kant's 'dogmatic slumber' awakening — Hume is named "
            "openly in the Prolegomena's introduction."
        ),
    ),
    AuthorMentionRule(
        name="kant_descartes",
        target_author="Descartes",
        target_work="",
        forms=(
            "Descartes",
            "Cartesianisch",
            "Cartesianischen",
            "Cartesian",
            "Cartesianism",
        ),
        confidence=0.65,
        langs=("deu", "eng"),
        note=(
            "Kant's Refutation of Idealism (B274 ff.) is structurally "
            "anti-Cartesian; the Paralogisms also engage Descartes."
        ),
    ),
    AuthorMentionRule(
        name="kant_spinoza",
        target_author="Spinoza",
        target_work="",
        forms=("Spinoza", "Spinozas", "Spinozism", "Spinozismus"),
        confidence=0.6,
        langs=("deu", "eng"),
        note=(
            "Kant's Critique of Practical Reason's Anlage / postulates "
            "discussion names Spinoza as the radical-pantheist alternative."
        ),
    ),
    AuthorMentionRule(
        name="kant_berkeley",
        target_author="Berkeley",  # out-of-corpus
        target_work="",
        forms=("Berkeley", "Berkeleys", "Berkeleyan"),
        confidence=0.6,
        langs=("deu", "eng"),
        note="Refutation of Idealism (B274).",
    ),
    AuthorMentionRule(
        name="kant_wolff",
        target_author="Wolff",  # out-of-corpus
        target_work="",
        forms=("Wolff", "Wolffs", "Wolffian", "Wolffischen", "Wolffsche"),
        confidence=0.6,
        langs=("deu", "eng"),
        note="The Leibniz-Wolff school is Kant's local foil.",
    ),
    # Rousseau — Kant's principal modern moral influence. Kant
    # famously credited Rousseau with his moral-philosophical
    # turn: "Rousseau set me right." References pervade the second
    # Critique, the Religion within the Boundaries, and the
    # Anthropology. Strong rule.
    StrongMentionRule(
        name="kant_rousseau",
        target_author="Rousseau",
        target_work="",
        forms=(
            "Rousseau",
            "Rousseaus",
            "Rousseausche",
            "Rousseauschen",
            "rousseauisch",
        ),
        confidence=0.92,
        langs=("deu", "eng"),
        note=(
            "Kant's 'Newton of the moral world'. The second Critique "
            "and Religion within the Boundaries are pervasively "
            "Rousseauian; Kant kept a portrait of Rousseau on his "
            "study wall."
        ),
    ),
    # Hobbes — Kant engages Hobbes's political philosophy in the
    # Metaphysics of Morals (Doctrine of Right) and Theory and
    # Practice essay.
    AuthorMentionRule(
        name="kant_hobbes",
        target_author="Hobbes",
        target_work="",
        forms=("Hobbes", "Hobbes'", "Hobbesisch", "Hobbesische", "Hobbesischen"),
        confidence=0.75,
        langs=("deu", "eng"),
        note=(
            "Kant's principal sparring partner on the state of "
            "nature and sovereignty in the Doctrine of Right."
        ),
    ),
    # Locke — Kant cites Locke as the founder of empiricism and
    # the Essay-style analysis of understanding; KrV B127, A86,
    # multiple Anthropology lectures.
    AuthorMentionRule(
        name="kant_locke",
        target_author="Locke",
        target_work="",
        forms=("Locke", "Lockes", "Lockesche", "Lockeschen", "lockesch"),
        confidence=0.85,
        langs=("deu", "eng"),
        note=(
            "Locke is one of Kant's two paired empiricists "
            "(with Hume); KrV B127 names him explicitly."
        ),
    ),
    # Newton — Kant's scientific authority. The Critique of Pure
    # Reason is methodologically Newtonian; the Metaphysical
    # Foundations of Natural Science is essentially commentary on
    # Newton's Principia. Out-of-corpus.
    AuthorMentionRule(
        name="kant_newton",
        target_author="Newton",
        target_work="",
        forms=("Newton", "Newtons", "Newtonisch", "Newtonische", "Newtonischen"),
        confidence=0.85,
        langs=("deu", "eng"),
        note=(
            "Kant's primary scientific authority; the Metaphysical "
            "Foundations of Natural Science is Newton-commentary. "
            "Out-of-corpus target."
        ),
    ),
)
