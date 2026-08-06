"""Smoke tests for `minerva.refs.rules.locke`.

Locke is ingested as English-only (Essay + Second Treatise of
Government, both 1689). All rules gate on `langs=("eng",)`. Tests
fire representative English passages at the rules and assert the
right Candidate emerges; the dispatcher and insert paths are
covered generically in `test_refs_rules.py`.
"""

from __future__ import annotations

from minerva.refs.rules import ChunkInfo
from minerva.refs.rules.locke import RULES


def _chunk(
    text: str,
    *,
    lang: str = "eng",
    work: str = "An Essay Concerning Human Understanding",
    section: str | None = "Book II, Ch. 1",
) -> ChunkInfo:
    return ChunkInfo(
        chunk_id="t1",
        author="Locke",
        work=work,
        lang=lang,
        section=section,
        text=text,
    )


def _candidates_for(text: str, **kw: object) -> list[tuple[str, str, str]]:
    chunk = _chunk(text, **kw)  # type: ignore[arg-type]
    out: list[tuple[str, str, str]] = []
    for rule in RULES:
        for cand in rule.scan(chunk):
            out.append((rule.name, cand.target_author, cand.source_form_snapshot))
    return out


# ════════════════════════════════════════════════════════════════════
# Mention rules — English forms
# ════════════════════════════════════════════════════════════════════


class TestLockeRules:
    def test_descartes_named(self) -> None:
        cands = _candidates_for("as Descartes hath erroneously supposed in his Meditations")
        assert any(c[1] == "Descartes" and c[2] == "Descartes" for c in cands)

    def test_cartesian_adjective(self) -> None:
        cands = _candidates_for(
            "the Cartesian doctrine of innate ideas falls before this consideration"
        )
        assert any(c[1] == "Descartes" for c in cands)

    def test_hobbes_named(self) -> None:
        cands = _candidates_for("Hobbes hath observed in his Leviathan")
        assert any(c[1] == "Hobbes" and c[2] == "Hobbes" for c in cands)

    def test_aristotle_named(self) -> None:
        cands = _candidates_for("Aristotle taught the doctrine of the syllogism")
        assert any(c[1] == "Aristotle" and c[2] == "Aristotle" for c in cands)

    def test_peripatetic_form(self) -> None:
        cands = _candidates_for("the Peripatetic philosophy hath been overthrown")
        assert any(c[1] == "Aristotle" and c[2] == "Peripatetic" for c in cands)

    def test_judicious_hooker_strong(self) -> None:
        # The Second Treatise epithet — should fire under the
        # strong-mention rule.
        cands = _candidates_for("the judicious Hooker, in his first book of Ecclesiastical Polity")
        assert any(c[0] == "locke_hooker" and c[1] == "Hooker" for c in cands)

    def test_filmer_named(self) -> None:
        cands = _candidates_for("Sir Robert Filmer hath traced the rights of kings from Adam")
        assert any(c[1] == "Filmer" for c in cands)

    def test_patriarcha_work_title(self) -> None:
        cands = _candidates_for("as we may see in the Patriarcha")
        assert any(c[1] == "Filmer" and c[2] == "Patriarcha" for c in cands)

    def test_cicero_named(self) -> None:
        cands = _candidates_for("Cicero in his Offices distinguisheth justice and prudence")
        assert any(c[1] == "Cicero" and c[2] == "Cicero" for c in cands)

    def test_tully_resolves_to_cicero(self) -> None:
        cands = _candidates_for("Tully in this respect agreeth with the ancients")
        assert any(c[1] == "Cicero" and c[2] == "Tully" for c in cands)

    def test_schoolmen_routes_to_aquinas(self) -> None:
        cands = _candidates_for("the Schoolmen, having built much on this distinction")
        assert any(c[0] == "locke_schoolmen" and c[1] == "Aquinas" for c in cands)


# ════════════════════════════════════════════════════════════════════
# Language gating
# ════════════════════════════════════════════════════════════════════


class TestLockeLangFiltering:
    def test_latin_chunk_skipped(self) -> None:
        cands = _candidates_for(
            "ut dixit Cartesius in Meditationibus",
            lang="lat",
        )
        assert cands == []

    def test_french_chunk_skipped(self) -> None:
        cands = _candidates_for(
            "comme l'a écrit Descartes",
            lang="fra",
        )
        assert cands == []
