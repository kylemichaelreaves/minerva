"""Rules that fire on Lucretius chunks.

Lucretius's *De Rerum Natura* names a tight cluster of philosophical
predecessors. The canonical four are explicitly invoked by name:

  * **Epicurus** — Lucretius's master and the explicit hero of the
    poem. Named directly + via the "Graius homo" periphrasis in
    Book I (lines 62-79). Strong rule.
  * **Democritus** — atomism's other founder; named multiple times.
  * **Empedocles** — DRN I.716ff praises Empedocles by name as
    Sicilian / Acragantine philosopher.
  * **Heraclitus** — DRN I.638ff names "Heraclitus the Obscure"
    pejoratively.

Plus secondary mentions: Anaxagoras (DRN I.830ff, the homoeomeria
critique), Ennius (the Roman poet, DRN I.117ff).

All rules language-gated to both Latin (Perseus original) and
English (the Munro / Leonard PG translations).
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule

RULES = (
    # Epicurus — Lucretius's hero. The strong rule fires on both
    # the direct name (Latin: Epicurus / Epicuri / Epicurum; English:
    # Epicurus / Epicurean) and on the explicit periphrases Lucretius
    # uses in lieu of naming (Graius homo, dux noster).
    StrongMentionRule(
        name="lucretius_epicurus",
        target_author="Epicurus",
        target_work="",
        forms=(
            "Epicurus",
            "Epicuri",
            "Epicurum",
            "Epicuro",
            "Epicurean",
            "Epicureans",
            "Epicurean",
            "Graius homo",  # the famous DRN I.66 periphrasis
        ),
        confidence=0.95,
        langs=("lat", "eng"),
        note=(
            "Epicurus is the explicit hero of De Rerum Natura — "
            "every named reference is to him without ambiguity. "
            "Out-of-corpus target."
        ),
    ),
    AuthorMentionRule(
        name="lucretius_democritus",
        target_author="Democritus",
        target_work="",
        forms=("Democritus", "Democriti", "Democritum"),
        confidence=0.85,
        langs=("lat", "eng"),
    ),
    AuthorMentionRule(
        name="lucretius_empedocles",
        target_author="Empedocles",
        target_work="",
        forms=("Empedocles", "Empedoclis", "Empedoclem"),
        confidence=0.9,
        langs=("lat", "eng"),
        note="DRN I.716ff explicitly praises Empedocles by name.",
    ),
    AuthorMentionRule(
        name="lucretius_heraclitus",
        target_author="Heraclitus",
        target_work="",
        forms=("Heraclitus", "Heracliti", "Heraclitum", "Heracliteans"),
        confidence=0.9,
        langs=("lat", "eng"),
        note="DRN I.638ff pejorative reference to 'Heraclitus the Obscure'.",
    ),
    AuthorMentionRule(
        name="lucretius_anaxagoras",
        target_author="Anaxagoras",
        target_work="",
        forms=("Anaxagoras", "Anaxagorae", "Anaxagoram"),
        confidence=0.85,
        langs=("lat", "eng"),
        note="DRN I.830ff homoeomeria critique.",
    ),
)
