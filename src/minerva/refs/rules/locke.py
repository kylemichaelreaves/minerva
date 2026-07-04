"""Rules that fire on Locke chunks.

Locke's two ingested works engage different sets of interlocutors:

* The *Essay Concerning Human Understanding* (1689) — primarily
  epistemology and philosophy of mind. Engages Descartes (the
  innate-ideas critique), Aristotle / "the Schoolmen" (the
  scholastic-logic critique), and the Cambridge Platonists by
  implication. The Essay is also Locke's most-cited work by later
  authors (Hume, Berkeley, Reid), making it a hub in the corpus.

* The *Second Treatise of Government* (1689) — political theory.
  Locke quotes Richard Hooker ("the judicious Hooker") at length,
  argues against Robert Filmer's *Patriarcha* (the whole First
  Treatise is a refutation of Filmer; the Second Treatise inherits
  the polemical context), and engages Hobbes's *Leviathan* on
  sovereignty / the state of nature without naming him.

Cicero is cited occasionally as a natural-law authority.

All rules gate on `langs=("eng",)` — Locke is English-only in our
ingest.
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule, _figures
from .scripture_cite import ScriptureCiteRuleEn

RULES = (
    # ── English scripture cites → KJV. Reasonableness of Christianity
    # is the densest biblical engagement; the Essay scatters cites
    # throughout the chapters on revelation and faith.
    ScriptureCiteRuleEn(name="locke_scripture_cite_en"),
    # Descartes — Locke's central epistemological target in the
    # Essay. The innate-ideas critique in Book I is essentially a
    # reply to Cartesian rationalism.
    AuthorMentionRule(
        name="locke_descartes",
        target_author="Descartes",
        target_work="",
        forms=_figures.DESCARTES_ENG,
        confidence=0.75,
        langs=("eng",),
    ),
    # Hobbes — engaged in the Second Treatise on sovereignty and the
    # state of nature. Less explicit by name than Filmer but the
    # references that DO appear are deliberate.
    AuthorMentionRule(
        name="locke_hobbes",
        target_author="Hobbes",
        target_work="",
        forms=_figures.HOBBES_ENG,
        confidence=0.7,
        langs=("eng",),
    ),
    # Aristotle — both works engage Aristotle. The Essay (Bk IV) on
    # syllogism / scholastic logic; the Second Treatise on natural
    # law inheritance from the Politics.
    AuthorMentionRule(
        name="locke_aristotle",
        target_author="Aristotle",
        target_work="",
        forms=_figures.ARISTOTLE_ENG,
        confidence=0.7,
        langs=("eng",),
    ),
    # Hooker — the "judicious Hooker" Locke quotes at length in
    # the Second Treatise. Out-of-corpus target until Hooker is
    # ingested directly.
    StrongMentionRule(
        name="locke_hooker",
        target_author="Hooker",
        target_work="",
        forms=("Hooker", "judicious Hooker"),
        confidence=0.85,
        langs=("eng",),
        note=(
            "Richard Hooker, *Of the Laws of Ecclesiastical Polity*. "
            "Locke uses the epithet 'the judicious Hooker' specifically "
            "in the Second Treatise."
        ),
    ),
    # Filmer — the explicit target of the First Treatise; named
    # references survive in the Second. Out-of-corpus target.
    StrongMentionRule(
        name="locke_filmer",
        target_author="Filmer",
        target_work="",
        forms=("Filmer", "Sir Robert Filmer", "Patriarcha"),
        confidence=0.9,
        langs=("eng",),
        note=(
            "Robert Filmer, *Patriarcha* (pub. posth. 1680). Locke's "
            "explicit antagonist; the First Treatise is a sustained "
            "refutation. Out-of-corpus target."
        ),
    ),
    # Cicero — natural-law authority cited in the Second Treatise.
    AuthorMentionRule(
        name="locke_cicero",
        target_author="Cicero",
        target_work="",
        forms=("Cicero", "Tully"),
        confidence=0.7,
        langs=("eng",),
        note=("Locke cites Cicero on natural law and natural rights, often via the De Officiis."),
    ),
    # The Schoolmen — same convention Hobbes uses; routed to
    # Aquinas as the in-corpus representative.
    StrongMentionRule(
        name="locke_schoolmen",
        target_author="Aquinas",
        target_work="",
        forms=_figures.AQUINAS_ENG,
        confidence=0.75,
        langs=("eng",),
        note=(
            "Locke's term for the late-medieval Aristotelians, used "
            "polemically in Essay Bk III-IV. Routed to Aquinas as the "
            "in-corpus scholastic; downstream verification can broaden."
        ),
    ),
    # Spinoza — contemporary; Locke references Spinoza occasionally
    # in the Essay's discussion of substance and in the Letters
    # Concerning Toleration.
    AuthorMentionRule(
        name="locke_spinoza",
        target_author="Spinoza",
        target_work="",
        forms=_figures.SPINOZA_ENG,
        confidence=0.85,
        langs=("eng",),
    ),
)
