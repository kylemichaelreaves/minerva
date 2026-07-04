"""Rules that fire on Nietzsche chunks.

Nietzsche's central interlocutors split into three groups:

* **In-corpus targets** Nietzsche engages by name: Kant, Hegel,
  Plato, Aristotle, Spinoza. Standard mention rules.
* **Out-of-corpus targets** central to specific works:
  - **Sokrates** — central to *Die Geburt der Tragödie* (the "Sokratic
    rationalism" critique) and to *Götzen-Dämmerung*'s "Problem des
    Sokrates" chapter. StrongMentionRule.
  - **Christus / Christentum** — *Der Antichrist*'s entire target.
    StrongMentionRule on the religion/founder cluster.
  - **Schopenhauer** — Nietzsche's principal modern predecessor; one
    of the four *Unzeitgemäße Betrachtungen* essays is on him,
    and *Geburt der Tragödie* is steeped in his metaphysics.
    StrongMentionRule.
  - **Wagner** — target of *Der Fall Wagner* and *Nietzsche contra
    Wagner*; previously Nietzsche's hero (*Richard Wagner in
    Bayreuth*). StrongMentionRule.
  - **Darwin / Darwinismus** — Nietzsche's polemical engagement with
    Darwinian survival-of-the-fittest in *JGB* and *GM*.
  - **Goethe** — frequently named as the German poet-philosopher
    Nietzsche admires.
  - **Buddha / Buddhismus** — referenced in *AC* and *GM* as a
    parallel to Christianity.

All rules gate on `langs=("deu",)` — Nietzsche is German-only.
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule, _figures
from .scripture_cite import default_scripture_rules

RULES = (
    *default_scripture_rules("nietzsche"),
    # ─── Out-of-corpus targets, central interlocutors ────────────
    StrongMentionRule(
        name="nietzsche_sokrates",
        target_author="Socrates",
        target_work="",
        forms=(
            "Sokrates",
            "Sokrates'",
            "sokratisch",
            "sokratische",
            "sokratischen",
            "Sokratismus",
            "Sokratiker",
        ),
        confidence=0.92,
        langs=("deu",),
        note=(
            "Sokrates is the principal target of Geburt der Tragödie's "
            "rationalism-vs-tragedy thesis and of Götzen-Dämmerung's "
            "'Das Problem des Sokrates' chapter. Out-of-corpus."
        ),
    ),
    StrongMentionRule(
        name="nietzsche_christus",
        target_author="Christ",
        target_work="",
        # Only the UNAMBIGUOUS direct references to the founder / the
        # named religion. German uses "Christus" for the person, so
        # these forms reliably point at the target (issue #54).
        forms=(
            "Christus",
            "Christi",
            "Christum",
            "Christo",
            "Jesus",
            "Christentum",
            "Christenthum",
            "Christlichkeit",
        ),
        confidence=0.88,
        langs=("deu",),
        note=(
            "Christianity / Christ is the central target of Der "
            "Antichrist and a sustained sub-theme across the late "
            "works (GD, EH, GM). Unambiguous founder/religion forms "
            "only; the ambiguous common-noun/adjective cluster is a "
            "separate rule_weak rule so it routes through llm-verify."
        ),
    ),
    AuthorMentionRule(
        name="nietzsche_christlich",
        target_author="Christ",
        target_work="",
        # High-volume, low-precision cluster: bare "Christ"/"Christen"
        # in German mean "a Christian"/"Christians" (NOT the person —
        # that's "Christus"), and "christlich*" is a topic adjective.
        # As rule_weak (< 0.85) these route through llm-verify triage
        # instead of landing as unverified rule_strong edges (issue #54).
        forms=(
            "Christ",
            "Christen",
            "christlich",
            "christliche",
            "christlichen",
            "christlicher",
        ),
        confidence=0.45,
        source_method="rule_weak",
        langs=("deu",),
        note=(
            "Ambiguous Christ/christlich cluster — weak signal, "
            "verified downstream rather than trusted as a strong cite."
        ),
    ),
    StrongMentionRule(
        name="nietzsche_schopenhauer",
        target_author="Schopenhauer",
        target_work="",
        forms=(
            "Schopenhauer",
            "Schopenhauers",
            "Schopenhauersche",
            "Schopenhauerschen",
            "schopenhauerisch",
            "schopenhauerische",
            "schopenhauerischen",
        ),
        confidence=0.92,
        langs=("deu",),
        note=(
            "Arthur Schopenhauer — Nietzsche's principal modern "
            "predecessor. One of the four Unzeitgemäße Betrachtungen "
            "('Schopenhauer als Erzieher') is on him; he frames "
            "Geburt der Tragödie's metaphysics. Out-of-corpus."
        ),
    ),
    StrongMentionRule(
        name="nietzsche_wagner",
        target_author="Wagner",
        target_work="",
        forms=(
            "Wagner",
            "Wagners",
            "Wagnersche",
            "Wagnerschen",
            "wagnerisch",
            "wagnerische",
            "wagnerischen",
            "Wagnerianer",
            "Richard Wagner",
        ),
        confidence=0.92,
        langs=("deu",),
        note=(
            "Richard Wagner — target of Der Fall Wagner and Nietzsche "
            "contra Wagner; subject of the early Richard Wagner in "
            "Bayreuth (one of the Unzeitgemäße Betrachtungen). "
            "Out-of-corpus."
        ),
    ),
    # ─── In-corpus targets ───────────────────────────────────────
    AuthorMentionRule(
        name="nietzsche_kant",
        target_author="Kant",
        target_work="",
        forms=(
            "Kant",
            "Kants",
            "Kantische",
            "Kantischen",
            "Kantischer",
            "Kantianer",
            "Kantianismus",
            "kantianisch",
            "kantianische",
        ),
        confidence=0.85,
        langs=("deu",),
    ),
    AuthorMentionRule(
        name="nietzsche_hegel",
        target_author="Hegel",
        target_work="",
        forms=(
            "Hegel",
            "Hegels",
            "Hegelsche",
            "Hegelschen",
            "Hegelianer",
            "hegelianisch",
            "hegelianische",
            "hegelianischen",
        ),
        confidence=0.85,
        langs=("deu",),
    ),
    AuthorMentionRule(
        name="nietzsche_plato",
        target_author="Plato",
        target_work="",
        forms=(
            "Plato",
            "Platon",
            "Platons",
            "Platonismus",
            "Platoniker",
            "platonisch",
            "platonische",
            "platonischen",
        ),
        confidence=0.8,
        langs=("deu",),
    ),
    AuthorMentionRule(
        name="nietzsche_aristoteles",
        target_author="Aristotle",
        target_work="",
        forms=(
            "Aristoteles",
            "aristotelisch",
            "aristotelische",
            "aristotelischen",
        ),
        confidence=0.75,
        langs=("deu",),
    ),
    AuthorMentionRule(
        name="nietzsche_spinoza",
        target_author="Spinoza",
        target_work="",
        forms=_figures.SPINOZA_DEU,
        confidence=0.85,
        langs=("deu",),
        note=(
            "Nietzsche calls Spinoza his 'Vorgänger' (precursor) in "
            "letters and in JGB §198. Less frequently cited than "
            "Schopenhauer but always deliberate when named."
        ),
    ),
    # ─── Other out-of-corpus targets (lower confidence) ──────────
    AuthorMentionRule(
        name="nietzsche_darwin",
        target_author="Darwin",
        target_work="",
        forms=("Darwin", "Darwins", "Darwinismus", "darwinistisch", "darwinistische"),
        confidence=0.85,
        langs=("deu",),
        note=(
            "Darwin / Darwinismus — Nietzsche engages the survival-"
            "of-the-fittest framework in JGB §13 and across GM. "
            "Out-of-corpus."
        ),
    ),
    AuthorMentionRule(
        name="nietzsche_goethe",
        target_author="Goethe",
        target_work="",
        forms=("Goethe", "Goethes", "Goethesche", "Goetheschen"),
        confidence=0.8,
        langs=("deu",),
    ),
    AuthorMentionRule(
        name="nietzsche_buddha",
        target_author="Buddha",
        target_work="",
        forms=("Buddha", "Buddhas", "Buddhismus", "buddhistisch", "buddhistische"),
        confidence=0.85,
        langs=("deu",),
        note=(
            "Buddhismus appears in AC and GM as a parallel to "
            "Christianity ('nihilist religion'). Out-of-corpus."
        ),
    ),
    # Heraclitus — Nietzsche's adopted Greek precursor. In Ecce
    # Homo (Geburt der Tragödie §3): "the doctrine of the 'eternal
    # recurrence,' that is, of the unconditional and infinitely
    # repeated circular course of all things — this doctrine of
    # Zarathustra might in the end have been taught already by
    # Heraclitus." Strong rule.
    StrongMentionRule(
        name="nietzsche_heraclitus",
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
        langs=("deu",),
        note=(
            "Nietzsche's most-claimed Greek predecessor. Discussed "
            "at length in Die Philosophie im tragischen Zeitalter "
            "der Griechen and in Ecce Homo."
        ),
    ),
    # Rousseau — Nietzsche's polemical target on egalitarianism
    # and ressentiment-driven moralism. "Die moralische Tarantel
    # Rousseau" (Götzen-Dämmerung). Strong rule because the
    # mentions are pointed.
    StrongMentionRule(
        name="nietzsche_rousseau",
        target_author="Rousseau",
        target_work="",
        forms=(
            "Rousseau",
            "Rousseaus",
            "Rousseausche",
            "Rousseauschen",
            "rousseauisch",
            "rousseauische",
        ),
        confidence=0.9,
        langs=("deu",),
        note=(
            "Nietzsche's polemical target on equality / moralism. "
            "BGE, GD, AC contain explicit polemics."
        ),
    ),
    # Pascal — Nietzsche's avowed sympathy with Pascal as the
    # tragic-religious thinker. BGE §45: "Pascal, den ich beinahe
    # liebe." Reference in EH, GM.
    StrongMentionRule(
        name="nietzsche_pascal",
        target_author="Pascal",
        target_work="",
        forms=("Pascal", "Pascals", "pascalsch", "pascalsche"),
        confidence=0.9,
        langs=("deu",),
        note=(
            "Nietzsche's 'Pascal whom I almost love' (BGE §45) — "
            "the religious-tragic Pascal is one of Nietzsche's "
            "most reverentially-treated targets."
        ),
    ),
    # Hobbes — referenced in BGE and GM in the moralism / state-
    # of-nature critiques. Less frequent than the major targets
    # but explicit.
    AuthorMentionRule(
        name="nietzsche_hobbes",
        target_author="Hobbes",
        target_work="",
        forms=_figures.HOBBES_DEU_ENG,
        confidence=0.8,
        langs=("deu",),
    ),
    # Descartes — referenced in MA, FW, JGB on the cogito and
    # rationalist epistemology.
    AuthorMentionRule(
        name="nietzsche_descartes",
        target_author="Descartes",
        target_work="",
        forms=(
            "Descartes",
            "Cartesianisch",
            "Cartesianische",
            "Cartesianischen",
            "cartesianisch",
            "Kartesianer",
        ),
        confidence=0.8,
        langs=("deu",),
    ),
    # Cicero — Nietzsche was a classical philologist; Cicero appears
    # in the early philological lectures + the Nachlass.
    AuthorMentionRule(
        name="nietzsche_cicero",
        target_author="Cicero",
        target_work="",
        forms=("Cicero", "Ciceros", "Ciceronian", "ciceronianisch"),
        confidence=0.75,
        langs=("deu",),
    ),
    # Epictetus — Stoic critique in BGE, FW. Out-of-corpus until
    # the ancient quartet round.
    AuthorMentionRule(
        name="nietzsche_epictetus",
        target_author="Epictetus",
        target_work="",
        forms=("Epiktet", "Epiktets", "Epictetus"),
        confidence=0.85,
        langs=("deu",),
    ),
    # Marcus Aurelius — Stoic philosopher-emperor; appears in BGE
    # + the Nachlass as Stoic exemplar.
    AuthorMentionRule(
        name="nietzsche_marcus_aurelius",
        target_author="Marcus Aurelius",
        target_work="",
        forms=("Mark Aurel", "Marc Aurel", "Marcus Aurelius", "Antoninus"),
        confidence=0.85,
        langs=("deu",),
    ),
    # Lucretius — classical philologist's reference; Nietzsche's
    # lectures + Nachlass discuss Lucretius.
    AuthorMentionRule(
        name="nietzsche_lucretius",
        target_author="Lucretius",
        target_work="",
        forms=("Lukrez", "Lucretius", "lukrezisch", "lukrezische"),
        confidence=0.8,
        langs=("deu",),
    ),
    # Democritus — Nietzsche's early philological focus. The
    # *Demokrit-Studien* notebooks (1866-69, BAW) were drafts for an
    # unpublished monograph; the published works keep invoking him as
    # the materialist counterweight to Plato.
    AuthorMentionRule(
        name="nietzsche_democritus",
        target_author="Democritus",
        target_work="",
        forms=("Demokrit", "Demokrits", "demokritisch", "demokritische", "Democritus"),
        confidence=0.85,
        langs=("deu",),
    ),
    # Theognis of Megara — aristocratic anti-democratic elegist (6th c.
    # BCE). Subject of Nietzsche's first major philological publication
    # *Zur Geschichte der Theognideischen Spruchsammlung* (1867), which
    # earned him the doctorate. The aristocratic-vs-demos value frame
    # Theognis defends prefigures Nietzsche's later *Herrenmoral*.
    AuthorMentionRule(
        name="nietzsche_theognis",
        target_author="Theognis",
        target_work="",
        forms=("Theognis", "Theognidis", "theognideisch", "theognideische"),
        confidence=0.88,
        langs=("deu",),
        note="Subject of Nietzsche's 1867 philological dissertation. Out-of-corpus.",
    ),
    # ── Tragedians (Geburt der Tragödie + Götzen-Dämmerung) ────────
    # Aeschylus and Sophocles are the heroes of Die Geburt der
    # Tragödie's "tragic age of the Greeks"; Euripides is the
    # villain who, with Sokrates, kills tragedy. The Nachlass
    # returns to them constantly. German Romantic spelling uses
    # 'Äschylus' (Goethe) alongside the modern 'Aischylos'; both
    # appear in Nietzsche's prose.
    AuthorMentionRule(
        name="nietzsche_aeschylus",
        target_author="Aeschylus",
        target_work="",
        forms=(
            "Äschylus",
            "Aischylos",
            "Aeschylus",
            "Aischylos'",
            "Äschylus'",
            "äschyleisch",
            "äschyleische",
            "aischyleisch",
        ),
        confidence=0.9,
        langs=("deu",),
        note=(
            "Die Geburt der Tragödie elevates Aeschylus as the apex of "
            "Dionysian art. Very high confidence — the references are "
            "almost never incidental."
        ),
    ),
    AuthorMentionRule(
        name="nietzsche_sophocles",
        target_author="Sophocles",
        target_work="",
        forms=(
            "Sophokles",
            "Sophocles",
            "Sophokles'",
            "sophokleisch",
            "sophokleische",
            "sophocleisch",
        ),
        confidence=0.9,
        langs=("deu",),
    ),
    AuthorMentionRule(
        name="nietzsche_euripides",
        target_author="Euripides",
        target_work="",
        forms=(
            "Euripides",
            "Euripides'",
            "euripideisch",
            "euripideische",
        ),
        confidence=0.9,
        langs=("deu",),
        note=(
            "Geburt der Tragödie §11–15 is a sustained polemic against "
            "Euripides as the agent of tragedy's death via Sokratic "
            "rationalism. Always a real reference."
        ),
    ),
    # Celsus — *Der Antichrist* invokes Celsus by name as a forerunner
    # of Nietzsche's own anti-Christian polemic; the *Genealogie der
    # Moral* slave-morality thesis structurally reformulates Celsus's
    # *Contra Celsum* 3.44 women/children/slaves critique. Out-of-
    # corpus target — Nietzsche knew Celsus only via Origen, but the
    # citations are direct enough to wire.
    AuthorMentionRule(
        name="nietzsche_celsus",
        target_author="Celsus",
        target_work="",
        forms=("Celsus", "Kelsos", "celsisch"),
        confidence=0.88,
        langs=("deu",),
        note=(
            "Der Antichrist names Celsus directly; Genealogy of Morals "
            "slave-morality is structurally Celsus 3.44. Out-of-corpus."
        ),
    ),
    # Origen — Nietzsche's classical-philology training makes Origen
    # a known quantity; references in the Nachlass and *Der Antichrist*
    # critique Origenist allegorical exegesis.
    AuthorMentionRule(
        name="nietzsche_origen",
        target_author="Origen",
        target_work="",
        forms=("Origenes", "Origen", "origenisch"),
        confidence=0.78,
        langs=("deu",),
    ),
    # Henri de Boulainvilliers — proximate historical source for the
    # Frankish-conquest / two-race material that Nietzsche reformulates
    # in *Genealogie der Moral* I.5/I.11 as the master-morality / blond-
    # beast thesis. Direct citations are sparse (Nietzsche absorbs the
    # thesis via 19th-c French historians — Renan, Thierry, Gobineau —
    # more than via the 18th-c original), so confidence is moderate;
    # the LLM-verify pass should disambiguate references to "die
    # Eroberer" / "die Franken" that are NOT specifically Boulainvilliers.
    # German spelling sometimes drops the second 'l' (Boulainviller) or
    # uses the older Boulainviller variant.
    AuthorMentionRule(
        name="nietzsche_boulainvilliers",
        target_author="Boulainvilliers",
        target_work="Histoire de l'ancien gouvernement de la France",
        forms=(
            "Boulainvilliers",
            "Boulainviller",
            "Boulainvillier",
        ),
        confidence=0.80,
        langs=("deu",),
        note=(
            "Frankish-conquest two-race thesis; GM I.5/I.11 master-"
            "morality / blond-beast reformulation. Often mediated via "
            "Renan / Thierry / Gobineau."
        ),
    ),
    # Arthur de Gobineau — *Essai sur l'inégalité des races humaines*
    # (1853-55) is the racial-determinism reformulation Nietzsche
    # absorbs (and partly distances from). Direct mentions in
    # Götzen-Dämmerung "Was den Deutschen abgeht", the Nachlass on
    # Rasse, and Ecce Homo. The "blond beast" of GM I.5/I.11 is
    # Gobineau's blond Aryan reread through Nietzsche's perspectival
    # frame.
    AuthorMentionRule(
        name="nietzsche_gobineau",
        target_author="Gobineau",
        target_work="Essai sur l'inégalité des races humaines",
        forms=(
            "Gobineau",
            "Gobineaus",
            "comte de Gobineau",
            "Graf Gobineau",
        ),
        confidence=0.85,
        langs=("deu",),
        note=(
            "Race / aristocracy / Aryan material — GM I.5/I.11 blond "
            "beast, Götzen-Dämmerung 'Was den Deutschen abgeht'."
        ),
    ),
    # Ernest Renan — Nietzsche names Renan repeatedly in *Der
    # Antichrist*, *Götzen-Dämmerung*, GM, and Ecce Homo. Renan's
    # *Vie de Jésus* (1863) and *L'Antéchrist* (1877) are the
    # direct targets; Nietzsche's own *Der Antichrist* title is a
    # polemical echo of Renan's. The *Histoire du peuple d'Israël*
    # (1887-93) is the source for the priestly-class genealogy
    # material Nietzsche reworks as slave-morality in GM I.7-8.
    AuthorMentionRule(
        name="nietzsche_renan",
        target_author="Renan",
        target_work="",
        forms=(
            "Renan",
            "Renans",
            "Ernest Renan",
            "Renanscher",
        ),
        confidence=0.88,
        langs=("deu",),
        note=(
            "Direct target of *Der Antichrist*; cited in GM, GD, EH. "
            "Vie de Jésus + L'Antéchrist + Histoire du peuple d'Israël "
            "all relevant."
        ),
    ),
    AuthorMentionRule(
        name="nietzsche_schiller",
        target_author="Schiller",
        target_work="",
        forms=("Schiller", "Schillers", "Schillersche", "Schillerschen", "schillersch"),
        confidence=0.7,
        langs=("deu",),
        note=(
            "Nietzsche engages Schiller's naive/sentimental distinction "
            "and aesthetic justification across the Birth of Tragedy and "
            "the Untimely Meditations; also GD."
        ),
    ),
)
