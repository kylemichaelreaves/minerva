"""Canonical figure surface-form tuples shared across ≥2 author rule modules.

Extracted from the per-author rule modules where the SAME target figure was
cited with the SAME language(s) and the SAME exact surface forms — e.g.
Homer's Greek declensions appeared verbatim in five ancient-Greek modules.
Centralising them removes copy-paste and gives one place to fix a form (#56).

IMPORTANT: these are ONLY sets that were ALREADY identical across modules. Do
NOT fold an author-specific variant in here — the narrower per-source form
lists elsewhere are deliberate precision choices, not accidental divergence;
pooling them would broaden detection and add false positives. A snapshot test
(tests/test_refs_forms_snapshot.py) guards every rule's forms against drift.
"""

from __future__ import annotations

# Aeschylus — eng; shared by aristotle, euripides, plato
AESCHYLUS_ENG: tuple[str, ...] = ("Aeschylus", "Aeschylean")
# Aeschylus — grc; shared by aristotle, euripides, plato
AESCHYLUS_GRC: tuple[str, ...] = ("Αἰσχύλος", "Αἰσχύλου", "Αἰσχύλον", "Αἰσχύλῳ")
# Aeschylus — lat/eng; shared by augustine, cicero
AESCHYLUS_LAT_ENG: tuple[str, ...] = ("Aeschylus", "Aeschyli", "Aeschylum", "Aeschylo")
# Anaxagoras — eng; shared by aristotle, euripides, plato
ANAXAGORAS_ENG: tuple[str, ...] = ("Anaxagoras",)
# Anaxagoras — grc; shared by aristotle, euripides, plato
ANAXAGORAS_GRC: tuple[str, ...] = ("Ἀναξαγόρας", "Ἀναξαγόρου", "Ἀναξαγόραν", "Ἀναξαγόρᾳ")
# Aquinas — eng; shared by hume, locke
AQUINAS_ENG: tuple[str, ...] = ("Schoolmen", "School-men", "Scholastics", "Schoolman")
# Aristotle — deu/eng; shared by hegel, kant
ARISTOTLE_DEU_ENG: tuple[str, ...] = (
    "Aristotle",
    "Aristoteles",
    "Aristotelian",
    "Aristotelische",
    "Aristotelischen",
)
# Aristotle — eng; shared by hume, locke
ARISTOTLE_ENG: tuple[str, ...] = ("Aristotle", "Aristotelian", "Aristotelians", "Peripatetic")
# Aristotle — lat; shared by augustine, spinoza
ARISTOTLE_LAT: tuple[str, ...] = ("Aristoteles", "Aristotelis", "Aristotelem", "Aristotele")
# Chrysippus — grc/eng; shared by epictetus, marcus_aurelius
CHRYSIPPUS_GRC_ENG: tuple[str, ...] = ("Χρύσιππος", "Χρύσιππον", "Χρυσίππου", "Chrysippus")
# Cicero — fra; shared by pascal, renan, rousseau
CICERO_FRA: tuple[str, ...] = ("Cicéron", "Ciceron")
# Cicero — lat; shared by aquinas, augustine
CICERO_LAT: tuple[str, ...] = ("Cicero", "Ciceronis", "Ciceronem", "Cicerone", "Tullius", "Tullii")
# Descartes — eng; shared by hume, locke
DESCARTES_ENG: tuple[str, ...] = ("Descartes", "Cartesian", "Cartesians", "Cartesianism")
# Euripides — eng; shared by aristotle, plato
EURIPIDES_ENG: tuple[str, ...] = ("Euripides", "Euripidean")
# Euripides — grc; shared by aristotle, plato
EURIPIDES_GRC: tuple[str, ...] = ("Εὐριπίδης", "Εὐριπίδου", "Εὐριπίδην", "Εὐριπίδῃ")
# Euripides — lat/eng; shared by augustine, cicero
EURIPIDES_LAT_ENG: tuple[str, ...] = ("Euripides", "Euripidis", "Euripidem", "Euripide")
# Heraclitus — eng; shared by aristotle, plato
HERACLITUS_ENG: tuple[str, ...] = ("Heraclitus", "Heraclitean")
# Heraclitus — grc; shared by aristotle, plato
HERACLITUS_GRC: tuple[str, ...] = ("Ἡράκλειτος", "Ἡρακλείτου", "Ἡράκλειτον", "Ἡρακλείτῳ")
# Hesiod — eng; shared by aeschylus, aristotle, euripides, plato, sophocles
HESIOD_ENG: tuple[str, ...] = ("Hesiod", "Hesiod's")
# Hesiod — grc; shared by aeschylus, aristotle, euripides, plato, sophocles
HESIOD_GRC: tuple[str, ...] = ("Ἡσίοδος", "Ἡσιόδου", "Ἡσίοδον", "Ἡσιόδῳ")
# Hobbes — deu/eng; shared by hegel, kant
HOBBES_DEU_ENG: tuple[str, ...] = ("Hobbes", "Hobbes'", "Hobbesisch", "Hobbesische", "Hobbesischen")
# Hobbes — eng; shared by hume, locke
HOBBES_ENG: tuple[str, ...] = ("Hobbes", "Hobbes's", "Hobbist", "Hobbists", "Hobbesian")
# Homer — eng; shared by aeschylus, aristotle, euripides, plato, sophocles
HOMER_ENG: tuple[str, ...] = ("Homer", "Homer's", "Homeric")
# Homer — grc; shared by aeschylus, aristotle, euripides, plato, sophocles
HOMER_GRC: tuple[str, ...] = ("Ὅμηρος", "Ὁμήρου", "Ὅμηρον", "Ὁμήρῳ")
# Locke — deu/eng; shared by hegel, kant
LOCKE_DEU_ENG: tuple[str, ...] = ("Locke", "Lockes", "Lockesche", "Lockeschen", "lockesch")
# Parmenides — grc; shared by aristotle, plato
PARMENIDES_GRC: tuple[str, ...] = ("Παρμενίδης", "Παρμενίδου", "Παρμενίδην", "Παρμενίδῃ")
# Plato — fra; shared by pascal, rousseau
PLATO_FRA: tuple[str, ...] = ("Platon", "platonicien", "platonicienne", "platoniciens")
# Plato — grc/eng; shared by epictetus, marcus_aurelius
# Πλάτωνι completes the singular paradigm (nom/acc/gen were present, dative
# was not); `origen` already carried it. Not a broadening — same name.
PLATO_GRC_ENG: tuple[str, ...] = ("Πλάτων", "Πλάτωνα", "Πλάτωνος", "Πλάτωνι", "Plato")
# Porphyry — lat; shared by aquinas, augustine
PORPHYRY_LAT: tuple[str, ...] = ("Porphyrius", "Porphyrii", "Porphyrium", "Porphyrio")
# Pythagoras — eng; shared by aristotle, plato
PYTHAGORAS_ENG: tuple[str, ...] = ("Pythagoras", "Pythagorean", "Pythagoreans")
# Pythagoras — grc; shared by aristotle, plato
PYTHAGORAS_GRC: tuple[str, ...] = (
    "Πυθαγόρας",
    "Πυθαγόρου",
    "Πυθαγόραν",
    "Πυθαγόρᾳ",
    "Πυθαγόρειοι",
    "Πυθαγόρειος",
)
# Rousseau — deu/eng; shared by hegel, kant
ROUSSEAU_DEU_ENG: tuple[str, ...] = (
    "Rousseau",
    "Rousseaus",
    "Rousseausche",
    "Rousseauschen",
    "rousseauisch",
)
# Socrates — grc/eng; shared by epictetus, marcus_aurelius
SOCRATES_GRC_ENG: tuple[str, ...] = (
    "Σωκράτης",
    "Σωκράτη",
    "Σωκράτους",
    "Σωκράτει",
    "Socrates",
    "Socratic",
)
# Sophocles — eng; shared by aristotle, plato
SOPHOCLES_ENG: tuple[str, ...] = ("Sophocles", "Sophoclean")
# Sophocles — grc; shared by aristotle, plato
SOPHOCLES_GRC: tuple[str, ...] = ("Σοφοκλῆς", "Σοφοκλέους", "Σοφοκλέα", "Σοφοκλεῖ")
# Sophocles — lat/eng; shared by augustine, cicero
SOPHOCLES_LAT_ENG: tuple[str, ...] = ("Sophocles", "Sophoclis", "Sophoclem", "Sophocle")
# Spinoza — deu; shared by marx, nietzsche
SPINOZA_DEU: tuple[str, ...] = (
    "Spinoza",
    "Spinozas",
    "Spinozismus",
    "spinozistisch",
    "spinozistische",
)
# Spinoza — deu/eng; shared by hegel, kant
SPINOZA_DEU_ENG: tuple[str, ...] = ("Spinoza", "Spinozas", "Spinozism", "Spinozismus")
# Spinoza — eng; shared by hume, locke
SPINOZA_ENG: tuple[str, ...] = ("Spinoza", "Spinozism", "Spinozist", "Spinoza's")
# Theognis — eng; shared by aristotle, plato
THEOGNIS_ENG: tuple[str, ...] = ("Theognis", "Theognidean")
# Theognis — grc; shared by aristotle, plato
THEOGNIS_GRC: tuple[str, ...] = ("Θέογνις", "Θεόγνιδος", "Θεόγνιδι", "Θέογνιν")
