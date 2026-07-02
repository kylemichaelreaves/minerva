"""Rules that fire on Augustine chunks.

Augustine's Latin prose names its sources by name throughout. The
Plotinus debt is mediated through Porphyry's epitomes / Marius
Victorinus's translations — so direct Plotinus mentions are rare,
but Plato (whom Augustine read in Plotinian dress) is named often.

Cicero is the classical-philosophical interlocutor for Augustine
(the Hortensius launched his philosophical career — Conf. III.4);
Vergil is the literary-quotation pool; Ambrose is the Milan-era
teacher cited throughout the Confessions.
"""

from __future__ import annotations

from . import AuthorMentionRule
from .scripture_cite import FormulaicQuoteRule

RULES = (
    # ── formulaic Psalm-quote rule: Augustine cites scripture
    # exclusively in the quoted-text style (no chapter:verse
    # locators in his la.wikisource source). Survey found 143
    # Psalm-introducer matches across his 1,406 chunks — the
    # highest-volume scripture target by far. Apostolus / Dominus
    # /sicut-scriptum-est formulae point at multi-work targets
    # (Pauline epistles, four Gospels, all of OT) which exceeds
    # embed-verify Pass A's single-work scope — deferred.
    FormulaicQuoteRule(
        name="augustine_psalm_quote",
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
            # Augustine-specific: "sancti psalmi" (genitive Psalm
            # reference, often in his exegetical works).
            r"sancti\s+psalmi",
        ),
    ),
    AuthorMentionRule(
        name="augustine_cicero",
        target_author="Cicero",
        target_work="",
        forms=("Cicero", "Ciceronis", "Ciceronem", "Cicerone", "Tullius", "Tullii"),
        confidence=0.65,
        langs=("lat",),
        note=(
            "Cicero is Augustine's main classical-philosophical "
            "interlocutor — Hortensius (Conf. III.4) launched his "
            "philosophical career."
        ),
    ),
    AuthorMentionRule(
        name="augustine_plato",
        target_author="Plato",
        target_work="",
        forms=("Plato", "Platonis", "Platonem", "Platone", "Platoni"),
        confidence=0.65,
        langs=("lat",),
        note=(
            "The Platonist books that mediated Augustine's conversion "
            "(Conf. VII.9 ff.) frame the De civ. Dei VIII-X engagement."
        ),
    ),
    AuthorMentionRule(
        name="augustine_platonici",
        target_author="Plato",
        target_work="",
        forms=("Platonici", "Platonicorum", "Platonicis", "Platonicos"),
        confidence=0.55,
        langs=("lat",),
        note=(
            "Augustine's collective term for the Plotinian Neoplatonists. "
            "Different surface form, but functionally a Plato reference."
        ),
    ),
    AuthorMentionRule(
        name="augustine_plotinus",
        target_author="Plotinus",
        target_work="",
        forms=("Plotinus", "Plotini", "Plotinum", "Plotino"),
        confidence=0.8,
        langs=("lat",),
        note=(
            "Direct Plotinus mention is rare in Augustine — when it "
            "appears it's load-bearing (De civ. Dei IX-X)."
        ),
    ),
    AuthorMentionRule(
        name="augustine_porphyrius",
        target_author="Porphyry",
        target_work="",
        forms=("Porphyrius", "Porphyrii", "Porphyrium", "Porphyrio"),
        confidence=0.7,
        langs=("lat",),
        note=(
            "Porphyry is Augustine's epistolary foil in De civ. Dei X "
            "(against Christianity). Direct mention is unambiguous."
        ),
    ),
    AuthorMentionRule(
        name="augustine_vergil",
        target_author="Vergil",
        target_work="",
        forms=("Virgilius", "Virgilii", "Maro", "Maronis"),
        confidence=0.5,
        langs=("lat",),
        note=(
            "Vergil is pervasive in Confessions but rarely named — "
            "most quotes are unattributed. Direct name-mention is "
            "the high-confidence signal here."
        ),
    ),
    AuthorMentionRule(
        name="augustine_ambrosius",
        target_author="Ambrose",
        target_work="",
        forms=("Ambrosius", "Ambrosii", "Ambrosium", "Ambrosio"),
        confidence=0.75,
        langs=("lat",),
        note="Augustine's Milan-era teacher; named throughout the Confessions.",
    ),
    AuthorMentionRule(
        name="augustine_aristoteles",
        target_author="Aristotle",
        target_work="",
        forms=(
            "Aristoteles",
            "Aristotelis",
            "Aristotelem",
            "Aristotele",
        ),
        confidence=0.6,
        langs=("lat",),
        note=(
            "Augustine read the Categories in Latin translation — "
            "the De civ. Dei VIII surveys Aristotle alongside Plato."
        ),
    ),
    AuthorMentionRule(
        name="augustine_manichaei",
        target_author="Manichaeus",  # the Manichaean tradition — out of corpus
        target_work="",
        forms=("Manichaeus", "Manichaei", "Manichaeorum", "Manichaeis"),
        confidence=0.5,
        langs=("lat",),
        note=(
            "Augustine's pre-conversion adversary tradition. The mention "
            "is always a reference (Augustine is anti-Manichaean) but the "
            "target is a school rather than an author — keep low confidence "
            "until a curator can refine."
        ),
    ),
    # ── Tragedians (City of God uses tragedy as moral exempla) ────
    # Augustine engages Greek tragedy in De Civitate Dei Bk II–III
    # (against pagan stage shows) and occasionally in Confessions /
    # De Doctrina Christiana. References are typically by Latinized
    # name. Lower confidence than the philosophers because the
    # mention is often a side-mention in a polemical aside.
    AuthorMentionRule(
        name="augustine_aeschylus",
        target_author="Aeschylus",
        target_work="",
        forms=("Aeschylus", "Aeschyli", "Aeschylum", "Aeschylo"),
        confidence=0.65,
        langs=("lat", "eng"),
    ),
    AuthorMentionRule(
        name="augustine_sophocles",
        target_author="Sophocles",
        target_work="",
        forms=("Sophocles", "Sophoclis", "Sophoclem", "Sophocle"),
        confidence=0.65,
        langs=("lat", "eng"),
    ),
    AuthorMentionRule(
        name="augustine_euripides",
        target_author="Euripides",
        target_work="",
        forms=("Euripides", "Euripidis", "Euripidem", "Euripide"),
        confidence=0.65,
        langs=("lat", "eng"),
    ),
    # Origen — Augustine engages Origen on multiple doctrinal points
    # (apokatastasis, eschatology, allegorical exegesis). *De Civitate
    # Dei* XXI.17 critiques Origen by name; *De Haeresibus* lists him;
    # other letters and treatises return to him.
    AuthorMentionRule(
        name="augustine_origen",
        target_author="Origen",
        target_work="",
        forms=("Origenes", "Origenis", "Origenem", "Origeni", "Origenian"),
        confidence=0.9,
        langs=("lat", "eng"),
        note="De Civ. Dei XXI.17 + De Haeresibus + various letters.",
    ),
    AuthorMentionRule(
        name="augustine_origen_eng",
        target_author="Origen",
        target_work="",
        forms=("Origen", "Origenistic"),
        confidence=0.88,
        langs=("eng",),
    ),
    # Celsus — Augustine knows Celsus via Origen and occasionally
    # invokes him as a stand-in for pagan anti-Christian critique.
    # Lower confidence than Origen itself; verify on next embed-pass.
    AuthorMentionRule(
        name="augustine_celsus",
        target_author="Celsus",
        target_work="",
        forms=("Celsus", "Celsi", "Celsum", "Celso"),
        confidence=0.7,
        langs=("lat", "eng"),
        note="Augustine knows Celsus only through Origen. Out-of-corpus.",
    ),
)
