"""Rules that fire on Marx chunks.

Marx's interlocutors split by work:

* **Hegel** is the central in-corpus interlocutor — the *Kritik der
  Hegel'schen Rechtsphilosophie* is direct; the *Thesen über
  Feuerbach* and *Deutsche Ideologie* extend the same critique; the
  *Kapital* dialectic is self-consciously Hegelian. Strong rule.
* **Feuerbach** — explicit target of the *Thesen* (`Erste These...`
  on Feuerbach) and a sustained section of the *Deutsche Ideologie*.
  Strong rule.
* **Aristoteles** — *Kapital* Bd 1 ch. 1 invokes Aristotle on the
  origin of money and on the difference between use-value and
  exchange-value. The reference frame is the *Politik* and the
  *Nikomachische Ethik*.
* Out-of-corpus targets: **Adam Smith** (Wealth of Nations, the
  classical-economist backdrop for Kapital); **David Ricardo**
  (labor-theory-of-value precursor); **Proudhon** (target of
  *Elend der Philosophie*); **Stirner** (target of the *Sankt Max*
  chapter of *Deutsche Ideologie*); **Bruno Bauer** (target of
  *Heilige Familie*); the utopian socialists **Saint-Simon**,
  **Fourier**, and **Owen** (named in the Manifest).

All rules gate on `langs=("deu",)` — Marx is German-only.
"""

from __future__ import annotations

from . import AuthorMentionRule, StrongMentionRule
from .scripture_cite import default_scripture_rules

RULES = (
    *default_scripture_rules("marx"),

    # Hegel — Marx's central in-corpus interlocutor. Strong rule
    # because every "Hegel" mention in Marx is unambiguously THE
    # Hegel (G.W.F.), not a different person of the same name.
    StrongMentionRule(
        name="marx_hegel",
        target_author="Hegel",
        target_work="",
        forms=(
            "Hegel",
            "Hegels",
            "Hegelsche",
            "Hegelschen",
            "Hegelscher",
            "Hegelsches",
            "Hegelianer",
            "Hegelianern",
            "hegelianisch",
            "hegelianische",
            "hegelianischen",
        ),
        confidence=0.92,
        langs=("deu",),
        note=(
            "Marx's primary German predecessor. Every named "
            "reference is to G.W.F. Hegel; no ambiguity in this corpus."
        ),
    ),

    # Feuerbach — explicit target of Thesen + Deutsche Ideologie.
    StrongMentionRule(
        name="marx_feuerbach",
        target_author="Feuerbach",
        target_work="",
        forms=(
            "Feuerbach",
            "Feuerbachs",
            "Feuerbachsche",
            "Feuerbachschen",
            "feuerbachsch",
            "feuerbachsche",
            "feuerbachschen",
        ),
        confidence=0.9,
        langs=("deu",),
        note=(
            "Ludwig Feuerbach, named target of the 1845 Thesen and "
            "the Feuerbach chapter of the Deutsche Ideologie. "
            "Out-of-corpus target."
        ),
    ),

    # Aristoteles — invoked in Kapital Bd 1 ch. 1 on the form of
    # value. The German form is "Aristoteles" (not "Aristotle").
    AuthorMentionRule(
        name="marx_aristoteles",
        target_author="Aristotle",
        target_work="",
        forms=(
            "Aristoteles",
            "Aristotelisch",
            "Aristotelische",
            "Aristotelischen",
            "aristotelisch",
            "aristotelische",
            "aristotelischen",
        ),
        confidence=0.75,
        langs=("deu",),
    ),

    # Adam Smith — the classical-economist backdrop for Kapital.
    AuthorMentionRule(
        name="marx_smith",
        target_author="Smith",
        target_work="",
        forms=("Adam Smith", "Smithschen", "Smithsche", "Smith's"),
        confidence=0.8,
        langs=("deu",),
        note=(
            "Adam Smith. We use the more-specific phrase 'Adam "
            "Smith' over bare 'Smith' to avoid colliding with the "
            "many other Smiths Marx may name (William Smith, etc.). "
            "Out-of-corpus target."
        ),
    ),

    # David Ricardo — labor-theory-of-value precursor.
    StrongMentionRule(
        name="marx_ricardo",
        target_author="Ricardo",
        target_work="",
        forms=("Ricardo", "Ricardos", "Ricardosche", "Ricardoschen", "Ricardo's"),
        confidence=0.88,
        langs=("deu",),
        note=(
            "David Ricardo, the most-cited classical economist in "
            "Kapital. The German Ricardo references are dense in "
            "Bd 1 chs. 1, 18-19. Out-of-corpus target."
        ),
    ),

    # Proudhon — target of Elend der Philosophie. "Misère de la
    # philosophie" was Marx's German-language reply to Proudhon's
    # "Philosophie de la misère"; the German edition uses "Proudhon"
    # throughout.
    StrongMentionRule(
        name="marx_proudhon",
        target_author="Proudhon",
        target_work="",
        forms=("Proudhon", "Proudhons", "Proudhonsche", "Proudhonschen"),
        confidence=0.92,
        langs=("deu",),
        note=(
            "Pierre-Joseph Proudhon, the named antagonist of Das "
            "Elend der Philosophie. Out-of-corpus target."
        ),
    ),

    # Max Stirner — target of the 'Sankt Max' chapter of Deutsche
    # Ideologie. Marx's polemical references are dense.
    StrongMentionRule(
        name="marx_stirner",
        target_author="Stirner",
        target_work="",
        forms=("Stirner", "Stirners", "Sankt Max", "Stirnersche", "Stirnerschen"),
        confidence=0.9,
        langs=("deu",),
        note=(
            "Max Stirner, *Der Einzige und sein Eigentum*. The "
            "'Sankt Max' chapter of the Deutsche Ideologie is a "
            "sustained refutation. Out-of-corpus target."
        ),
    ),

    # Bruno Bauer — target of Die heilige Familie. "Bauer" alone is
    # too common a German name, so require the disambiguating
    # 'Bruno' or 'B. Bauer' form.
    StrongMentionRule(
        name="marx_bauer",
        target_author="Bauer",
        target_work="",
        forms=("Bruno Bauer", "B. Bauer", "Bruno Bauers"),
        confidence=0.9,
        langs=("deu",),
        note=(
            "Bruno Bauer, principal target of Die heilige Familie. "
            "We require the 'Bruno' qualifier to avoid colliding "
            "with the German common noun 'Bauer' (farmer/peasant) "
            "or other surnamed Bauers Marx mentions. Out-of-corpus."
        ),
    ),

    # Saint-Simon — utopian socialist named in the Manifest.
    AuthorMentionRule(
        name="marx_saint_simon",
        target_author="Saint-Simon",
        target_work="",
        forms=("Saint-Simon", "Saint-Simons", "Saint-Simonsche", "Saint-Simonschen"),
        confidence=0.85,
        langs=("deu",),
    ),

    # Fourier — utopian socialist named in the Manifest.
    AuthorMentionRule(
        name="marx_fourier",
        target_author="Fourier",
        target_work="",
        forms=("Fourier", "Fouriers", "Fouriersche", "Fourierschen"),
        confidence=0.8,
        langs=("deu",),
    ),

    # Owen — utopian socialist named in the Manifest.
    AuthorMentionRule(
        name="marx_owen",
        target_author="Owen",
        target_work="",
        forms=("Owen", "Owens", "Owensche", "Owenschen", "Robert Owen"),
        confidence=0.8,
        langs=("deu",),
    ),

    # Spinoza — Marx's dissertation foreshadows Spinoza's
    # immanent-materialism reading; named references appear in
    # the Heilige Familie and in early letters/notebooks.
    AuthorMentionRule(
        name="marx_spinoza",
        target_author="Spinoza",
        target_work="",
        forms=("Spinoza", "Spinozas", "Spinozismus", "spinozistisch", "spinozistische"),
        confidence=0.85,
        langs=("deu",),
    ),

    # Kant — referenced in the Heilige Familie, the Frühschriften,
    # and as part of Marx's general critique of "German ideology."
    # Less central than Hegel/Feuerbach but explicit.
    AuthorMentionRule(
        name="marx_kant",
        target_author="Kant",
        target_work="",
        forms=("Kant", "Kants", "Kantische", "Kantischen", "Kantianer"),
        confidence=0.8,
        langs=("deu",),
    ),

    # Lucretius — Marx's 1841 doctoral dissertation was on Democritean
    # and Epicurean natural philosophy. The Difference Between the
    # Democritean and Epicurean Philosophy of Nature engages Lucretius
    # directly, and references resurface in the early-1840s notebooks.
    AuthorMentionRule(
        name="marx_lucretius",
        target_author="Lucretius",
        target_work="",
        forms=("Lukrez", "Lucretius", "Lucretian"),
        confidence=0.88,
        langs=("deu",),
        note="Marx's 1841 dissertation engages Lucretius alongside Epicurus.",
    ),

    # Epicurus — primary target of Marx's dissertation. Out-of-corpus.
    AuthorMentionRule(
        name="marx_epicurus",
        target_author="Epicurus",
        target_work="",
        forms=("Epikur", "Epikurs", "Epikureisch", "Epikureische", "Epicurus"),
        confidence=0.9,
        langs=("deu",),
        note="Subject of Marx's 1841 doctoral dissertation. Out-of-corpus.",
    ),

    # Democritus — co-equal subject of Marx's 1841 dissertation (full
    # title: *The Difference Between the Democritean and Epicurean
    # Philosophy of Nature*). The preparatory *Hefte zur epikureischen
    # Philosophie* engage Democritus throughout. Out-of-corpus.
    AuthorMentionRule(
        name="marx_democritus",
        target_author="Democritus",
        target_work="",
        forms=(
            "Demokrit",
            "Demokrits",
            "Demokriteisch",
            "Demokritisch",
            "Demokritischen",
            "Democritus",
            "Democritean",
        ),
        confidence=0.9,
        langs=("deu",),
        note="Co-equal subject of Marx's 1841 doctoral dissertation. Out-of-corpus.",
    ),

    # Aesop — *18th Brumaire of Louis Bonaparte* (1852) chapter 1
    # famously reuses Hegel's "Hic Rhodus, hic salta" — which is in
    # turn a Latinisation of Aesop's *Boastful Athlete* fable. So Marx
    # inherits the Aesop reference via Hegel; the form set is shared.
    AuthorMentionRule(
        name="marx_aesop",
        target_author="Aesop",
        target_work="",
        forms=("Äsop", "Äsops", "Aesop", "Hic Rhodus"),
        confidence=0.85,
        langs=("deu",),
        note=(
            "18th Brumaire ch.1 reuses Hegel's 'Hic Rhodus, hic salta' "
            "rendering of Aesop's Boastful Athlete fable."
        ),
    ),

    AuthorMentionRule(
        name="marx_schiller",
        target_author="Schiller",
        target_work="",
        forms=("Schiller", "Schillers", "Schillersche", "Schillerschen"),
        confidence=0.55,
        langs=("deu",),
        note=(
            "Marx quotes Schiller's poetry and invokes the aesthetic "
            "critique of alienation; weaker, mostly literary allusion."
        ),
    ),
)
