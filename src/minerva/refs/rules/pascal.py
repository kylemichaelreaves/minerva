"""Rules that fire on Pascal chunks.

Pascal's principal interlocutors in the *Pensées*:

* **Augustine** — the Jansenist framework Pascal works within is
  thoroughly Augustinian; Pascal cites *saint Augustin* by name as
  the highest authority on grace, original sin, and the divided
  will. This is the biggest single cross-author relationship in
  the corpus for Pascal.
* **Descartes** — the *Pensées* fragments on the cogito and on
  proof-by-reason engage Cartesian rationalism directly ("Descartes,
  inutile et incertain"). Pascal's *physique* essays in earlier
  collections also reply to Descartes on the vacuum.
* **Montaigne** — Pascal's primary modern interlocutor; the
  *Pensées* fragments on the human condition, custom, and
  scepticism read as a sustained reply to Montaigne's *Essais*.
* **Aristotle** and **Plato** — cited less often but explicitly,
  usually in the context of philosophical pretensions Pascal is
  about to deflate.
* The **Jesuits** (via *Lettres provinciales*) are Pascal's
  polemical target but not an in-corpus author; we don't route
  them anywhere.

All rules are French-only (`langs=("fra",)`) since Pascal is
ingested only in the original French. Latin and English forms
are not in our ingest of the *Pensées*.
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule, _figures
from .scripture_cite import ScriptureCiteRuleFr

RULES = (
    # ── French scripture cites → Sacy (the Jansenist Port-Royal
    # translation Pascal cites). Pensées is densely biblical — both
    # explicit cites and unattributed allusions. Pascal mixes French
    # and Latin abbrevs ("Rom. 1, 18" alongside "Romanos 1:18"); the
    # rule tolerates both separators.
    ScriptureCiteRuleFr(name="pascal_scripture_cite_fr"),
    # Augustine — Pascal's central theological authority. Strong
    # rule because the references are explicit and the Jansenist /
    # Augustinian framework makes "saint Augustin" essentially
    # definitional in any passage on grace, fall, or will.
    StrongMentionRule(
        name="pascal_augustin",
        target_author="Augustine",
        target_work="",
        forms=(
            "Augustin",
            "saint Augustin",
            "S. Augustin",
            "Augustinien",
            "Augustinienne",
            "augustinien",
            "augustinienne",
        ),
        confidence=0.9,
        langs=("fra",),
        note=(
            "Pascal cites Augustine as the highest patristic "
            "authority — both directly and via the Jansenist "
            "framework of *De gratia et libero arbitrio*."
        ),
    ),
    # Descartes — explicitly polemicized in several Pensées
    # fragments ("Descartes inutile et incertain"). Cartesian as
    # an adjective is unambiguous in Pascal's French.
    AuthorMentionRule(
        name="pascal_descartes",
        target_author="Descartes",
        target_work="",
        forms=(
            "Descartes",
            "Cartésien",
            "Cartésienne",
            "Cartésiens",
            "Cartésiennes",
            "cartésien",
            "cartésienne",
        ),
        confidence=0.75,
        langs=("fra",),
    ),
    # Montaigne — Pascal's primary modern interlocutor in the
    # Pensées. The Pensées fragments on l'homme / condition
    # humaine essentially commentary on the Essais.
    AuthorMentionRule(
        name="pascal_montaigne",
        target_author="Montaigne",
        target_work="",
        forms=("Montaigne",),
        confidence=0.7,
        langs=("fra",),
        note="Pascal's *Pensées* engages Montaigne throughout.",
    ),
    # Plato — referenced in the L'Esprit géométrique tradition
    # and as part of the philosophical authorities Pascal critiques.
    AuthorMentionRule(
        name="pascal_plato",
        target_author="Plato",
        target_work="",
        forms=_figures.PLATO_FRA,
        confidence=0.65,
        langs=("fra",),
    ),
    # Aristotle — the scholastic Aristotle Pascal is often
    # implicitly arguing against ("ils ont mis tout leur soin à
    # savoir Aristote").
    AuthorMentionRule(
        name="pascal_aristote",
        target_author="Aristotle",
        target_work="",
        forms=(
            "Aristote",
            "aristotélicien",
            "aristotélicienne",
            "aristotéliciens",
            "péripatéticien",
            "péripatéticiens",
        ),
        confidence=0.7,
        langs=("fra",),
    ),
    # Epictetus — Pascal's "Entretien avec M. de Sacy sur Épictète
    # et Montaigne" pairs Epictetus and Montaigne as the two great
    # representatives of pagan ethics. Strong rule.
    StrongMentionRule(
        name="pascal_epictete",
        target_author="Epictetus",
        target_work="",
        forms=("Épictète", "Epictète", "Épictete"),
        confidence=0.9,
        langs=("fra",),
        note=(
            "Pascal's 'Entretien sur Épictète et Montaigne' establishes "
            "Epictetus as one of Pascal's two principal pagan-ethics "
            "interlocutors."
        ),
    ),
    # Cicero — Pascal references Cicero in the Pensées, often via
    # the French form "Cicéron".
    AuthorMentionRule(
        name="pascal_ciceron",
        target_author="Cicero",
        target_work="",
        forms=_figures.CICERO_FRA,
        confidence=0.85,
        langs=("fra",),
    ),
    # Origen — the *Pensées* cite the Church Fathers occasionally for
    # apologetic / prophecy / miracle arguments. Origen is named in a
    # handful of fragments; the French form is "Origène".
    AuthorMentionRule(
        name="pascal_origene",
        target_author="Origen",
        target_work="",
        forms=("Origène", "Origenes", "Origen"),
        confidence=0.75,
        langs=("fra",),
    ),
)
