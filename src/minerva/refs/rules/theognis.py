"""Rules that fire on Theognis chunks.

Theognis of Megara (6th c. BCE) is a pre-philosophical elegiac poet —
he doesn't cite philosophical interlocutors in our corpus. The
Theognidea's references are entirely to mythological figures (Apollo,
Athena) and to a few aristocratic addressees (Cyrnus, Simonides as a
contemporary). None of those map to in-corpus targets we'd want
auto-linked.

Per the [[refs-rules-mandatory-for-new-authors]] memory the file is
still required; the empty RULES tuple is the right shape for a
pre-philosophical corpus-leaf author. The bidirectional audit work
lives in the OTHER files (``nietzsche.py`` already ships
``nietzsche_theognis``; ``plato.py`` and ``aristotle.py`` get
``plato_theognis`` / ``aristotle_theognis`` added in this same pass —
see [[add-theognis-plan]]).
"""

from __future__ import annotations

from . import Rule

RULES: tuple[Rule, ...] = ()
