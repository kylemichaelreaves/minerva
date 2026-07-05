"""Canonical work titles for Plato — the single source of truth shared by
the TEI parser (``tei.py``), the title-canonicalization migration, and the
German "Platon: die Werke" splitter.

Convention (2026-07-05): a Greek author's canonical ``works.title`` is the
**Latinized-Greek** name of the work (Euthyphron, Politikos, Symposion,
Politeia, Nomoi, Epistole I–XIII). Each edition/translation keeps its own
*local* title as subordinate display (English "Euthyphro", the German
title), stored in ``editions.title_local`` / ``translations.title_local``.

Today the corpus stores Greek dialogues under beta-code titles
(``*eu)qu/frwn``) and English under anglicized titles (``Euthyphro``), so
they resolve to *separate* ``works`` rows. Mapping every raw title to one
canonical name unifies them: one work per dialogue with a Greek edition,
an English translation, and (once ingested) a German translation — which
is what the reader's edition switcher / parallel-compare needs.
"""

from __future__ import annotations

# (canonical, beta_code_grc, english) for the 32 dialogues stored split
# across a beta-code Greek work and an anglicized English work.
_SPLIT: tuple[tuple[str, str, str], ...] = (
    ("Euthyphron", "*eu)qu/frwn", "Euthyphro"),
    ("Apologia", "*a)pologi/a *swkra/tous", "Apology"),
    ("Kriton", "*kri/twn", "Crito"),
    ("Phaidon", "*fai/dwn", "Phaedo"),
    ("Kratylos", "*kratu/los", "Cratylus"),
    ("Theaitetos", "*qeai/thtos", "Theaetetus"),
    ("Sophistes", "*sofisth/s", "Sophist"),
    ("Politikos", "*politiko/s", "Statesman"),
    ("Parmenides", "*parmeni/dhs", "Parmenides"),
    ("Philebos", "*fi/lhbos", "Philebus"),
    ("Symposion", "*sumposi/on", "Symposium"),
    ("Phaidros", "*fai=dros", "Phaedrus"),
    ("Alkibiades I", "*)alkibia/dhs a", "Alcibiades 1"),
    ("Alkibiades II", "*)alkibia/dhs b", "Alcibiades 2"),
    ("Hipparchos", "*(ippa/rxos", "Hipparchus"),
    ("Erastai", "*e)rastai/", "Lovers"),
    ("Theages", "*qea/ghs", "Theages"),
    ("Charmides", "*xarmi/dhs", "Charmides"),
    ("Laches", "*la/xhs", "Laches"),
    ("Lysis", "*lu/sis", "Lysis"),
    ("Euthydemos", "*eu)qu/dhmos", "Euthydemus"),
    ("Protagoras", "*prwtago/ras", "Protagoras"),
    ("Gorgias", "*gorgi/as", "Gorgias"),
    ("Menon", "*me/nwn", "Meno"),
    ("Hippias Meizon", "*(ippi/as meizw/n", "Hippias Major"),
    ("Hippias Elatton", "*(ippi/as *e)lattw/n", "Hippias Minor"),
    ("Ion", "*)/iwn", "Ion"),
    ("Menexenos", "*mene/cenos", "Menexenus"),
    ("Kleitophon", "*kleito/fwn", "Cleitophon"),
    ("Timaios", "*ti/maios", "Timaeus"),
    ("Kritias", "*kriti/as", "Critias"),
    ("Minos", "*mi/nws", "Minos"),
    ("Epinomis", "*e)pi/nomis", "Epinomis, or Nocturnal Council"),
)

# Works ALREADY unified under one (English) title across languages —
# just renamed to canonical Latinized-Greek. (canonical, current_title, english_local)
_UNIFIED: tuple[tuple[str, str, str], ...] = (
    ("Politeia", "Republic", "Republic"),
    ("Nomoi", "Laws", "Laws"),
)

_ROMAN = (
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII",
    "IX", "X", "XI", "XII", "XIII",
)
# The 13 Letters: canonical "Epistole VII" ↔ current/English "Letter 7".
_LETTERS: tuple[tuple[str, str, str], ...] = tuple(
    (f"Epistole {_ROMAN[i - 1]}", f"Letter {i}", f"Letter {i}") for i in range(1, 14)
)


# ── derived lookups ────────────────────────────────────────────────────
CANONICAL: tuple[str, ...] = tuple(
    c for c, *_ in (*_SPLIT, *_UNIFIED, *_LETTERS)
)

# every raw stored title (beta-code grc OR anglicized/current eng) → canonical
ALIASES: dict[str, str] = {}
# canonical → English local (subordinate) title
LOCAL_EN: dict[str, str] = {}
for _canon, _raw_grc, _en in _SPLIT:
    ALIASES[_raw_grc] = _canon
    ALIASES[_en] = _canon
    LOCAL_EN[_canon] = _en
for _canon, _cur, _en in (*_UNIFIED, *_LETTERS):
    ALIASES[_cur] = _canon
    LOCAL_EN[_canon] = _en

# German edition heading (UPPERCASE, from the PDF's tetralogy index) → canonical.
# The splitter matches its dialogue headings against this. Alkibiades I/II are
# disambiguated by the splitter (two "ALKIBIADES" headings in reading order).
GERMAN_HEADINGS: dict[str, str] = {
    "EUTHYPHRON": "Euthyphron",
    "APOLOGIA SOCRATIS": "Apologia",
    "APOLOGIA": "Apologia",
    "KRITON": "Kriton",
    "PHAIDON": "Phaidon",
    "KRATYLOS": "Kratylos",
    "THEAITETOS": "Theaitetos",
    "SOPHISTES": "Sophistes",
    "POLITIKOS": "Politikos",
    "PARMENIDES": "Parmenides",
    "PHILEBOS": "Philebos",
    "SYMPOSION": "Symposion",
    "PHAIDROS": "Phaidros",
    "HIPPARCHOS": "Hipparchos",
    "AMATORES": "Erastai",
    "ERASTAI": "Erastai",
    "THEAGES": "Theages",
    "CHARMIDES": "Charmides",
    "LACHES": "Laches",
    "LYSIS": "Lysis",
    "EUTHYDEMOS": "Euthydemos",
    "PROTAGORAS": "Protagoras",
    "GORGIAS": "Gorgias",
    "MENON": "Menon",
    "HIPPIAS MAIOR": "Hippias Meizon",
    "HIPPIAS MINOR": "Hippias Elatton",
    "ION": "Ion",
    "MENEXENOS": "Menexenos",
    "KLEITOPHON": "Kleitophon",
    "POLITEIA": "Politeia",
    "TIMAIOS": "Timaios",
    "KRITIAS": "Kritias",
    "MINOS": "Minos",
    "NOMOI": "Nomoi",
    "EPINOMIS": "Epinomis",
}


def canonical_for(raw_title: str | None) -> str | None:
    """Map a raw stored/heading title to its canonical Latinized-Greek
    name, or ``None`` when unknown (caller keeps the raw title)."""
    if not raw_title:
        return None
    if raw_title in ALIASES:
        return ALIASES[raw_title]
    key = " ".join(raw_title.upper().rstrip(".").split())
    return GERMAN_HEADINGS.get(key)


def local_title(canonical: str, lang: str) -> str | None:
    """Subordinate per-edition display title. English gets its anglicized
    title; the Greek original and German render the canonical name, so
    they have no local override (``None``)."""
    if lang == "eng":
        return LOCAL_EN.get(canonical)
    return None
