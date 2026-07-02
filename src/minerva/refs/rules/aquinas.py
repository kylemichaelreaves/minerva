"""Rules that fire on Aquinas chunks.

Most distinctive is the Aquinas "Philosophus" convention — in
practice every occurrence of *Philosophus* (and its Latin oblique
forms) in Aquinas's writings refers to Aristotle. Scholarly editions
treat this as definitional, not interpretive, so the rule fires at
high confidence (`rule_strong`, confidence 0.95) without further
disambiguation. Same logic for the rarer "Commentator" → Averroes.

Lower-confidence rules fire for explicit name mentions of other
authors (Plato, Augustine, Aristoteles when spelled out, Boethius,
Avicenna). These mention Plato et al. in oblique forms (Plato /
Platonis / Platonem / Platone) since Latin scholastic prose declines
the names.

A separate structural rule (:class:`StructuralCommentaryRule`)
handles the four Aristotle commentaries (Ethics, Metaphysics,
Physics, De anima). Every lectio in commentary lib. L is, by
definition, commentary on Aristotle book L of the corresponding
work — so every commentary chunk gets a high-confidence
``comments_on`` cross-reference whose target is the matching
Aristotle work at the book level.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from . import AuthorMentionRule, Candidate, ChunkInfo, StrongMentionRule
from .scripture_cite import FormulaicQuoteRule, ScriptureCiteRule

# ──────────────────────────────────────────────────────────────────
# Structural commentary rule
# ──────────────────────────────────────────────────────────────────

# Map commentary work title → Aristotle target work title (exact
# match against the `works.title` column for the in-corpus Aristotle
# editions, both Greek and English).
_COMMENTARY_TARGETS: dict[str, str] = {
    "Sententia libri Ethicorum": "Nicomachean Ethics",
    "Sententia libri Metaphysicae": "Metaphysics",
    "In libros Physicorum": "Physics",
    "Sentencia libri De anima": "On the Soul",
}

# `Sent. Ethic., lib. 3, lect. 14` → captures lib=3.
# `Sent. Metaphys., pr.` → no lib match → emitted with locator=None.
_SECTION_LIB_RE = re.compile(r"\blib\.\s*(\d+)", re.IGNORECASE)


def _roman(n: int) -> str:
    """Tiny Roman-numeral converter for 1..20 (commentary books cap
    at 12 for Metaphysics)."""

    if n <= 0 or n > 20:
        return str(n)
    table = [
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    out: list[str] = []
    for value, sym in table:
        while n >= value:
            out.append(sym)
            n -= value
    return "".join(out)


@dataclass(frozen=True)
class StructuralCommentaryRule:
    """Emits one ``comments_on`` cross-reference per commentary chunk.

    Fires on Aquinas chunks whose ``work`` is one of the four major
    Aristotle commentaries. The target is the corresponding Aristotle
    work, with the book locator parsed from the chunk's section
    label (e.g. ``Sent. Ethic., lib. 3, lect. 14`` → target locator
    ``"III"``). Prooemium chunks (``Sent. Metaphys., pr.``) emit a
    work-level reference with locator=None.

    Confidence is 0.95 — structurally, every commentary chunk is
    commentary on the corresponding Aristotle passage. The only
    ambiguity is at the lectio-to-Bekker level, which we don't
    resolve here (book-level is sufficient to thread the corpus).
    """

    name: str = "aquinas_structural_commentary"

    def scan(self, chunk: ChunkInfo) -> Iterable[Candidate]:
        target_work = _COMMENTARY_TARGETS.get(chunk.work)
        if target_work is None:
            return
        if chunk.lang != "lat":
            return
        # Book locator from section. Missing = prooemium → locator stays None.
        locator: str | None = None
        if chunk.section:
            m = _SECTION_LIB_RE.search(chunk.section)
            if m:
                locator = _roman(int(m.group(1)))
        yield Candidate(
            source_chunk_id=chunk.chunk_id,
            source_span_start=None,
            source_span_end=None,
            source_form_snapshot=chunk.work,
            target_author="Aristotle",
            target_work=target_work,
            target_locator=locator,
            reference_type="comments_on",
            confidence=0.95,
            source_method="rule_strong",
            note=(
                "Structural — every chunk of the commentary is, by "
                "definition, commentary on the corresponding book of "
                f"Aristotle's {target_work}."
            ),
        )


RULES = (
    # ── structural rule: every commentary chunk → its Aristotle source
    StructuralCommentaryRule(),
    # ── scripture-cite rule: <BookAbbrev>. <chap>-<verse> → Vulgate
    # verse. Generic by design — Augustine can reuse it once that
    # source's cite conventions are surveyed. The chunk binder in
    # `insert_candidate` resolves verse-level targets to the actual
    # Vulgate chunk_id at insert time, no embed/llm verify needed.
    ScriptureCiteRule(),
    # ── formulaic-quote rule: introducer-phrase + colon + quoted
    # verse text, no chapter:verse locator. The Psalm number is
    # implicit in the quoted text; embed-verify Pass A binds the
    # quoted_phrase to the matching Vulgate Psalm chunk by cosine
    # similarity. Survey showed ~59 such cites in Aquinas; Apostolus
    # / Augustinus formulae are out of scope today (Aquinas's
    # "Apostolus" target spans 13 Pauline epistles which would
    # require a cross-work cosine search beyond Pass A's single-work
    # scope).
    FormulaicQuoteRule(
        name="aquinas_psalm_quote",
        target_author="Vulgate",
        target_work="Psalms",
        introducer_patterns=(
            r"in\s+Psalmo",
            r"Psalmus",
            r"Psalmi",
            r"Psalmista",
            r"ait\s+Psalmista",
            r"dicit\s+Psalmista",
            r"sicut\s+illud\s+Psalmi",
            r"secundum\s+illud\s+Psalmi",
        ),
    ),
    # ── strong rules (rule_strong, confidence ~0.95) ─────────────
    StrongMentionRule(
        name="aquinas_philosophus",
        target_author="Aristotle",
        target_work="",
        forms=(
            "Philosophus",
            "Philosophi",  # genitive: "ut Philosophi sententia"
            "Philosopho",  # dative / ablative
            "Philosophum",  # accusative
        ),
        confidence=0.95,
        langs=("lat",),
        note=(
            "Aquinas's 'Philosophus' convention. Throughout the corpus, "
            "every unqualified 'the Philosopher' is Aristotle. Strong by "
            "design — the convention is editorial-glossary canon."
        ),
    ),
    StrongMentionRule(
        name="aquinas_commentator",
        target_author="Averroes",
        target_work="",
        forms=(
            "Commentator",
            "Commentatoris",
            "Commentatori",
            "Commentatorem",
        ),
        confidence=0.92,
        langs=("lat",),
        note=(
            "Aquinas's 'Commentator' is Averroes (the great commentator "
            "on Aristotle). Strong by convention — used with the same "
            "definitional consistency as 'Philosophus'."
        ),
    ),
    # ── weak rules: surface-form name mentions ───────────────────
    AuthorMentionRule(
        name="aquinas_aristoteles",
        target_author="Aristotle",
        target_work="",
        forms=(
            "Aristoteles",
            "Aristotelis",
            "Aristotelem",
            "Aristotele",
            "Aristoteli",
        ),
        confidence=0.7,
        # Higher than the 0.45 default because Aristotle is the dominant
        # Aquinas interlocutor — a name-mention is highly likely to be
        # a real reference, just not as load-bearing as the Philosophus
        # convention.
        langs=("lat",),
    ),
    AuthorMentionRule(
        name="aquinas_plato",
        target_author="Plato",
        target_work="",
        forms=("Plato", "Platonis", "Platonem", "Platone", "Platoni"),
        confidence=0.6,
        langs=("lat",),
    ),
    AuthorMentionRule(
        name="aquinas_augustinus",
        target_author="Augustine",
        target_work="",
        forms=(
            "Augustinus",
            "Augustini",
            "Augustinum",
            "Augustino",
        ),
        confidence=0.65,
        langs=("lat",),
        note="Aquinas cites Augustine constantly across ST and SCG.",
    ),
    AuthorMentionRule(
        name="aquinas_dionysius",
        target_author="Pseudo-Dionysius",
        target_work="",
        forms=(
            "Dionysius",
            "Dionysii",
            "Dionysium",
            "Dionysio",
        ),
        confidence=0.6,
        langs=("lat",),
        note=(
            "= Pseudo-Dionysius the Areopagite (5th-c. Syrian Christian "
            "Neoplatonist). Aquinas treats him as patristic auctoritas; "
            "the 'Pseudo-' is modern."
        ),
    ),
    AuthorMentionRule(
        name="aquinas_boethius",
        target_author="Boethius",
        target_work="",
        forms=("Boethius", "Boethii", "Boethium", "Boethio"),
        confidence=0.65,
        langs=("lat",),
    ),
    AuthorMentionRule(
        name="aquinas_avicenna",
        target_author="Avicenna",
        target_work="",
        forms=("Avicenna", "Avicennae", "Avicennam"),
        confidence=0.7,
        langs=("lat",),
    ),
    AuthorMentionRule(
        name="aquinas_averroes_byname",
        target_author="Averroes",
        target_work="",
        forms=("Averroes", "Averrois", "Averroem"),
        confidence=0.7,
        langs=("lat",),
        note="Direct name mention; complements the Commentator strong rule.",
    ),
    AuthorMentionRule(
        name="aquinas_cicero",
        target_author="Cicero",
        target_work="",
        forms=("Cicero", "Ciceronis", "Ciceronem", "Cicerone", "Tullius", "Tullii"),
        confidence=0.55,
        langs=("lat",),
        note="Includes the 'Tullius' surface form Aquinas occasionally uses.",
    ),
    AuthorMentionRule(
        name="aquinas_porphyrius",
        target_author="Porphyry",
        target_work="",
        forms=("Porphyrius", "Porphyrii", "Porphyrium", "Porphyrio"),
        confidence=0.55,
        langs=("lat",),
    ),
    # Origen — Aquinas engages Origen via Augustine and Jerome more
    # than directly, but the ST commentaries (esp. ST I q.20 a.3,
    # q.62, q.106) name him. Lower confidence than Augustine →
    # Origen since Aquinas's Origen-citations are usually mediated.
    AuthorMentionRule(
        name="aquinas_origen",
        target_author="Origen",
        target_work="",
        forms=("Origenes", "Origenis", "Origenem", "Origeni"),
        confidence=0.85,
        langs=("lat",),
        note="ST citations of Origen on grace, free will, eschatology.",
    ),
)
