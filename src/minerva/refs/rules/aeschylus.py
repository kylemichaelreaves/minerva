"""Rules that fire on Aeschylus chunks.

Aeschylus (c. 525–456 BCE) is the earliest of the three tragedians.
His outbound citation surface is narrow because:

* Aeschylus famously called his plays "slices from Homer's banquet"
  (Athenaeus 8.347e) — the *Iliad* and *Odyssey* are the dominant
  source. Trojan-cycle figures saturate the *Oresteia* and *Persians*.
* Hesiod's *Theogony* supplies the Prometheus / Titans cosmology that
  *Prometheus Bound* dramatizes (authorship of which is disputed but
  traditionally part of the corpus).
* No direct name-mentions of Presocratic philosophers — Aeschylus
  predates the heavy philosophical engagement that shows up in
  Euripides.

The rules below are deliberately conservative — the embedding +
LLM verifier passes upgrade the rule-weak signal where the actual
text is doing a real citation rather than a mythological allusion."""

from __future__ import annotations

from . import AuthorMentionRule

RULES = (
    # ── Homer ─────────────────────────────────────────────────────
    # Greek inflections — only the by-name mentions, not "Homeric"
    # references which would over-match.
    AuthorMentionRule(
        name="aeschylus_homer_grc",
        target_author="Homer",
        target_work="",
        forms=("Ὅμηρος", "Ὁμήρου", "Ὅμηρον", "Ὁμήρῳ"),
        confidence=0.7,
        langs=("grc",),
        note=(
            "Aeschylus's debt to Homer is structural — Trojan-cycle "
            "subjects, epic similes, formulaic diction. Direct "
            "name-mentions are rare in the surviving plays; this rule "
            "fires on the (few) explicit references."
        ),
    ),
    AuthorMentionRule(
        name="aeschylus_homer_eng",
        target_author="Homer",
        target_work="",
        forms=("Homer", "Homer's", "Homeric"),
        confidence=0.6,
        langs=("eng",),
        note=(
            "English Smyth translation occasionally adds 'Homeric' as "
            "an interpretive gloss. Lower confidence since Smyth's "
            "running commentary footnotes also use the word."
        ),
    ),
    # ── Hesiod ───────────────────────────────────────────────────
    AuthorMentionRule(
        name="aeschylus_hesiod_grc",
        target_author="Hesiod",
        target_work="",
        forms=("Ἡσίοδος", "Ἡσιόδου", "Ἡσίοδον", "Ἡσιόδῳ"),
        confidence=0.7,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="aeschylus_hesiod_eng",
        target_author="Hesiod",
        target_work="",
        forms=("Hesiod", "Hesiod's"),
        confidence=0.65,
        langs=("eng",),
    ),
)
