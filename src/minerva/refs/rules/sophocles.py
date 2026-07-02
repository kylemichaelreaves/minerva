"""Rules that fire on Sophocles chunks.

Sophocles (c. 497–406 BCE) has the narrowest by-name citation surface
of the three tragedians:

* Homer is the unambiguous main source — *Ajax* and *Philoctetes* are
  both Iliad-cycle subjects, and *Odyssey* echoes saturate *Electra*
  and *Oedipus at Colonus*.
* Hesiod is alluded to in the choral material (especially the
  Trachiniae nightingale ode) but rarely named.
* Sophocles does NOT name-drop contemporary tragedians (Aeschylus,
  Euripides). The Frogs evidence (Aristophanes mocking Euripides for
  ridiculing Aeschylus) doesn't extend to Sophocles. Inter-tragedian
  intertextuality is handled by the embedding-verify pass, not by
  name-mention rules.

Given how little name-citation Sophocles does explicitly, this module
is genuinely thin. That's the empirical reality, not a gap."""

from __future__ import annotations

from . import AuthorMentionRule

RULES = (
    # ── Homer ─────────────────────────────────────────────────────
    AuthorMentionRule(
        name="sophocles_homer_grc",
        target_author="Homer",
        target_work="",
        forms=("Ὅμηρος", "Ὁμήρου", "Ὅμηρον", "Ὁμήρῳ"),
        confidence=0.7,
        langs=("grc",),
        note=(
            "Sophoclean tragedy is steeped in Homer (Ajax, Philoctetes, "
            "the Iliad cycle); explicit name-mentions are rare and "
            "the LLM verifier filters mythological-allusion noise."
        ),
    ),
    AuthorMentionRule(
        name="sophocles_homer_eng",
        target_author="Homer",
        target_work="",
        forms=("Homer", "Homer's", "Homeric"),
        confidence=0.6,
        langs=("eng",),
    ),
    # ── Hesiod ───────────────────────────────────────────────────
    AuthorMentionRule(
        name="sophocles_hesiod_grc",
        target_author="Hesiod",
        target_work="",
        forms=("Ἡσίοδος", "Ἡσιόδου", "Ἡσίοδον", "Ἡσιόδῳ"),
        confidence=0.6,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="sophocles_hesiod_eng",
        target_author="Hesiod",
        target_work="",
        forms=("Hesiod", "Hesiod's"),
        confidence=0.55,
        langs=("eng",),
    ),
)
