"""Rules that fire on Euripides chunks.

Euripides (c. 480–406 BCE) has the broadest by-name citation surface
of the three tragedians, because:

* Like the others, he uses Homer and Hesiod as mythological source.
* Unlike them, he engages contemporary philosophy openly. Ancient
  testimony (Diogenes Laertius 2.10, Aulus Gellius 15.20) makes him
  a student of Anaxagoras and a friend of Protagoras; Plato's
  *Apology* groups Euripides with the sophists in popular perception.
  Philosophical fragments and Anaxagorean cosmology surface across
  *Trojan Women*, *Bacchae*, *Helen*.
* Euripides does name predecessors and contemporary tragedians on
  occasion — far more than Aeschylus / Sophocles, who almost never
  do.

The Anaxagoras / Protagoras rules carry lower confidence because the
context can be either a citation or a critical caricature (the
*Bacchae*'s "Pentheus as rationalist" arc is in dialogue with sophistic
thought without naming individuals). The LLM verifier sorts these out."""

from __future__ import annotations

from . import AuthorMentionRule

RULES = (
    # ── Homer ─────────────────────────────────────────────────────
    AuthorMentionRule(
        name="euripides_homer_grc",
        target_author="Homer",
        target_work="",
        forms=("Ὅμηρος", "Ὁμήρου", "Ὅμηρον", "Ὁμήρῳ"),
        confidence=0.7,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="euripides_homer_eng",
        target_author="Homer",
        target_work="",
        forms=("Homer", "Homer's", "Homeric"),
        confidence=0.6,
        langs=("eng",),
    ),
    # ── Hesiod ───────────────────────────────────────────────────
    AuthorMentionRule(
        name="euripides_hesiod_grc",
        target_author="Hesiod",
        target_work="",
        forms=("Ἡσίοδος", "Ἡσιόδου", "Ἡσίοδον", "Ἡσιόδῳ"),
        confidence=0.65,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="euripides_hesiod_eng",
        target_author="Hesiod",
        target_work="",
        forms=("Hesiod", "Hesiod's"),
        confidence=0.6,
        langs=("eng",),
    ),
    # ── Anaxagoras (his teacher per ancient testimony) ───────────
    AuthorMentionRule(
        name="euripides_anaxagoras_grc",
        target_author="Anaxagoras",
        target_work="",
        forms=("Ἀναξαγόρας", "Ἀναξαγόρου", "Ἀναξαγόραν", "Ἀναξαγόρᾳ"),
        confidence=0.65,
        langs=("grc",),
        note=(
            "Direct name-mentions of Anaxagoras in extant Euripides "
            "are very rare; the Anaxagorean cosmology surfaces "
            "thematically and the embed-verify pass catches the "
            "unnamed cases."
        ),
    ),
    AuthorMentionRule(
        name="euripides_anaxagoras_eng",
        target_author="Anaxagoras",
        target_work="",
        forms=("Anaxagoras",),
        confidence=0.6,
        langs=("eng",),
    ),
    # ── Protagoras (sophistic milieu) ────────────────────────────
    AuthorMentionRule(
        name="euripides_protagoras_grc",
        target_author="Protagoras",
        target_work="",
        forms=("Πρωταγόρας", "Πρωταγόρου", "Πρωταγόραν", "Πρωταγόρᾳ"),
        confidence=0.55,
        langs=("grc",),
        note=(
            "Out-of-corpus target; ensure_target creates a stub. The "
            "LLM verifier handles the rhetorical-question case where "
            "Hecuba or Pentheus dialectic plays the sophistic move "
            "without naming Protagoras."
        ),
    ),
    AuthorMentionRule(
        name="euripides_protagoras_eng",
        target_author="Protagoras",
        target_work="",
        forms=("Protagoras",),
        confidence=0.55,
        langs=("eng",),
    ),
    # ── Aeschylus (intra-tragedian — rare but attested) ──────────
    # Euripides' *Frogs* fame — Aristophanes' parodic confrontation
    # of Euripides with Aeschylus — depends on real intertextual
    # engagement. Name-mentions in Euripides himself are rare; this
    # is mostly a placeholder so the bidirectional graph isn't empty.
    AuthorMentionRule(
        name="euripides_aeschylus_grc",
        target_author="Aeschylus",
        target_work="",
        forms=("Αἰσχύλος", "Αἰσχύλου", "Αἰσχύλον", "Αἰσχύλῳ"),
        confidence=0.55,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="euripides_aeschylus_eng",
        target_author="Aeschylus",
        target_work="",
        forms=("Aeschylus", "Aeschylean"),
        confidence=0.55,
        langs=("eng",),
    ),
)
