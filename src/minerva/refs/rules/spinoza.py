"""Rules that fire on Spinoza chunks.

Spinoza's Latin engages Descartes as a near-constant interlocutor.
He uses "Cartesius" / "Renatus Cartesius" throughout the Ethica
and Tractatus Theologico-Politicus; the Principia philosophiae
Cartesianae more componentibus demonstrata is itself a geometric
reconstruction of Descartes's project.

Other targets (Maimonides, Hobbes, the Stoics) are mentioned less
often and at lower confidence by default.
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule

RULES = (
    StrongMentionRule(
        name="spinoza_cartesius",
        target_author="Descartes",
        target_work="",
        forms=(
            "Cartesius",
            "Cartesii",
            "Cartesium",
            "Cartesio",
            "Renatus Cartesius",
            "Cartesianus",
            "Cartesianorum",
        ),
        confidence=0.93,
        langs=("lat",),
        note=(
            "Spinoza's primary interlocutor. The 'Cartesius' convention "
            "in Spinoza is as definitional as Aquinas's 'Philosophus' — "
            "every mention is Descartes, no ambiguity."
        ),
    ),

    AuthorMentionRule(
        name="spinoza_maimonides",
        target_author="Maimonides",
        target_work="",
        forms=("Maimonides", "Maimonidis", "Maimonidem"),
        confidence=0.75,
        langs=("lat",),
        note=(
            "Maimonides is named in the TTP's chapters on prophecy and "
            "biblical hermeneutics."
        ),
    ),

    AuthorMentionRule(
        name="spinoza_hobbes",
        target_author="Hobbes",
        target_work="",
        forms=("Hobbes", "Hobbesius", "Hobbesii", "Hobbesium"),
        confidence=0.7,
        langs=("lat",),
        note="The TTP and TP engage Hobbesian contractualism by name.",
    ),

    AuthorMentionRule(
        name="spinoza_aristoteles",
        target_author="Aristotle",
        target_work="",
        forms=(
            "Aristoteles",
            "Aristotelis",
            "Aristotelem",
            "Aristotele",
        ),
        confidence=0.6,
        langs=("lat",),
    ),

    AuthorMentionRule(
        name="spinoza_plato",
        target_author="Plato",
        target_work="",
        forms=("Plato", "Platonis", "Platonem", "Platone"),
        confidence=0.55,
        langs=("lat",),
    ),

    AuthorMentionRule(
        name="spinoza_seneca",
        target_author="Seneca",  # out-of-corpus
        target_work="",
        forms=("Seneca", "Senecae", "Senecam"),
        confidence=0.55,
        langs=("lat",),
    ),
)
