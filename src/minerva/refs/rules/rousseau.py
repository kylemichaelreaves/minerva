"""Rules that fire on Rousseau chunks.

*Du contrat social* (1762) engages a tight set of named
interlocutors:

* **Hobbes** — the central modern target on sovereignty and the
  state of nature. Rousseau both inherits Hobbes's framework
  (man-as-natural-individual) and rejects his conclusions (the
  natural man is good; the social pact, not absolute sovereignty,
  is the source of legitimacy).
* **Grotius** — Rousseau names *Grotius* repeatedly as the
  preeminent natural-law jurist whose contract theory he is
  refuting (*Le droit de la guerre et de la paix*).
* **Locke** — Rousseau is on Locke's side of the contract-theory
  family but the explicit citations are sparse (Locke is more
  inherited than argued-with).
* **Aristote** — natural-slavery polemic; Livre I, ch. 2.
* **Caligula**, **Pufendorf**, **Barbeyrac**, **Sidney**,
  **Montesquieu** — appear by name. Pufendorf and Barbeyrac get
  rules; Sidney / Caligula are too sparse to warrant their own
  rule in Phase 1.

All rules gate on `langs=("fra",)` — Rousseau is French-only.
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule
from .scripture_cite import ScriptureCiteRuleFr

RULES = (
    # ── French scripture cites → Sacy. Rousseau's biblical engagement
    # is concentrated in the Vicar's Profession of Faith (Émile IV)
    # and scattered through Lettre à Christophe de Beaumont. Expect
    # moderate counts — Émile's biblical critique is dense within
    # that section but the Œuvres overall is lighter than Pascal.
    ScriptureCiteRuleFr(name="rousseau_scripture_cite_fr"),
    # Hobbes — central modern target. Rousseau names him explicitly
    # multiple times in Livres I and IV.
    AuthorMentionRule(
        name="rousseau_hobbes",
        target_author="Hobbes",
        target_work="",
        forms=("Hobbes", "Hobbes's", "Hobbesien", "Hobbesienne", "hobbesien"),
        confidence=0.8,
        langs=("fra",),
    ),
    # Grotius — the preeminent named target of the Contrat's
    # natural-law polemic. Strong rule because any "Grotius"
    # mention in Rousseau is the Hugo Grotius of De jure belli.
    StrongMentionRule(
        name="rousseau_grotius",
        target_author="Grotius",
        target_work="",
        forms=("Grotius", "grotien", "grotienne"),
        confidence=0.9,
        langs=("fra",),
        note=(
            "Hugo Grotius, *De jure belli ac pacis* (1625). Rousseau's "
            "explicit antagonist on natural-law contract theory. "
            "Out-of-corpus target."
        ),
    ),
    # Locke — same contract-theory family but cited more sparsely.
    AuthorMentionRule(
        name="rousseau_locke",
        target_author="Locke",
        target_work="",
        forms=("Locke", "Locke's", "lockéen", "lockéenne"),
        confidence=0.75,
        langs=("fra",),
    ),
    # Aristote — natural-slavery polemic (Livre I ch. 2).
    AuthorMentionRule(
        name="rousseau_aristote",
        target_author="Aristotle",
        target_work="",
        forms=(
            "Aristote",
            "aristotélicien",
            "aristotélicienne",
            "aristotéliciens",
        ),
        confidence=0.7,
        langs=("fra",),
    ),
    # Platon — referenced occasionally on the legislator and on
    # the ideal city.
    AuthorMentionRule(
        name="rousseau_platon",
        target_author="Plato",
        target_work="",
        forms=("Platon", "platonicien", "platonicienne", "platoniciens"),
        confidence=0.65,
        langs=("fra",),
    ),
    # Pufendorf — Samuel von Pufendorf, *De jure naturae et
    # gentium* (1672). Cited alongside Grotius in the natural-law
    # discussions.
    AuthorMentionRule(
        name="rousseau_pufendorf",
        target_author="Pufendorf",
        target_work="",
        forms=("Pufendorf", "Puffendorf"),
        confidence=0.85,
        langs=("fra",),
        note=("Samuel von Pufendorf, the German natural-law jurist. Out-of-corpus target."),
    ),
    # Barbeyrac — Jean Barbeyrac, the translator and commentator
    # who introduced Pufendorf to the French-reading public.
    # Rousseau cites him by name when arguing against the
    # Pufendorf/Grotius tradition.
    AuthorMentionRule(
        name="rousseau_barbeyrac",
        target_author="Barbeyrac",
        target_work="",
        forms=("Barbeyrac",),
        confidence=0.85,
        langs=("fra",),
        note=(
            "Jean Barbeyrac (1674–1744), translator of Pufendorf and Grotius. Out-of-corpus target."
        ),
    ),
    # Montesquieu — *De l'esprit des lois* (1748) is the standing
    # backdrop to Rousseau's discussion of forms of government.
    # Rousseau cites Montesquieu by name in Livres II–III.
    AuthorMentionRule(
        name="rousseau_montesquieu",
        target_author="Montesquieu",
        target_work="",
        forms=("Montesquieu",),
        confidence=0.85,
        langs=("fra",),
        note=(
            "Charles-Louis de Secondat, Baron de Montesquieu. "
            "*L'Esprit des lois* is the principal French political-"
            "theory backdrop Rousseau argues against. Out-of-corpus "
            "target."
        ),
    ),
    # Cicero — Rousseau invokes Cicero on natural law in the
    # Contrat Social and the Discours.
    AuthorMentionRule(
        name="rousseau_ciceron",
        target_author="Cicero",
        target_work="",
        forms=("Cicéron", "Ciceron"),
        confidence=0.85,
        langs=("fra",),
    ),
    # Hume — Rousseau's English protector during his 1766 exile.
    # The famous Hume-Rousseau quarrel makes these references
    # biographically pointed; Rousseau also cites Hume on
    # epistemology in the Confessions and Rêveries.
    AuthorMentionRule(
        name="rousseau_hume",
        target_author="Hume",
        target_work="",
        forms=("Hume",),
        confidence=0.85,
        langs=("fra",),
        note=(
            "David Hume — Rousseau's protector in England (1766) "
            "and the antagonist of the famous Hume-Rousseau quarrel. "
            "Named references are biographically deliberate."
        ),
    ),
)
