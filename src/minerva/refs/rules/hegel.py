"""Rules that fire on Hegel chunks.

Hegel cites by name across the corpus — Kant most often, then Plato,
Aristotle, Spinoza, Descartes, and the broader history of philosophy.
The PR and PhG names them openly; the Wissenschaft der Logik and
Encyclopedia argue with them by name in the Anmerkungen.

The corpus has both German originals and English translations under
the same author header, so the rules cover both languages. German
forms (Kant, Kantischen, kantisch) and English (Kant, Kantian).
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule, _figures
from .scripture_cite import default_scripture_rules

RULES = (
    *default_scripture_rules("hegel"),
    AuthorMentionRule(
        name="hegel_kant",
        target_author="Kant",
        target_work="",
        forms=(
            "Kant",
            "Kantischen",
            "Kantische",
            "kantisch",
            "Kantian",
            "Kantianism",
        ),
        confidence=0.75,
        langs=("deu", "eng"),
        note=(
            "Hegel's primary modern interlocutor. PR §29 / §258 in "
            "particular are explicit corrections of Kant's MS and "
            "social-contract project."
        ),
    ),
    AuthorMentionRule(
        name="hegel_kritik_der_reinen_vernunft",
        target_author="Kant",
        target_work="Critique of Pure Reason",
        forms=(
            "Vernunftkritik",
            "Kritik der reinen Vernunft",
            "Critique of Pure Reason",
        ),
        confidence=0.9,
        # Higher than the bare-Kant name — the work-title proximity is
        # already encoded in the surface form itself, so this is
        # functionally a high-confidence work-targeted reference.
        langs=("deu", "eng"),
        note=(
            "Direct mention of Kant's KrV — work-title-explicit, so the "
            "ensure_target call resolves to the in-corpus Kant work and "
            "the 'Open in reader →' affordance lights up."
        ),
    ),
    AuthorMentionRule(
        name="hegel_plato",
        target_author="Plato",
        target_work="",
        forms=(
            "Plato",
            "Platon",
            "Platons",
            "Platonic",
            "Platonische",
            "Platonischen",
        ),
        confidence=0.65,
        langs=("deu", "eng"),
        note=(
            "Hegel's account of Plato is foundational for the PR / "
            "Lectures on History of Philosophy II."
        ),
    ),
    AuthorMentionRule(
        name="hegel_aristotle",
        target_author="Aristotle",
        target_work="",
        forms=_figures.ARISTOTLE_DEU_ENG,
        confidence=0.65,
        langs=("deu", "eng"),
        note=(
            "Hegel's praise of Aristotle is the structuring move of "
            "the Encyclopedia's account of Spirit (Enz §§ 377–82)."
        ),
    ),
    AuthorMentionRule(
        name="hegel_spinoza",
        target_author="Spinoza",
        target_work="",
        forms=_figures.SPINOZA_DEU_ENG,
        confidence=0.75,
        langs=("deu", "eng"),
        note=(
            "Hegel reads Spinoza as the modern Eleaticism — substance "
            "without subject. The Wissenschaft der Logik's substance "
            "chapter argues this by name."
        ),
    ),
    AuthorMentionRule(
        name="hegel_descartes",
        target_author="Descartes",
        target_work="",
        forms=(
            "Descartes",
            "Cartesische",
            "Cartesischen",
            "Cartesian",
            "Cartesianism",
        ),
        confidence=0.7,
        langs=("deu", "eng"),
        note=(
            "Hegel's history-of-philosophy treatment of modern thought "
            "opens with Descartes as the inception of subjectivity."
        ),
    ),
    AuthorMentionRule(
        name="hegel_fichte",
        target_author="Fichte",  # out-of-corpus target
        target_work="",
        forms=("Fichte", "Fichtes", "Fichtean", "Fichtesche", "Fichteschen"),
        confidence=0.7,
        langs=("deu", "eng"),
        note=(
            "Fichte is Hegel's immediate post-Kantian foil — referenced "
            "openly across the PR's Vorrede and the Differenzschrift "
            "tradition. Out-of-corpus target."
        ),
    ),
    AuthorMentionRule(
        name="hegel_schelling",
        target_author="Schelling",  # out-of-corpus target
        target_work="",
        forms=("Schelling", "Schellings", "Schellingian"),
        confidence=0.7,
        langs=("deu", "eng"),
        note=("Schelling is the PhG Vorrede's polemical target. Out-of-corpus target."),
    ),
    AuthorMentionRule(
        name="hegel_augustine",
        target_author="Augustine",
        target_work="",
        forms=("Augustin", "Augustinus", "Augustine"),
        confidence=0.55,
        langs=("deu", "eng"),
    ),
    AuthorMentionRule(
        name="hegel_aquinas",
        target_author="Aquinas",
        target_work="",
        forms=("Thomas von Aquin", "Thomas Aquinas", "Aquinaten", "Thomism"),
        confidence=0.55,
        langs=("deu", "eng"),
        note=(
            "Hegel's medieval treatments are sparse but Aquinas is "
            "named in the Lectures on History of Philosophy."
        ),
    ),
    # Heraclitus — Hegel's famous admiration: "There is no
    # proposition of Heraclitus which I have not adopted in my
    # Logic." Discussed at length in the Lectures on History of
    # Philosophy Vol I.
    StrongMentionRule(
        name="hegel_heraclitus",
        target_author="Heraclitus",
        target_work="",
        forms=(
            "Heraklit",
            "Heraklits",
            "Heraclitus",
            "heraklitisch",
            "heraklitische",
            "heraklitischen",
        ),
        confidence=0.9,
        langs=("deu", "eng"),
        note=(
            "Hegel's famous declaration in the LHP Vol I: 'es ist "
            "kein Satz des Heraklit, den ich nicht in meine Logik "
            "aufgenommen.'"
        ),
    ),
    # Hobbes — engaged in the Philosophy of Right (state of
    # nature, sovereignty) and the LHP Vol III (the modern
    # political philosophy chapter).
    AuthorMentionRule(
        name="hegel_hobbes",
        target_author="Hobbes",
        target_work="",
        forms=_figures.HOBBES_DEU_ENG,
        confidence=0.85,
        langs=("deu", "eng"),
        note=("Philosophy of Right §§29-30 + LHP Vol III modern political philosophy section."),
    ),
    # Locke — engaged in LHP Vol III as the founding empiricist.
    AuthorMentionRule(
        name="hegel_locke",
        target_author="Locke",
        target_work="",
        forms=_figures.LOCKE_DEU_ENG,
        confidence=0.85,
        langs=("deu", "eng"),
    ),
    # Hume — sceptical empiricism, the bridge to Kant. Discussed
    # in LHP Vol III and referenced throughout the Phenomenology
    # of Spirit's treatment of certainty.
    AuthorMentionRule(
        name="hegel_hume",
        target_author="Hume",
        target_work="",
        forms=("Hume", "Humes", "Humesch", "Humesche", "Humeschen"),
        confidence=0.85,
        langs=("deu", "eng"),
    ),
    # Rousseau — engaged in the Philosophy of Right (general will,
    # contract theory) and LHP Vol III.
    AuthorMentionRule(
        name="hegel_rousseau",
        target_author="Rousseau",
        target_work="",
        forms=_figures.ROUSSEAU_DEU_ENG,
        confidence=0.85,
        langs=("deu", "eng"),
        note=("Philosophy of Right §§29-30 (general will) + LHP Vol III."),
    ),
    # Pascal — referenced occasionally in the Phenomenology of
    # Religion and the LHP Vol III.
    AuthorMentionRule(
        name="hegel_pascal",
        target_author="Pascal",
        target_work="",
        forms=("Pascal", "Pascals", "pascalsch", "pascalsche"),
        confidence=0.75,
        langs=("deu", "eng"),
    ),
    # Cicero — engaged in LHP Vol I (Hellenistic section).
    AuthorMentionRule(
        name="hegel_cicero",
        target_author="Cicero",
        target_work="",
        forms=("Cicero", "Ciceros", "Ciceronisch", "Ciceronische", "Ciceronischen"),
        confidence=0.85,
        langs=("deu", "eng"),
        note="LHP Vol I Hellenistic + LHP Vol II Latin patristic sections.",
    ),
    # Lucretius — discussed in LHP Vol I as the Epicurean.
    AuthorMentionRule(
        name="hegel_lucretius",
        target_author="Lucretius",
        target_work="",
        forms=("Lukrez", "Lukrezius", "Lucretius", "Lucretian"),
        confidence=0.85,
        langs=("deu", "eng"),
    ),
    # Democritus + Epicurus — LHP Vol I devotes a full atomism section
    # to Leukipp/Demokrit (the founders) and Epikur (the systematizer).
    # The Phänomenologie's sense-certainty critique and the
    # Wissenschaft der Logik's discussion of the One/Many circle back
    # to these atomists.
    AuthorMentionRule(
        name="hegel_democritus",
        target_author="Democritus",
        target_work="",
        forms=("Demokrit", "Demokrits", "Demokritisch", "Democritus", "Democritean"),
        confidence=0.88,
        langs=("deu", "eng"),
    ),
    AuthorMentionRule(
        name="hegel_epicurus",
        target_author="Epicurus",
        target_work="",
        forms=("Epikur", "Epikurs", "Epikureisch", "Epikureische", "Epicurus", "Epicurean"),
        confidence=0.88,
        langs=("deu", "eng"),
    ),
    # Epictetus — Stoic discussion in LHP Vol I and the Stoicism
    # chapter of the Phenomenology of Spirit.
    AuthorMentionRule(
        name="hegel_epictetus",
        target_author="Epictetus",
        target_work="",
        forms=("Epiktet", "Epiktets", "Epictetus"),
        confidence=0.88,
        langs=("deu", "eng"),
    ),
    # Marcus Aurelius — paired with Epictetus in the LHP Stoicism
    # section.
    AuthorMentionRule(
        name="hegel_marcus_aurelius",
        target_author="Marcus Aurelius",
        target_work="",
        forms=("Marc Aurel", "Mark Aurel", "Marcus Aurelius", "Antoninus"),
        confidence=0.85,
        langs=("deu", "eng"),
    ),
    # ── Tragedians ────────────────────────────────────────────────
    # The Phänomenologie's Antigone reading (Section C, VI.A.a — the
    # "Sittlichkeit" chapter) and the Vorlesungen über die Ästhetik's
    # treatment of Greek tragedy make all three tragedians central to
    # Hegel's thought. Antigone is the privileged exemplar; Aeschylus
    # appears via Eumenides (state vs. family conflict) and Promethus
    # Bound; Euripides is mentioned with Hegel's characteristic note
    # of "decadence" (the dialectical shift from Sophoclean substance
    # to Euripidean reflection).
    AuthorMentionRule(
        name="hegel_aeschylus",
        target_author="Aeschylus",
        target_work="",
        forms=(
            "Äschylus",
            "Aeschylus",
            "Aischylos",
            "äschyleisch",
            "äschyleische",
        ),
        confidence=0.85,
        langs=("deu", "eng"),
    ),
    AuthorMentionRule(
        name="hegel_sophocles",
        target_author="Sophocles",
        target_work="",
        forms=(
            "Sophokles",
            "Sophocles",
            "sophokleisch",
            "sophokleische",
            "Sophoclean",
        ),
        confidence=0.9,
        langs=("deu", "eng"),
        note=(
            "Antigone is Hegel's tragic exemplar in PhG VI.A.a and in "
            "the Ästhetik's tragedy chapter. Very high confidence — "
            "Hegel's Sophocles references are essentially never "
            "incidental."
        ),
    ),
    AuthorMentionRule(
        name="hegel_euripides",
        target_author="Euripides",
        target_work="",
        forms=(
            "Euripides",
            "Euripideisch",
            "euripideisch",
            "euripideische",
        ),
        confidence=0.8,
        langs=("deu", "eng"),
    ),
    # Aesop — the marquee link is the Preface to *Philosophy of Right*:
    # Hegel's "Hic Rhodus, hic salta" Latin tag and his German
    # "Hier ist die Rose, hier tanze" are both renderings of Aesop's
    # *Boastful Athlete* fable (Babrius 47 / Perry 33). LHP also
    # discusses Aesop in the pre-philosophical Greek section.
    AuthorMentionRule(
        name="hegel_aesop",
        target_author="Aesop",
        target_work="",
        forms=("Äsop", "Äsops", "Aesop", "Hic Rhodus"),
        confidence=0.9,
        langs=("deu", "eng"),
        note=(
            "Preface to Philosophy of Right: 'Hic Rhodus, hic salta' / "
            "'Hier ist die Rose, hier tanze' renders Aesop's Boastful "
            "Athlete fable (Babrius 47 / Perry 33)."
        ),
    ),
    # Origen — LHP Vol II patristic section discusses Origen on
    # allegorical exegesis and the Logos doctrine.
    AuthorMentionRule(
        name="hegel_origen",
        target_author="Origen",
        target_work="",
        forms=("Origenes", "Origen", "Origenian"),
        confidence=0.82,
        langs=("deu", "eng"),
    ),
    # Celsus — Hegel knows Celsus only via Origen; named in the LHP
    # patristic section as exemplar pagan critic of Christianity.
    AuthorMentionRule(
        name="hegel_celsus",
        target_author="Celsus",
        target_work="",
        forms=("Celsus", "Kelsos"),
        confidence=0.72,
        langs=("deu", "eng"),
        note="LHP Vol II patristic-era discussion. Out-of-corpus.",
    ),
    # ─── Homer ───────────────────────────────────────────────────
    # Hegel cites Homer across the Phenomenology, the Aesthetics, the
    # Philosophy of Right (Preface — *Penelope's weaving* as figure
    # for philosophy that "begins afresh every day"), the Lectures
    # on Philosophy of World History (Trojan War), and the Lectures
    # on History of Philosophy. Surface mentions span the work title
    # (Iliad / Odyssey), the author name (Homer / Homère), and the
    # most prominent characters (Penelope, Achilles, Ulysses,
    # Odysseus, Hector). The Penelope-weaving figure is the marquee
    # Phil-of-Right Preface reference the user flagged on 2026-05-29.
    AuthorMentionRule(
        name="hegel_homer",
        target_author="Homer",
        target_work="",
        forms=(
            "Homer",
            "Homère",
            "Iliad",
            "Iliade",
            "Odyssey",
            "Odyssee",
            "Odyssée",
            "Penelope",
            "Pénélope",
            "Achilles",
            "Achilleus",
            "Achill",  # German short form
            "Ulysses",
            "Odysseus",
            "Hector",
            "Hektor",
            "Trojan War",
            "Trojanische Krieg",
        ),
        confidence=0.85,
        langs=("deu", "eng"),
        note=(
            "Phil of Right Preface §3 *Penelope's weaving*; Phenomenology "
            "uses Antigone + Iliad heroic-vs-ethical contrasts; LPHW "
            "Trojan War as origin of Greek self-consciousness; Aesthetics "
            "treats Iliad as the paradigmatic epic."
        ),
    ),
    AuthorMentionRule(
        name="hegel_schiller",
        target_author="Schiller",
        target_work="",
        forms=("Schiller", "Schillers", "Schillersche", "Schillerschen", "schillersch"),
        confidence=0.75,
        langs=("deu", "eng"),
        note=(
            "Hegel closes the Phenomenology paraphrasing Schiller "
            "('die Wunden des Geistes heilen…') and quotes Schiller "
            "repeatedly in the Aesthetics lectures on the aesthetic."
        ),
    ),
)
