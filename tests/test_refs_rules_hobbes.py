"""Smoke tests for `minerva.refs.rules.hobbes`.

The Hobbes rules cover both English (1651/1650 editions) and Latin
(1668 Leviathan, 1642 De Cive) surface forms for the principal
interlocutors. Each test fires a representative passage at the rules
and asserts the right Candidate emerges. We don't exercise the
dispatcher / insert path here — generic coverage lives in
``test_refs_rules.py``.
"""

from __future__ import annotations

from minerva.refs.rules import ChunkInfo
from minerva.refs.rules.hobbes import RULES


def _chunk(
    text: str,
    *,
    lang: str = "eng",
    work: str = "Leviathan",
    section: str | None = "Ch 13",
) -> ChunkInfo:
    return ChunkInfo(
        chunk_id="t1",
        author="Hobbes",
        work=work,
        lang=lang,
        section=section,
        text=text,
    )


def _candidates_for(text: str, **kw: object) -> list[tuple[str, str, str]]:
    """Return (rule_name, target_author, surface_form) tuples for
    every Candidate emitted across all Hobbes rules on this text."""

    chunk = _chunk(text, **kw)  # type: ignore[arg-type]
    out: list[tuple[str, str, str]] = []
    for rule in RULES:
        for cand in rule.scan(chunk):
            out.append(
                (rule.name, cand.target_author, cand.source_form_snapshot)
            )
    return out


# ════════════════════════════════════════════════════════════════════
# English forms
# ════════════════════════════════════════════════════════════════════


class TestHobbesEnglish:

    def test_aristotle_named(self) -> None:
        cands = _candidates_for(
            "as Aristotle saith in his Politiques",
            lang="eng",
        )
        assert any(c[1] == "Aristotle" and c[2] == "Aristotle" for c in cands)

    def test_stagirite_periphrasis(self) -> None:
        # Hobbes occasionally calls Aristotle "the Stagirite".
        cands = _candidates_for(
            "the Stagirite affirmeth that man is by nature a politicall creature",
            lang="eng",
        )
        assert any(c[1] == "Aristotle" and c[2] == "Stagirite" for c in cands)

    def test_tully_resolves_to_cicero(self) -> None:
        cands = _candidates_for(
            "Tully in his Offices defendeth the contrary",
            lang="eng",
        )
        assert any(c[1] == "Cicero" and c[2] == "Tully" for c in cands)

    def test_cicero_named(self) -> None:
        cands = _candidates_for(
            "Cicero distinguisheth between honestum and utile",
            lang="eng",
        )
        assert any(c[1] == "Cicero" and c[2] == "Cicero" for c in cands)

    def test_plato_named(self) -> None:
        cands = _candidates_for(
            "Plato was of all the philosophers the greatest",
            lang="eng",
        )
        assert any(c[1] == "Plato" and c[2] == "Plato" for c in cands)

    def test_schoolmen_routes_to_aquinas(self) -> None:
        cands = _candidates_for(
            "the Schoolmen built upon Aristotle's metaphysics",
            lang="eng",
        )
        # The Schoolmen rule emits — and a separate Aristotle rule
        # also emits for the trailing "Aristotle".
        assert any(c[0] == "hobbes_schoolmen" and c[1] == "Aquinas" for c in cands)

    def test_thucydides_strong_mention(self) -> None:
        cands = _candidates_for(
            "Thucydides describeth the plague of Athens",
            lang="eng",
        )
        assert any(c[1] == "Thucydides" for c in cands)


# ════════════════════════════════════════════════════════════════════
# Latin forms
# ════════════════════════════════════════════════════════════════════


class TestHobbesLatin:

    def test_aristoteles_declined(self) -> None:
        cands = _candidates_for(
            "ut docet Aristoteles in libro de Anima",
            lang="lat",
            work="Leviathan",
        )
        assert any(c[1] == "Aristotle" and c[2] == "Aristoteles" for c in cands)

    def test_aristotelis_genitive(self) -> None:
        cands = _candidates_for(
            "contra sententiam Aristotelis qui dixit",
            lang="lat",
        )
        assert any(c[1] == "Aristotle" and c[2] == "Aristotelis" for c in cands)

    def test_platonis_declined(self) -> None:
        cands = _candidates_for(
            "in Platonis Republica scribitur",
            lang="lat",
        )
        assert any(c[1] == "Plato" and c[2] == "Platonis" for c in cands)

    def test_cicero_lat(self) -> None:
        cands = _candidates_for(
            "Cicero in libro de Officiis disputat",
            lang="lat",
        )
        assert any(c[1] == "Cicero" and c[2] == "Cicero" for c in cands)

    def test_cartesius_resolves_to_descartes(self) -> None:
        cands = _candidates_for(
            "ut autem dicit Cartesius in Meditationibus",
            lang="lat",
        )
        assert any(c[1] == "Descartes" and c[2] == "Cartesius" for c in cands)


# ════════════════════════════════════════════════════════════════════
# Language gating
# ════════════════════════════════════════════════════════════════════


class TestHobbesLangFiltering:

    def test_english_only_rule_skips_latin(self) -> None:
        # "Schoolmen" is English-only; a Latin chunk shouldn't fire it.
        cands = _candidates_for(
            "Schoolmen dicunt aliter, sed nos contradicimus",
            lang="lat",
        )
        assert not any(c[0] == "hobbes_schoolmen" for c in cands)

    def test_latin_only_rule_skips_english(self) -> None:
        # "Aristotelis" is Latin-only; an English chunk shouldn't fire it.
        cands = _candidates_for(
            "Aristotelis is the Latin genitive form",
            lang="eng",
        )
        assert not any(c[0] == "hobbes_aristotle_lat" for c in cands)

    def test_thucydides_fires_in_both_langs(self) -> None:
        # langs=() means "all languages" — Thucydides should fire in
        # both English and Latin.
        for lang in ("eng", "lat"):
            cands = _candidates_for(
                "Thucydides scripsit hoc",
                lang=lang,
            )
            assert any(c[1] == "Thucydides" for c in cands), f"failed for lang={lang}"
