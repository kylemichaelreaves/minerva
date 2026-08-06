"""Smoke tests for the four ancient-quartet rule modules.

Consolidated rather than one-per-file because the rules are small
and the test shape is uniform — each rule fires on a representative
fragment of source text in its target language; language gating
filters chunks in the wrong language.
"""

from __future__ import annotations

from minerva.refs.rules import ChunkInfo
from minerva.refs.rules.cicero import RULES as CICERO_RULES
from minerva.refs.rules.epictetus import RULES as EPICTETUS_RULES
from minerva.refs.rules.lucretius import RULES as LUCRETIUS_RULES
from minerva.refs.rules.marcus_aurelius import RULES as MA_RULES


def _hits(rules, text, *, lang, author):
    chunk = ChunkInfo(
        chunk_id="t1",
        author=author,
        work="Test",
        lang=lang,
        section=None,
        text=text,
    )
    out = []
    for r in rules:
        for c in r.scan(chunk):
            out.append((r.name, c.target_author, c.source_form_snapshot))
    return out


# ════════════════════════════════════════════════════════════════════
# Cicero (Lat + Eng)
# ════════════════════════════════════════════════════════════════════


class TestCicero:
    def test_plato_lat(self) -> None:
        hits = _hits(CICERO_RULES, "ut docet Platonis Republica", lang="lat", author="Cicero")
        assert any(h[1] == "Plato" for h in hits)

    def test_aristotle_eng(self) -> None:
        hits = _hits(
            CICERO_RULES, "as Aristotle teaches in his Ethics", lang="eng", author="Cicero"
        )
        assert any(h[1] == "Aristotle" for h in hits)

    def test_epicurus_polemic(self) -> None:
        hits = _hits(CICERO_RULES, "contra Epicuri sententiam", lang="lat", author="Cicero")
        assert any(h[1] == "Epicurus" for h in hits)

    def test_carneades_named(self) -> None:
        hits = _hits(CICERO_RULES, "Carneades disputat aliter", lang="lat", author="Cicero")
        assert any(h[1] == "Carneades" for h in hits)

    def test_lang_gates_skip_grc(self) -> None:
        # Cicero shouldn't fire on Greek chunks.
        hits = _hits(CICERO_RULES, "Πλάτων δοκεῖ", lang="grc", author="Cicero")
        assert hits == []


# ════════════════════════════════════════════════════════════════════
# Lucretius (Lat + Eng)
# ════════════════════════════════════════════════════════════════════


class TestLucretius:
    def test_epicurus_strong(self) -> None:
        hits = _hits(
            LUCRETIUS_RULES,
            "Graius homo mortales primus tollere contra",
            lang="lat",
            author="Lucretius",
        )
        assert any(h[1] == "Epicurus" and "Graius homo" in h[2] for h in hits)

    def test_empedocles(self) -> None:
        hits = _hits(
            LUCRETIUS_RULES, "as Empedocles of Acragas taught", lang="eng", author="Lucretius"
        )
        assert any(h[1] == "Empedocles" for h in hits)

    def test_heraclitus(self) -> None:
        hits = _hits(
            LUCRETIUS_RULES,
            "clarus ob obscuram linguam magis inter inanes Heraclitus",
            lang="lat",
            author="Lucretius",
        )
        assert any(h[1] == "Heraclitus" for h in hits)


# ════════════════════════════════════════════════════════════════════
# Epictetus (Grc + Eng)
# ════════════════════════════════════════════════════════════════════


class TestEpictetus:
    def test_socrates_grc(self) -> None:
        hits = _hits(EPICTETUS_RULES, "ὁ Σωκράτης ἔλεγεν", lang="grc", author="Epictetus")
        assert any(h[1] == "Socrates" for h in hits)

    def test_diogenes_eng(self) -> None:
        hits = _hits(
            EPICTETUS_RULES, "Diogenes the Cynic refused alike", lang="eng", author="Epictetus"
        )
        assert any(h[1] == "Diogenes" for h in hits)

    def test_chrysippus_grc(self) -> None:
        hits = _hits(EPICTETUS_RULES, "ὥσπερ ὁ Χρύσιππος γράφει", lang="grc", author="Epictetus")
        assert any(h[1] == "Chrysippus" for h in hits)

    def test_lang_gates_skip_lat(self) -> None:
        hits = _hits(EPICTETUS_RULES, "Socrates docet", lang="lat", author="Epictetus")
        assert hits == []


# ════════════════════════════════════════════════════════════════════
# Marcus Aurelius (Grc + Eng)
# ════════════════════════════════════════════════════════════════════


class TestMarcusAurelius:
    def test_epictetus_strong(self) -> None:
        hits = _hits(MA_RULES, "as Epictetus teaches", lang="eng", author="Marcus Aurelius")
        assert any(h[1] == "Epictetus" for h in hits)

    def test_socrates_grc(self) -> None:
        hits = _hits(MA_RULES, "ὁ Σωκράτης παράδειγμα", lang="grc", author="Marcus Aurelius")
        assert any(h[1] == "Socrates" for h in hits)

    def test_heraclitus(self) -> None:
        hits = _hits(
            MA_RULES, "Heraclitus says the cosmos flows", lang="eng", author="Marcus Aurelius"
        )
        assert any(h[1] == "Heraclitus" for h in hits)
