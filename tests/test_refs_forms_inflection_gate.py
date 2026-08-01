"""Gate against accidental inflectional-form drift between author rule modules.

Adding author N to the corpus means hand-writing `refs/rules/n.py` AND
auditing every existing author's rules for incoming mentions of N (see
`docs/INGESTION.md`). That audit is O(N²) by hand, and the failure mode is
quiet: two modules cite the SAME target author in the SAME language, but one
lists `platonische` and the other only `Platonische`. Matching is
case-sensitive and anchored `\\b(?:…)(?!\\w)`, so the second module silently
misses every lowercase occurrence. ~500 cross-references went missing this
way before the gap was noticed manually.

This test makes that class of gap fail the build instead of being found by
audit. It flags a rule when a SIBLING rule (same `target_author`, same
language) lists a form whose ASCII-folded alphabetic stem the rule ALREADY
matches — i.e. a different inflection or capitalisation of a name the rule
demonstrably knows about.

What it deliberately does NOT flag:

  * Author-specific vocabulary. Hobbes calls the Schoolmen "Schoolmen" where
    Hegel writes "Thomas von Aquin"; the stems differ, so no report. This is
    the precision philosophy `_figures.py` documents — narrower per-source
    form lists are deliberate, and pooling them would add false positives.
  * Deliberate in-corpus-host routings. `renan`'s "Celse" → `target_author`
    "Origen" and `descartes`'s "Socrate" → "Plato" survive because the stem
    test never matches an unrelated name.
  * Genuine inflection where the ENDING changes, e.g. the Greek dative
    `Πλάτωνι` against a nominative `Πλάτων`. Stems must match EXACTLY.

That last exclusion is a deliberate precision-over-recall choice. A
common-prefix heuristic was tried and rejected: it raised 681 reports (vs 38)
and its highest-volume suggestions were wrong in ways that would have
corrupted the graph — it wanted `augustine_platonici` to absorb "Plato",
which would double-count against the separate `augustine_plato` rule, and it
treated `Christentum` (Christianity, the religion) as an inflection of
`christlich` for a person-target. A build gate that cries wolf gets muted, so
this one only reports variants it can be sure about: same letters, different
case/diacritics/punctuation. Ending-level gaps stay a manual review job.

`EXEMPT` holds pairs where the omission is CORRECT because the form does not
occur in that author's ingested text — adding it would be dead weight that
can never match. Each entry was verified against `data/index.sqlite` with a
case-sensitive `\\b(?:form)(?!\\w)` scan over that author's chunks in that
language. The corpus is far too large to query from a unit test, hence the
static list.

To re-derive EXEMPT after an ingest or a rules change, scan each candidate
against the corpus and keep only the zero-hit ones:

    SELECT text FROM chunks_full WHERE author=? AND lang=? AND text LIKE ?

A NEW entry appearing here is the signal to act: check whether the form
occurs in that author's corpus. If it does, add it to the rule. If it does
not, add it to EXEMPT with that fact recorded.
"""

from __future__ import annotations

import importlib
import pkgutil
import unicodedata
from collections import defaultdict
from pathlib import Path

import minerva.refs.rules as R

# (module, rule_name, lang, form) — form is absent from the rule ON PURPOSE
# because it has zero case-sensitive occurrences in that author's chunks for
# that language. Verified 2026-07-24 against data/index.sqlite (428,601
# chunks). Mostly German adjectival case-variants and English/Greek
# possessive-or-dative forms that a sibling module needs and this one doesn't.
EXEMPT: frozenset[tuple[str, str, str, str]] = frozenset(
    {
        ("hegel", "hegel_aeschylus", "deu", "Aischylos'"),
        ("hegel", "hegel_aeschylus", "deu", "Äschylus'"),
        ("hegel", "hegel_aristotle", "deu", "aristotelische"),
        ("hegel", "hegel_aristotle", "deu", "aristotelischen"),
        ("hegel", "hegel_democritus", "deu", "demokritisch"),
        ("hegel", "hegel_euripides", "deu", "Euripides'"),
        ("hegel", "hegel_kant", "deu", "Kantisch"),
        ("hegel", "hegel_sophocles", "deu", "Sophokles'"),
        ("hume", "hume_berkeley", "eng", "Berkeleys"),
        ("hume", "hume_hobbes", "eng", "Hobbes'"),
        ("hume", "hume_locke", "eng", "Lockes"),
        ("hume", "hume_newton", "eng", "Newtons"),
        ("hume", "hume_spinoza", "eng", "Spinozas"),
        ("kant", "kant_aristotle", "deu", "aristotelische"),
        ("kant", "kant_aristotle", "deu", "aristotelischen"),
        ("kant", "kant_berkeley", "eng", "Berkeley's"),
        ("kant", "kant_descartes", "deu", "cartesianisch"),
        ("kant", "kant_locke", "deu", "Locke's"),
        ("kant", "kant_locke", "eng", "Locke's"),
        ("kant", "kant_spinoza", "deu", "Spinoza's"),
        ("kant", "kant_spinoza", "eng", "Spinoza's"),
        ("locke", "locke_hobbes", "eng", "Hobbes'"),
        ("locke", "locke_spinoza", "eng", "Spinozas"),
        ("marx", "marx_democritus", "deu", "demokritisch"),
        ("marx", "marx_spinoza", "deu", "Spinoza's"),
        ("nietzsche", "nietzsche_aristoteles", "deu", "Aristotelisch"),
        ("nietzsche", "nietzsche_aristoteles", "deu", "Aristotelische"),
        ("nietzsche", "nietzsche_aristoteles", "deu", "Aristotelischen"),
        ("nietzsche", "nietzsche_democritus", "deu", "Demokritisch"),
        ("nietzsche", "nietzsche_euripides", "deu", "Euripideisch"),
        ("nietzsche", "nietzsche_plato", "deu", "Platonisch"),
        ("nietzsche", "nietzsche_spinoza", "deu", "Spinoza's"),
        ("renan", "renan_augustin", "fra", "Augustinien"),
        ("renan", "renan_epictete", "fra", "Épictete"),
        ("schiller", "schiller_aristotle", "deu", "aristotelisch"),
        ("schiller", "schiller_aristotle", "deu", "aristotelische"),
        ("schiller", "schiller_aristotle", "deu", "aristotelischen"),
        ("schiller", "schiller_plato", "deu", "platonisch"),
    }
)


def _stem(form: str) -> str:
    """Strip case, diacritics and punctuation; keep letters of any script.

    `Platonische` / `platonische` → `platonische`; `Äschylus` /
    `Äschylus'` → `aschylus`; `Πλάτων` → `πλατων`. Greek and Cyrillic
    letters survive — an earlier version ASCII-encoded here, which
    silently collapsed every Greek form to the empty string and made
    non-Latin scripts invisible to this gate.
    """

    decomposed = unicodedata.normalize("NFD", form)
    decomposed = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in decomposed.casefold() if c.isalpha())


def _rules() -> list[dict]:
    pkgdir = str(Path(R.__file__).parent)
    mods = [
        n
        for _, n, _ in pkgutil.iter_modules([pkgdir])
        if n not in ("__init__", "loader", "_figures")
    ]
    out: list[dict] = []
    for m in sorted(mods):
        mod = importlib.import_module(f"minerva.refs.rules.{m}")
        for rule in getattr(mod, "RULES", ()):
            forms = getattr(rule, "forms", None)
            if not forms:
                continue
            out.append(
                {
                    "module": m,
                    "name": getattr(rule, "name", None),
                    "author": getattr(rule, "target_author", None),
                    "langs": tuple(getattr(rule, "langs", ()) or ()),
                    "forms": frozenset(forms),
                }
            )
    return out


def _divergences() -> set[tuple[str, str, str, str]]:
    """Return (module, rule, lang, missing_form) for every inflection gap."""

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in _rules():
        # A rule with no explicit langs applies everywhere; bucket it under
        # "*" so it is only ever compared with other unrestricted rules.
        for lang in r["langs"] or ("*",):
            groups[(r["author"], lang)].append(r)

    found: set[tuple[str, str, str, str]] = set()
    for (_author, lang), siblings in groups.items():
        if len(siblings) < 2:
            continue
        for rule in siblings:
            mine = rule["forms"]
            my_stems = {s for s in (_stem(f) for f in mine) if s}
            for other in siblings:
                if other is rule:
                    continue
                for form in other["forms"] - mine:
                    if _stem(form) in my_stems:
                        found.add((rule["module"], rule["name"], lang, form))
    return found


def test_no_unexplained_inflection_gaps() -> None:
    """Every same-author/same-language inflection gap is either fixed or EXEMPT."""

    unexplained = sorted(_divergences() - EXEMPT)
    assert not unexplained, (
        "Rule(s) omit an inflection of a name they already match, and the "
        "omission is not recorded in EXEMPT. For each entry below, check "
        "whether the form occurs in that author's ingested text:\n"
        "  SELECT text FROM chunks_full WHERE author=? AND lang=? AND text LIKE ?\n"
        "If it occurs, add the form to the rule. If it does not, add the "
        "entry to EXEMPT noting that it has zero occurrences.\n"
        + "\n".join(f"  {m}.{n} [{lang}] missing {f!r}" for m, n, lang, f in unexplained)
    )


def test_exempt_list_has_no_stale_entries() -> None:
    """EXEMPT must not outlive the divergence it explains.

    Without this, an entry lingers after someone adds the form to the rule
    (or deletes the rule), and the allowlist slowly stops describing reality.
    """

    stale = sorted(EXEMPT - _divergences())
    assert not stale, (
        "EXEMPT entries no longer correspond to a real divergence — the form "
        "was added to the rule, or the rule/sibling was removed. Delete "
        "them:\n" + "\n".join(f"  {m}.{n} [{lang}] {f!r}" for m, n, lang, f in stale)
    )
