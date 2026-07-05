"""Rules that fire on Hobbes chunks.

Hobbes's principal named interlocutors are Aristotle ("the
philosopher of Stagira" who frames the whole Leviathan ch. 46
polemic), Plato, Cicero ("Tully"), Thucydides (whom Hobbes
translated), and Descartes (the Objections to the Meditations were
written before Leviathan). His standard term for the late medieval
Aristotelians is "the Schoolmen" — at the rough resolution of our
corpus this almost always means Aquinas.

The rules are bilingual: each interlocutor gets surface forms in
both English (modern spelling, the 1651/1650 English editions) and
Latin (declined forms, the 1668 Leviathan / 1642 De Cive). The
Latin Hobbes uses standard Renaissance Latin spellings — Aristoteles
/ Aristotelis, Plato / Platonis, Cicero / Ciceronis.
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule
from .scripture_cite import ScriptureCiteRule, ScriptureCiteRuleEn

RULES = (
    # ── English scripture cites → KJV. Hobbes is the corpus's heaviest
    # biblical exegete — Leviathan Parts III–IV are book-by-book
    # biblical interpretation. Expect the largest citation count
    # of any modern author.
    ScriptureCiteRuleEn(name="hobbes_scripture_cite_en"),
    # ── Latin Vulgate cites → the 1668 Latin Leviathan and 1642 De
    # Cive quote scripture in Latin; without this rule those biblical
    # citations were never detected (issue #55).
    ScriptureCiteRule(name="hobbes_scripture_cite_lat"),
    # Aristotle — Hobbes's central polemical target in Leviathan
    # part IV ("Of the Kingdom of Darkness") and the De Cive
    # preface. References are frequent and explicit; high
    # confidence on the strong-name form.
    AuthorMentionRule(
        name="hobbes_aristotle_eng",
        target_author="Aristotle",
        target_work="",
        forms=("Aristotle", "Aristotelian", "Aristotelians", "Stagirite"),
        confidence=0.75,
        langs=("eng",),
        note=(
            "Hobbes engages Aristotle by name throughout Leviathan "
            "(ch 4, 12, 46) and De Cive (preface, ch 1). 'Stagirite' "
            "is a periphrasis but used unambiguously of Aristotle."
        ),
    ),
    AuthorMentionRule(
        name="hobbes_aristotle_lat",
        target_author="Aristotle",
        target_work="",
        forms=(
            "Aristoteles",
            "Aristotelis",
            "Aristotelem",
            "Aristotele",
            "Aristotelici",
        ),
        confidence=0.75,
        langs=("lat",),
    ),
    # Plato — referenced less often than Aristotle but as a counter-
    # weight ("Plato was one of the greatest philosophers" — Lev. 46).
    AuthorMentionRule(
        name="hobbes_plato_eng",
        target_author="Plato",
        target_work="",
        forms=("Plato", "Platonist", "Platonists", "Platonic"),
        confidence=0.65,
        langs=("eng",),
    ),
    AuthorMentionRule(
        name="hobbes_plato_lat",
        target_author="Plato",
        target_work="",
        forms=("Plato", "Platonis", "Platonem", "Platone"),
        confidence=0.65,
        langs=("lat",),
    ),
    # Cicero — Hobbes calls him "Tully" in the English Leviathan
    # (the standard 17th-c. anglicization). Both forms fire.
    AuthorMentionRule(
        name="hobbes_cicero_eng",
        target_author="Cicero",
        target_work="",
        forms=("Cicero", "Tully", "Tullie"),
        confidence=0.7,
        langs=("eng",),
        note=(
            "Hobbes alternates 'Cicero' and 'Tully' — the latter from "
            "Tullius (Cicero's nomen). Both are unambiguous in context."
        ),
    ),
    AuthorMentionRule(
        name="hobbes_cicero_lat",
        target_author="Cicero",
        target_work="",
        forms=("Cicero", "Ciceronis", "Ciceronem", "Cicerone", "Tullius"),
        confidence=0.7,
        langs=("lat",),
    ),
    # Thucydides — Hobbes translated him in 1629; references in the
    # later works are pointed and high-confidence. Out-of-corpus
    # target (we don't have Thucydides in minerva yet) but rules
    # still emit candidates that the verifier downstream can route.
    StrongMentionRule(
        name="hobbes_thucydides",
        target_author="Thucydides",
        target_work="",
        forms=("Thucydides", "Thucydidem", "Thucydidis"),
        confidence=0.85,
        langs=(),  # both English and Latin
        note=(
            "Hobbes was Thucydides's first English translator (1629). "
            "Any named reference is deliberate."
        ),
    ),
    # The Schoolmen → Aquinas-shaped (out of strict accuracy this
    # spans the whole scholastic tradition, but in minerva the only
    # scholastic we have ingested is Aquinas, so route there).
    StrongMentionRule(
        name="hobbes_schoolmen",
        target_author="Aquinas",
        target_work="",
        forms=(
            "Schoolmen",
            "School-men",
            "Schoolemen",
            "Schoolman",
            "Schoolmans",
            "Scholastics",
        ),
        confidence=0.8,
        langs=("eng",),
        note=(
            "Hobbes's standard English term for the medieval "
            "Aristotelians. Routed to Aquinas as the sole in-corpus "
            "representative; downstream verification may upgrade or "
            "broaden the target."
        ),
    ),
    # Descartes — Hobbes wrote the Third Objections to the
    # Meditations (1641), and the Cartesian framework is referenced
    # in the De Corpore / De Homine cycle.
    AuthorMentionRule(
        name="hobbes_descartes_eng",
        target_author="Descartes",
        target_work="",
        forms=("Descartes", "Cartesian", "Cartesians"),
        confidence=0.7,
        langs=("eng",),
    ),
    AuthorMentionRule(
        name="hobbes_descartes_lat",
        target_author="Descartes",
        target_work="",
        forms=("Cartesius", "Cartesii", "Cartesium", "Cartesio", "Cartesianus"),
        confidence=0.7,
        langs=("lat",),
    ),
    # Lucretius — Hobbes's materialist physics in De Corpore is
    # explicitly Lucretian; the Elementa de Corpore reference
    # Lucretius by name on atomism + the void.
    AuthorMentionRule(
        name="hobbes_lucretius",
        target_author="Lucretius",
        target_work="",
        forms=("Lucretius", "Lucreti", "Lucretium", "Lucretian"),
        confidence=0.85,
        langs=("eng", "lat"),
        note=(
            "Hobbes's materialism descends from Lucretius's atomism. "
            "De Corpore + De Homine cite Lucretius on void and matter."
        ),
    ),
)
