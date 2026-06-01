"""Canonical Aristotle works catalog with per-work source mapping.

Single source of truth for the cross-source Aristotle ingest:

* Perseus ``dltext`` (the existing 9 works) — handled by
  ``perseus/download_perseus_aristotle.py``.
* OpenGreekAndLatin ``First1KGreek`` GitHub mirror — fills in the rest
  of the Greek originals (Categories, De Anima, Physics, biological
  works, Parva Naturalia, etc.). Fetched by
  ``perseus/download_first1kgreek_aristotle.py``.
* Internet Classics Archive (classics.mit.edu) — public-domain English
  translations for most of the canon (Ross, Edghill, Smith, Stocks,
  Beare, Thompson, Forster, Peck, Jowett). Fetched by
  ``perseus/download_ica_aristotle.py``.

Each row pairs the same canonical English title across all available
sources so the term-glossary side gets a single Work row per
Aristotelian text, regardless of which source supplied the Greek and
which supplied the English.

TLG numbering follows OpenGreekAndLatin's ``First1KGreek`` repository,
which uses the official TLG canon numbering for Aristotle (urn
``urn:cts:greekLit:tlg0086.tlgNNN``). The ``perseus_tlg`` column maps
the same work to Perseus's internal numbering when Perseus has it
(used for de-duplication — we don't want two parallel Greek editions
of Nicomachean Ethics, one from each source).
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class AristotleWork:
    """Canonical record for one Aristotelian work.

    Field semantics
    ---------------
    * ``canonical_title`` is what we write into ``works.title``.
      Translations and editions from different sources for the same
      work share this string so the term-glossary system groups them
      under a single Work row.
    * ``first1k_tlg`` — directory name under
      ``OpenGreekAndLatin/First1KGreek/data/tlg0086/``. Empty when
      First1KGreek doesn't carry the work.
    * ``ica_slug`` — URL slug under ``https://classics.mit.edu/Aristotle/``.
      Empty when ICA doesn't carry the work.
    * ``perseus_already_has`` — True when the existing Perseus
      ``dltext`` download script already covers this work. Used by
      the new downloaders to skip the Greek and/or English side so we
      don't ingest two parallel editions of the same text.
    * ``locator`` — citation system for ``works.citation_system``.
      Most Aristotle uses Bekker pagination; a few (Athenian
      Constitution, Poetics) use chapter+section numbering. The
      First1KGreek TEI files carry Bekker page+line markers when
      applicable.
    """

    canonical_title: str
    first1k_tlg: str | None = None
    ica_slug: str | None = None
    perseus_already_has: bool = False
    locator: str = "bekker"  # "bekker" | "paragraph"
    notes: str = ""


# Order roughly follows the canonical Bekker numbering — readers
# familiar with the corpus get a meaningful sort. Three columns are
# what each ingester reads: TLG (Greek source), ICA slug (English
# source), and Perseus-have flag.
ARISTOTLE_WORKS: tuple[AristotleWork, ...] = (
    # ── Organon ───────────────────────────────────────────────────
    AristotleWork(
        canonical_title="Categories",
        first1k_tlg="tlg006",
        ica_slug="categories",
    ),
    AristotleWork(
        canonical_title="On Interpretation",
        first1k_tlg="tlg017",
        ica_slug="interpretation",
    ),
    AristotleWork(
        canonical_title="Prior Analytics",
        first1k_tlg="tlg001",
        ica_slug="prior",
    ),
    AristotleWork(
        canonical_title="Posterior Analytics",
        first1k_tlg=None,
        ica_slug="posterior",
        notes=(
            "Greek not reachable from Perseus canonical-greekLit or "
            "First1KGreek; the latter's tlg034 was removed as 'superfluous' "
            "(see OGL issue #2801). English-only via ICA (G. R. G. Mure). "
            "Sources for the Greek would need a non-Perseus pipeline "
            "(Wikisource Greek or Oxford Translation scans)."
        ),
    ),
    AristotleWork(
        canonical_title="Topics",
        first1k_tlg="tlg044",
        ica_slug="topics",
    ),
    AristotleWork(
        canonical_title="Sophistical Refutations",
        first1k_tlg="tlg040",
        ica_slug="sophist_refut",
    ),
    # ── Physical / cosmological ───────────────────────────────────
    AristotleWork(
        canonical_title="Physics",
        first1k_tlg="tlg031",
        ica_slug="physics",
    ),
    AristotleWork(
        canonical_title="On the Heavens",
        first1k_tlg="tlg005",
        ica_slug="heavens",
    ),
    AristotleWork(
        canonical_title="On Generation and Corruption",
        first1k_tlg="tlg013",
        ica_slug="gener_corr",
    ),
    AristotleWork(
        canonical_title="Meteorology",
        first1k_tlg="tlg026",
        ica_slug="meteorology",
    ),
    # ── On the Soul + Parva Naturalia ─────────────────────────────
    AristotleWork(
        canonical_title="On the Soul",
        first1k_tlg="tlg002",
        ica_slug="soul",
    ),
    AristotleWork(
        canonical_title="On Sense and the Sensible",
        first1k_tlg="tlg041",
        ica_slug="sense",
    ),
    AristotleWork(
        canonical_title="On Memory and Reminiscence",
        first1k_tlg="tlg024",
        ica_slug="memory",
    ),
    AristotleWork(
        canonical_title="On Sleep and Sleeplessness",
        first1k_tlg="tlg042",
        ica_slug="sleep",
    ),
    AristotleWork(
        canonical_title="On Dreams",
        first1k_tlg="tlg016",
        ica_slug="dreams",
    ),
    AristotleWork(
        canonical_title="On Prophesying by Dreams",
        first1k_tlg="tlg008",
        ica_slug="prophesying",
    ),
    AristotleWork(
        canonical_title="On Longevity and Shortness of Life",
        first1k_tlg="tlg020",
        ica_slug="longev_short",
    ),
    AristotleWork(
        canonical_title="On Youth, Old Age, Life and Death",
        first1k_tlg="tlg018",
        ica_slug="youth_old",
    ),
    # ── Biological ────────────────────────────────────────────────
    AristotleWork(
        canonical_title="History of Animals",
        first1k_tlg="tlg014",
        ica_slug="history_anim",
    ),
    AristotleWork(
        canonical_title="Parts of Animals",
        first1k_tlg="tlg030",
        ica_slug="parts_animals",
    ),
    AristotleWork(
        canonical_title="Generation of Animals",
        first1k_tlg="tlg012",
        ica_slug=None,
        notes=(
            "Greek from First1KGreek. Confirmed: ICA's Aristotle browse "
            "page lists 29 works and Generation of Animals is not among "
            "them. Platt's translation is public domain (Oxford Translation "
            "Vol. 5) but only as PDF scans."
        ),
    ),
    AristotleWork(
        canonical_title="Movement of Animals",
        first1k_tlg="tlg021",
        ica_slug="motion_animals",
    ),
    AristotleWork(
        canonical_title="Progression of Animals",
        first1k_tlg="tlg015",
        ica_slug="gait_anim",
    ),
    # ── Ethics, politics, rhetoric, poetics (Perseus already has) ─
    AristotleWork(
        canonical_title="Metaphysics",
        first1k_tlg=None,
        ica_slug=None,
        perseus_already_has=True,
    ),
    AristotleWork(
        canonical_title="Nicomachean Ethics",
        first1k_tlg=None,
        ica_slug=None,
        perseus_already_has=True,
    ),
    AristotleWork(
        canonical_title="Eudemian Ethics",
        first1k_tlg=None,
        ica_slug=None,
        perseus_already_has=True,
    ),
    AristotleWork(
        canonical_title="Politics",
        first1k_tlg=None,
        ica_slug=None,
        perseus_already_has=True,
    ),
    AristotleWork(
        canonical_title="Rhetoric",
        first1k_tlg=None,
        ica_slug=None,
        perseus_already_has=True,
    ),
    AristotleWork(
        canonical_title="Poetics",
        first1k_tlg=None,
        ica_slug=None,
        perseus_already_has=True,
        locator="paragraph",
    ),
    AristotleWork(
        canonical_title="Athenian Constitution",
        first1k_tlg=None,
        ica_slug=None,
        perseus_already_has=True,
        locator="paragraph",
    ),
    AristotleWork(
        canonical_title="On Virtues and Vices",
        first1k_tlg=None,
        ica_slug=None,
        perseus_already_has=True,
        locator="paragraph",
    ),
    AristotleWork(
        canonical_title="Economics",
        first1k_tlg=None,
        ica_slug=None,
        perseus_already_has=True,
    ),
    # ── Disputed / minor (Greek-only — no public-domain English source
    #     we can reach without scraping archive.org PDF scans) ─────
    AristotleWork(
        canonical_title="Magna Moralia",
        first1k_tlg="tlg022",
        ica_slug=None,
        notes=(
            "Greek from First1KGreek. English (Stock, Oxford Translation) "
            "exists in public domain but only as archive.org PDF scans; "
            "out of scope for the cleaner text-mirror pipeline."
        ),
    ),
    AristotleWork(
        canonical_title="Problems",
        first1k_tlg="tlg036",
        ica_slug=None,
        notes=(
            "Greek from First1KGreek. English (Forster) exists in "
            "Oxford Translation Vol. 7 scans; same caveat as Magna Moralia."
        ),
    ),
    AristotleWork(
        canonical_title="Mechanics",
        first1k_tlg="tlg023",
        ica_slug=None,
        notes=(
            "Pseudo-Aristotelian. Greek from First1KGreek. English "
            "(Forster) in Oxford Translation Vol. 6 scans."
        ),
    ),
)


def works_with_first1k() -> tuple[AristotleWork, ...]:
    """Subset that has a First1KGreek TLG directory (Greek source)."""
    return tuple(w for w in ARISTOTLE_WORKS if w.first1k_tlg)


def works_with_ica() -> tuple[AristotleWork, ...]:
    """Subset that has an ICA URL slug (English translation)."""
    return tuple(w for w in ARISTOTLE_WORKS if w.ica_slug)


def by_first1k_tlg(tlg: str) -> AristotleWork | None:
    for w in ARISTOTLE_WORKS:
        if w.first1k_tlg == tlg:
            return w
    return None


def by_ica_slug(slug: str) -> AristotleWork | None:
    for w in ARISTOTLE_WORKS:
        if w.ica_slug == slug:
            return w
    return None
