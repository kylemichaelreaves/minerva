"""Canonical play catalogue for the three Greek tragedians.

Single source of truth for play slugs (filesystem directory names) and
display titles (the canonical English Loeb forms used everywhere in
the corpus — Reader headings, sparkline tooltips, refs cite-resolver).

Used by:
- ``perseus/download_perseus_tragedy.py`` to construct destination paths
- ``src/minerva/tei_drama.py`` (via ``parse_dir``) to map a slug back
  to its canonical title at ingest time
- the ingest registry to declare per-corpus paths
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class Play:
    """One play with its filesystem slug and the canonical display title."""

    slug: str
    title: str


# Aeschylus — tlg0085. 7 surviving plays. Trilogy order:
# Persians → Seven Against Thebes → Suppliants → the Oresteia
# (Agamemnon → Libation Bearers → Eumenides) → Prometheus Bound
# (authorship disputed but traditionally part of the corpus).
AESCHYLUS_PLAYS: tuple[Play, ...] = (
    Play("suppliants", "Suppliants"),
    Play("persians", "Persians"),
    Play("prometheus_bound", "Prometheus Bound"),
    Play("seven_against_thebes", "Seven Against Thebes"),
    Play("agamemnon", "Agamemnon"),
    Play("libation_bearers", "Libation Bearers"),
    Play("eumenides", "Eumenides"),
)

# Sophocles — tlg0011. 7 surviving plays. The Theban cycle (Antigone /
# Oedipus Tyrannus / Oedipus at Colonus) wasn't composed as a trilogy
# — the production order was OT → Antigone → Oedipus at Colonus, but
# the dramatic chronology runs OT → Antigone → Oedipus at Colonus too.
# tlg008 (Ichneutae) is a satyr-play fragment — excluded.
SOPHOCLES_PLAYS: tuple[Play, ...] = (
    Play("trachiniae", "Trachiniae"),
    Play("antigone", "Antigone"),
    Play("ajax", "Ajax"),
    Play("oedipus_tyrannus", "Oedipus Tyrannus"),
    Play("electra", "Electra"),
    Play("philoctetes", "Philoctetes"),
    Play("oedipus_at_colonus", "Oedipus at Colonus"),
)

# Euripides — tlg0006. 19 surviving plays. Cyclops is the only complete
# satyr play we have. Rhesus's authorship is disputed but it sits in
# the traditional Euripidean corpus.
EURIPIDES_PLAYS: tuple[Play, ...] = (
    Play("cyclops", "Cyclops"),
    Play("alcestis", "Alcestis"),
    Play("medea", "Medea"),
    Play("heraclidae", "Heraclidae"),
    Play("hippolytus", "Hippolytus"),
    Play("andromache", "Andromache"),
    Play("hecuba", "Hecuba"),
    Play("suppliants", "Suppliants"),
    Play("heracles", "Heracles"),
    Play("ion", "Ion"),
    Play("trojan_women", "Trojan Women"),
    Play("electra", "Electra"),
    Play("iphigenia_in_tauris", "Iphigenia in Tauris"),
    Play("helen", "Helen"),
    Play("phoenician_women", "Phoenician Women"),
    Play("orestes", "Orestes"),
    Play("bacchae", "Bacchae"),
    Play("iphigenia_in_aulis", "Iphigenia in Aulis"),
    Play("rhesus", "Rhesus"),
)


# Corpus slug → (display_name, plays). The corpus slug is the same key
# the CLI's ``--corpus`` arg, the ``Chunk.corpus`` column, and the
# ``AUTHOR_KEYWORDS`` map use everywhere else.
TRAGEDIANS: dict[str, tuple[str, tuple[Play, ...]]] = {
    "aeschylus": ("Aeschylus", AESCHYLUS_PLAYS),
    "sophocles": ("Sophocles", SOPHOCLES_PLAYS),
    "euripides": ("Euripides", EURIPIDES_PLAYS),
}


def find_play(corpus: str, slug: str) -> Play | None:
    """Look up a play by its filesystem slug. Returns ``None`` for
    unknown slugs so the caller can skip stray directories without
    erroring."""

    entry = TRAGEDIANS.get(corpus)
    if entry is None:
        return None
    _, plays = entry
    for p in plays:
        if p.slug == slug:
            return p
    return None
