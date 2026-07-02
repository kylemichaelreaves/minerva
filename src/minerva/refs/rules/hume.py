"""Rules that fire on Hume chunks.

Hume's two ingested works engage roughly the same set of
interlocutors but in different proportions:

* The *Treatise of Human Nature* (1739) — Locke is the dominant
  interlocutor; Berkeley a close second (Hume builds the
  impressions-vs-ideas distinction on Locke's *Essay* and Berkeley's
  *Principles*). Descartes is the rationalist target. Hobbes and
  Newton appear by name.

* The *Enquiry Concerning Human Understanding* (1748) — the more
  popular reformulation. Same interlocutors with Cicero added as a
  rhetorical model.

Newton is named as "Mr. Newton" / "Sir Isaac Newton" — Hume self-
identifies as bringing the Newtonian method to "moral subjects."

All rules gate on `langs=("eng",)` — Hume is English-only.
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule
from .scripture_cite import ScriptureCiteRuleEn

RULES = (
    # ── English scripture cites → KJV. Hume's biblical engagement is
    # lightest of the British triad — Natural History of Religion and
    # Of Miracles cite scripture in critique. Expect <50 cites total.
    ScriptureCiteRuleEn(name="hume_scripture_cite_en"),
    # Locke — Hume's most-cited modern predecessor. The Treatise's
    # impressions-and-ideas distinction is a self-conscious refinement
    # of Locke's Essay Bk II ch 1.
    AuthorMentionRule(
        name="hume_locke",
        target_author="Locke",
        target_work="",
        forms=("Locke", "Lockean", "Locke's", "Mr. Locke"),
        confidence=0.8,
        langs=("eng",),
    ),
    # Berkeley — engaged on idealism and abstract ideas. Hume both
    # accepts and rejects Berkeley in different places; the named
    # references are deliberate.
    AuthorMentionRule(
        name="hume_berkeley",
        target_author="Berkeley",
        target_work="",
        forms=("Berkeley", "Berkeley's", "Berkleian", "Berkeleian"),
        confidence=0.85,
        langs=("eng",),
        note=(
            "Hume on abstract ideas (Treatise I.i.7) explicitly invokes "
            "Berkeley's nominalist critique. Out-of-corpus target."
        ),
    ),
    # Descartes — the rationalist target. The Treatise's attack on
    # the cogito (I.iv.5–6) and on Cartesian doubt frames the whole
    # sceptical project.
    AuthorMentionRule(
        name="hume_descartes",
        target_author="Descartes",
        target_work="",
        forms=("Descartes", "Cartesian", "Cartesians", "Cartesianism"),
        confidence=0.75,
        langs=("eng",),
    ),
    # Hobbes — moral and political philosophy. Hume's contract-
    # theory critique in the Treatise Bk III engages Hobbes by name.
    AuthorMentionRule(
        name="hume_hobbes",
        target_author="Hobbes",
        target_work="",
        forms=("Hobbes", "Hobbes's", "Hobbist", "Hobbists", "Hobbesian"),
        confidence=0.75,
        langs=("eng",),
    ),
    # Newton — Hume's methodological model. "Mr. Newton" / "Sir
    # Isaac Newton" appears in the Treatise introduction and in the
    # Enquiry's prefatory remarks.
    StrongMentionRule(
        name="hume_newton",
        target_author="Newton",
        target_work="",
        forms=(
            "Newton",
            "Newtonian",
            "Sir Isaac Newton",
            "Mr. Newton",
            "Newton's",
        ),
        confidence=0.85,
        langs=("eng",),
        note=("Hume self-positions as the 'Newton of the moral sciences'. Out-of-corpus target."),
    ),
    # Cicero — moral-philosophy authority and rhetorical model.
    AuthorMentionRule(
        name="hume_cicero",
        target_author="Cicero",
        target_work="",
        forms=("Cicero", "Tully", "Ciceronian"),
        confidence=0.7,
        langs=("eng",),
    ),
    # Aristotle — engaged primarily as the source of the scholastic
    # apparatus Hume is critiquing.
    AuthorMentionRule(
        name="hume_aristotle",
        target_author="Aristotle",
        target_work="",
        forms=("Aristotle", "Aristotelian", "Aristotelians", "Peripatetic"),
        confidence=0.65,
        langs=("eng",),
    ),
    # The Schoolmen — Hume's term for the scholastic Aristotelians;
    # routed to Aquinas as the in-corpus representative.
    StrongMentionRule(
        name="hume_schoolmen",
        target_author="Aquinas",
        target_work="",
        forms=("Schoolmen", "School-men", "Scholastics", "Schoolman"),
        confidence=0.75,
        langs=("eng",),
        note=(
            "Hume's standard English term for the medieval "
            "Aristotelians. Routed to Aquinas as the sole in-corpus "
            "scholastic; downstream verification can broaden."
        ),
    ),
    # Spinoza — Hume cites "the hideous hypothesis" of Spinoza in
    # the Treatise (I.iv.5). Named references are sparse but
    # distinctive.
    AuthorMentionRule(
        name="hume_spinoza",
        target_author="Spinoza",
        target_work="",
        forms=("Spinoza", "Spinozism", "Spinozist", "Spinoza's"),
        confidence=0.8,
        langs=("eng",),
        note=(
            "Hume's critique of substance metaphysics in Treatise "
            "I.iv.5 attacks 'the famed atheist Spinoza' by name."
        ),
    ),
)
