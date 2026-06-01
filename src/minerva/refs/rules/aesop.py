"""Rules that fire on Aesop (Babrius / Phaedrus) chunks.

Aesop's fables are pre-philosophical narrative — they don't cite
philosophical predecessors in our corpus. Each fable stands alone,
moral-tagged but unattributed.

Per the [[refs-rules-mandatory-for-new-authors]] memory the file is
still required; the empty RULES tuple is the right shape. The real
work lives in the bidirectional audit — ``hegel_aesop``, ``marx_aesop``,
``plato_aesop``, ``aristotle_aesop`` rules are added to the existing
author files in this same pass (see [[add-aesop-plan]]).

The famous "Hic Rhodus, hic salta" passage that Hegel rendered as
"Hier ist die Rose, hier tanze" in the Preface to *Philosophy of
Right* is the *Boastful Athlete* fable — Babrius 47 / Perry 33.
"""

from __future__ import annotations

from . import Rule

RULES: tuple[Rule, ...] = ()
