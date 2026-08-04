"""Extra names a work answers to, beyond ``works.title`` and the
per-language ``title_local`` on its editions and translations.

Why a third mechanism. ``works.title`` is one string, and for some works
it is not a name any reader uses: Hegel's Phenomenology carries its
translator's surname in the title, so "Phenomenology of Spirit" matches
nothing, and Marx's Kapital is split by volume, so "Das Kapital" matches
nothing either. Those were the two failures left after #194 (#195).

``title_local`` cannot carry these. It holds ONE value per
(work, language) and it is what the reader displays
(``reader/queries.py``), so using it as an alias slot forces a display
change to buy a detection fix — and it still cannot express the
cross-language pairs, where an English work needs to answer to its
German name *and* keep its English one.

So aliases live here, in code, keyed on the NATURAL key
``(author, works.title)`` rather than a work id. That is deliberate:
``works.id`` is a surrogate reassigned by insertion order, and
``index --reset`` reshuffles it (#193 — a spec anchored on edition 58
came to name Homer's Iliad). Keyed on the title, this table is
re-materialized into the DB on every index run and cannot rot.
"""

from __future__ import annotations

# (author, works.title) → the other names that work answers to.
#
# Aliases are for names a reader would actually type. They are NOT for
# translations of the title into every language in the corpus, and not
# for abbreviations — `detect_work` requires every significant token of
# a name to appear in the query, so a short alias is a blunt instrument
# that matches far more than it should.
ALIASES: dict[tuple[str, str], tuple[str, ...]] = {
    # ── Hegel ─────────────────────────────────────────────────────────
    # The two English Phenomenologies bake the translator's surname into
    # `works.title`, so the bare name reaches neither. They are separate
    # `works` rows from the German (a known ingest quirk, documented at
    # glossary_spec.py's translation cross-check), which is why all three
    # need the alias rather than one shared row carrying it.
    ("Hegel", "Phenomenology of Spirit (Pinkard)"): (
        "Phenomenology of Spirit",
        "Phänomenologie des Geistes",
    ),
    ("Hegel", "Phenomenology of Spirit (Inwood)"): (
        "Phenomenology of Spirit",
        "Phänomenologie des Geistes",
    ),
    ("Hegel", "Phänomenologie des Geistes"): ("Phenomenology of Spirit",),
    # The English title is the Cambridge edition's ("Elements of…"); a
    # reader is at least as likely to write the conventional short form.
    ("Hegel", "Elements of the Philosophy of Right"): (
        "Philosophy of Right",
        "Grundlinien der Philosophie des Rechts",
    ),
    ("Hegel", "Grundlinien der Philosophie des Rechts"): (
        "Philosophy of Right",
        "Elements of the Philosophy of Right",
    ),
    ("Hegel", "Science of Logic"): ("Wissenschaft der Logik",),
    ("Hegel", "Wissenschaft der Logik"): ("Science of Logic",),
    # ── Marx ──────────────────────────────────────────────────────────
    # All three Bände answer to the bare title, and that is the correct
    # outcome rather than a collision: #194's fallback judges ambiguity
    # at the corpus level, so three works of one author still resolve
    # `marx`, while `detect_work` returns None and retrieval stays
    # corpus-scoped instead of guessing a volume.
    ("Marx", "Das Kapital, Band I"): ("Das Kapital",),
    ("Marx", "Das Kapital, Band II"): ("Das Kapital",),
    ("Marx", "Das Kapital, Band III"): ("Das Kapital",),
}


def aliases_for(author: str, title: str) -> tuple[str, ...]:
    """Every extra name ``(author, title)`` answers to; empty when none."""

    return ALIASES.get((author, title), ())
