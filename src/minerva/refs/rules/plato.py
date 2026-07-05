"""Rules that fire on Plato chunks.

Most of Plato's outbound citation traffic is to Homer — the *Republic*,
*Ion*, *Phaedrus*, and *Apology* all quote and discuss Homer
extensively, often by name (Ὅμηρος / "Homer"). A smaller stream
targets Hesiod, Pindar, Aeschylus, Sophocles, and earlier
philosophers (Heraclitus, Parmenides, Anaxagoras); these are
out-of-corpus for now and resolved against `reference_targets`
rows that `ensure_target` will auto-create.

No "Philosophus"-style strong-mention conventions in Plato's prose.
All rules are AuthorMentionRule with confidence 0.55–0.70 — the
LLM verifier handles disambiguation (especially separating Homer-
the-poet citations from incidental name-drops about Homeric
characters).

Both Greek (Unicode polytonic) and English forms are listed because
Plato's English translations cite the same figures.
"""

from __future__ import annotations

from . import AuthorMentionRule, _figures

RULES = (
    # ── Homer ─────────────────────────────────────────────────────
    AuthorMentionRule(
        name="plato_homer_grc",
        target_author="Homer",
        target_work="",
        forms=_figures.HOMER_GRC,
        confidence=0.7,
        langs=("grc",),
        note=(
            "Plato cites Homer constantly — Republic 363a-d, 364c-e, "
            "377a-392c, 595a-608b on the poets; Ion is a sustained "
            "engagement with Homeric rhapsody."
        ),
    ),
    AuthorMentionRule(
        name="plato_homer_eng",
        target_author="Homer",
        target_work="",
        forms=_figures.HOMER_ENG,
        confidence=0.7,
        langs=("eng",),
    ),
    # ── Hesiod (out-of-corpus) ────────────────────────────────────
    AuthorMentionRule(
        name="plato_hesiod_grc",
        target_author="Hesiod",
        target_work="",
        forms=_figures.HESIOD_GRC,
        confidence=0.65,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="plato_hesiod_eng",
        target_author="Hesiod",
        target_work="",
        forms=_figures.HESIOD_ENG,
        confidence=0.65,
        langs=("eng",),
    ),
    # ── Heraclitus (out-of-corpus) ────────────────────────────────
    AuthorMentionRule(
        name="plato_heraclitus_grc",
        target_author="Heraclitus",
        target_work="",
        forms=_figures.HERACLITUS_GRC,
        confidence=0.7,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="plato_heraclitus_eng",
        target_author="Heraclitus",
        target_work="",
        forms=_figures.HERACLITUS_ENG,
        confidence=0.7,
        langs=("eng",),
    ),
    # ── Parmenides (out-of-corpus, also a dialogue title) ─────────
    AuthorMentionRule(
        name="plato_parmenides_grc",
        target_author="Parmenides",
        target_work="",
        forms=_figures.PARMENIDES_GRC,
        confidence=0.55,
        langs=("grc",),
        note=(
            "Low confidence because 'Parmenides' is also the dialogue "
            "title; the LLM stage filters out the self-references."
        ),
    ),
    # ── Anaxagoras (out-of-corpus) ────────────────────────────────
    AuthorMentionRule(
        name="plato_anaxagoras_grc",
        target_author="Anaxagoras",
        target_work="",
        forms=_figures.ANAXAGORAS_GRC,
        confidence=0.7,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="plato_anaxagoras_eng",
        target_author="Anaxagoras",
        target_work="",
        forms=_figures.ANAXAGORAS_ENG,
        confidence=0.7,
        langs=("eng",),
    ),
    # ── Pythagoras (out-of-corpus) ────────────────────────────────
    AuthorMentionRule(
        name="plato_pythagoras_grc",
        target_author="Pythagoras",
        target_work="",
        forms=_figures.PYTHAGORAS_GRC,
        confidence=0.6,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="plato_pythagoras_eng",
        target_author="Pythagoras",
        target_work="",
        forms=_figures.PYTHAGORAS_ENG,
        confidence=0.6,
        langs=("eng",),
    ),
    # ── Aeschylus ─────────────────────────────────────────────────
    # Republic Bk II–III cites tragedy as part of the censorship
    # discussion; Symposium 188c and Republic 361b–c quote Aeschylus
    # by name.
    AuthorMentionRule(
        name="plato_aeschylus_grc",
        target_author="Aeschylus",
        target_work="",
        forms=_figures.AESCHYLUS_GRC,
        confidence=0.7,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="plato_aeschylus_eng",
        target_author="Aeschylus",
        target_work="",
        forms=_figures.AESCHYLUS_ENG,
        confidence=0.7,
        langs=("eng",),
    ),
    # ── Sophocles ─────────────────────────────────────────────────
    # Republic Bk I opens with the famous Sophocles-on-old-age
    # anecdote (329b-c) — "no longer the master of a savage tyrant."
    AuthorMentionRule(
        name="plato_sophocles_grc",
        target_author="Sophocles",
        target_work="",
        forms=_figures.SOPHOCLES_GRC,
        confidence=0.7,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="plato_sophocles_eng",
        target_author="Sophocles",
        target_work="",
        forms=_figures.SOPHOCLES_ENG,
        confidence=0.7,
        langs=("eng",),
    ),
    # ── Euripides ─────────────────────────────────────────────────
    # Symposium 177a, Phaedo 102d, Republic Bk VIII; the Apology
    # alludes to Euripides without naming him (caught by the
    # embed-verify pass instead).
    AuthorMentionRule(
        name="plato_euripides_grc",
        target_author="Euripides",
        target_work="",
        forms=_figures.EURIPIDES_GRC,
        confidence=0.7,
        langs=("grc",),
    ),
    AuthorMentionRule(
        name="plato_euripides_eng",
        target_author="Euripides",
        target_work="",
        forms=_figures.EURIPIDES_ENG,
        confidence=0.7,
        langs=("eng",),
    ),
    # Theognis — Plato cites Theognis in *Meno* 95d-96a (the "good
    # men come from good men" elegy) and *Laws* I 630a. Both passages
    # name Theognis explicitly.
    AuthorMentionRule(
        name="plato_theognis",
        target_author="Theognis",
        target_work="",
        forms=_figures.THEOGNIS_GRC,
        confidence=0.92,
        langs=("grc",),
        note="Meno 95d-96a + Laws I 630a name Theognis directly.",
    ),
    AuthorMentionRule(
        name="plato_theognis_eng",
        target_author="Theognis",
        target_work="",
        forms=_figures.THEOGNIS_ENG,
        confidence=0.9,
        langs=("eng",),
    ),
    # Aesop — *Phaedo* 60c-61b: Socrates in prison versifies Aesop.
    AuthorMentionRule(
        name="plato_aesop",
        target_author="Aesop",
        target_work="",
        forms=("Αἴσωπος", "Αἰσώπου", "Αἰσώπῳ", "Αἴσωπον", "Αἰσώπεια"),
        confidence=0.9,
        langs=("grc",),
        note="Phaedo 60c-61b: Socrates in prison versifies Aesop's fables.",
    ),
    AuthorMentionRule(
        name="plato_aesop_eng",
        target_author="Aesop",
        target_work="",
        forms=("Aesop", "Aesopic", "Aesopian"),
        confidence=0.88,
        langs=("eng",),
    ),
)
