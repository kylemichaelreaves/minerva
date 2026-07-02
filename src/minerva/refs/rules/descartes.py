"""Rules that fire on Descartes chunks.

Descartes is famously citation-averse — he presents the Meditations
as starting from nothing but the natural light. The audit counts
(2026-07, LIKE-matches over 3,312 chunks) bear that out, but the few
names he does use are load-bearing:

* **Aristotle (8)** — "Aristote" and the school ("péripatéticiens",
  "l'École") stand for the scholastic physics the Principes replace.
* **Plato (9)** — usually paired with Aristotle as the two ancient
  authorities.
* **Augustine (6)** — the cogito parallel Arnauld presses in the
  Fourth Objections; Descartes concedes it in the Replies.
* **Aquinas ("saint Thomas", 6)** — the Third Meditation's causal
  proof and the O&R discussions of God's existence engage him
  directly.
* **Socrates (3)** — routed to Plato (the corpus host).
* **Archimedes (5)** — the fixed-point simile opening Meditation II;
  out-of-corpus target.
* **Scripture** — sparse but real: the Replies quote Exodus's "ego
  sum qui sum" / Genesis; both French and Latin cite shapes occur
  (the corpus holds Latin originals AND French translations,
  including the Objections & Réponses).

The Objections chunks (block_type='objection', by Caterus / Hobbes /
Arnauld / Gassendi et al.) dispatch through this module too — their
source author is the Descartes corpus even though the voice is the
objector's. That's fine: an objection citing "saint Augustin" is
still a real cross-reference anchored at that chunk, and the reader's
citation label already attributes the voice correctly.
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule
from .scripture_cite import ScriptureCiteRule, ScriptureCiteRuleFr

RULES = (
    # ── Scripture: Latin cites in the originals, French in the
    # translations / Objections & Réponses.
    ScriptureCiteRule(name="descartes_scripture_cite_lat"),
    ScriptureCiteRuleFr(name="descartes_scripture_cite_fr"),
    # Aristotle — named directly and via the school. In Descartes's
    # polemical context "péripatéticiens" / "l'École" is a reference
    # to Aristotelian physics, not a loose adjective.
    AuthorMentionRule(
        name="descartes_aristote",
        target_author="Aristotle",
        target_work="",
        forms=(
            "Aristote",
            "Aristoteles",
            "Aristotelem",
            "péripatéticien",
            "péripatéticiens",
            "aristotélicien",
        ),
        confidence=0.8,
        langs=("fra", "lat"),
    ),
    AuthorMentionRule(
        name="descartes_platon",
        target_author="Plato",
        target_work="",
        forms=("Platon", "Plato", "Platonem", "platonicien", "platoniciens"),
        confidence=0.75,
        langs=("fra", "lat"),
    ),
    # Socrates → Plato (corpus host for the Socratic corpus).
    AuthorMentionRule(
        name="descartes_socrate",
        target_author="Plato",
        target_work="",
        forms=("Socrate", "Socratem", "Socrates"),
        confidence=0.6,
        langs=("fra", "lat"),
    ),
    # Augustine — the famous cogito precedent (Civ. Dei XI.26)
    # Arnauld raises in the Fourth Objections. Strong: "saint
    # Augustin" in this corpus is never anyone else.
    StrongMentionRule(
        name="descartes_augustin",
        target_author="Augustine",
        target_work="",
        forms=("saint Augustin", "S. Augustin", "Augustin", "Augustinus", "Augustini"),
        confidence=0.88,
        langs=("fra", "lat"),
        note="Arnauld's Fourth Objections press the Augustine cogito "
        "parallel; Descartes's Replies engage it directly.",
    ),
    # Aquinas — engaged by name in the Third Meditation discussions
    # and the Objections & Réponses on the proofs of God.
    StrongMentionRule(
        name="descartes_saint_thomas",
        target_author="Aquinas",
        target_work="",
        forms=("saint Thomas", "S. Thomas", "sanctus Thomas", "divus Thomas"),
        confidence=0.85,
        langs=("fra", "lat"),
    ),
    # Archimedes — the Meditation II fixed-point simile. Out-of-corpus
    # target; lands in reference_targets.
    AuthorMentionRule(
        name="descartes_archimede",
        target_author="Archimedes",
        target_work="",
        forms=("Archimède", "Archimedes", "Archimede"),
        confidence=0.8,
        langs=("fra", "lat"),
    ),
    # Epicurus — named in the Objections & Réponses discussions of
    # atomism and the senses.
    AuthorMentionRule(
        name="descartes_epicure",
        target_author="Epicurus",
        target_work="",
        forms=("Épicure", "Epicure", "Epicurus", "épicurien", "épicuriens"),
        confidence=0.7,
        langs=("fra", "lat"),
    ),
)
