"""Rules that fire on Origen chunks.

Unlike Theognis and Aesop, Origen IS philosophically allusive — the
*Contra Celsum* is structured as a sustained engagement with named
interlocutors (Celsus front and centre, with Plato, Homer, the LXX,
the New Testament threaded throughout).

The Celsus rule is the marquee addition: Celsus's lost *Alēthēs
Logos* survives only as the verbatim quotations Origen embeds and
attacks. The rule fires on Origen's explicit ``ὁ Κέλσος`` / ``φησίν``
introductions plus the English "Celsus says" / "according to Celsus"
patterns. ``reference_targets.notes`` for Celsus points readers back
to the canonical 3.44 women/children/slaves passage that Nietzsche
later reformulates as slave morality.

Plato and Homer rules cover the other two heavily-recurring sources.
The Septuagint / New Testament citations are deferred to the
scripture-cite pass (which handles biblical book.chapter.verse
locators uniformly across the corpus, see
``refs/rules/scripture_cite.py``).

See [[add-origen-celsus-plan]] for the broader bidirectional audit;
Augustine, Aquinas, Hegel, Pascal, and Nietzsche all get ``*_origen``
rules added to their respective rules files in this same pass.
"""

from __future__ import annotations

from . import AuthorMentionRule, Rule

RULES: tuple[Rule, ...] = (
    # ─── Celsus ────────────────────────────────────────────────────
    # The point of the whole work. Origen quotes Celsus verbatim
    # throughout and introduces him by name explicitly — ``ὁ Κέλσος
    # φησίν`` ("Celsus says") is the recurring formula. High
    # confidence; cross-walks to Celsus as an out-of-corpus reference
    # target (no chunks; just a `reference_targets` row).
    AuthorMentionRule(
        name="origen_celsus",
        target_author="Celsus",
        target_work="",
        forms=(
            "Κέλσος",
            "Κέλσου",
            "Κέλσῳ",
            "Κέλσον",
            "Celsus",
            "Celsus's",
            "Celsian",
        ),
        confidence=0.95,
        langs=("grc", "eng"),
        note=(
            "Out-of-corpus. Surviving testimony lives only here in "
            "Contra Celsum; the women/children/slaves passage at "
            "C.Cels. 3.44 is the antecedent of Nietzsche's slave-"
            "morality thesis in the Genealogy of Morals."
        ),
    ),
    # ─── Plato ─────────────────────────────────────────────────────
    # Origen engages Plato repeatedly — both because Celsus is a
    # Middle Platonist who cites Plato approvingly and because
    # Origen wants to reclaim Platonic eschatology for Christianity.
    AuthorMentionRule(
        name="origen_plato",
        target_author="Plato",
        target_work="",
        forms=("Πλάτων", "Πλάτωνος", "Πλάτωνι", "Πλάτωνα", "Plato"),
        confidence=0.88,
        langs=("grc", "eng"),
    ),
    # ─── Homer ─────────────────────────────────────────────────────
    # Celsus quotes Homer as a cultural-authority argument against
    # the Christians; Origen quotes back. Frequent in Books I-IV.
    AuthorMentionRule(
        name="origen_homer",
        target_author="Homer",
        target_work="",
        forms=("Ὅμηρος", "Ὁμήρου", "Ὅμηρον", "Ὁμήρῳ", "Homer", "Homeric"),
        confidence=0.85,
        langs=("grc", "eng"),
    ),
)
