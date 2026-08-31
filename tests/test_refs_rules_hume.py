"""Smoke tests for `minerva.refs.rules.hume`.

Hume is ingested as English-only (Treatise of Human Nature + Enquiry
Concerning Human Understanding). All rules gate on `langs=("eng",)`.
Tests fire representative English passages and assert the right
Candidate emerges; dispatcher and insert paths are covered
generically in `test_refs_rules.py`.
"""

from __future__ import annotations

from minerva.refs.rules import ChunkInfo
from minerva.refs.rules.hume import RULES


def _chunk(
    text: str,
    *,
    lang: str = "eng",
    work: str = "A Treatise of Human Nature",
    section: str | None = "Book I, Part i, Sect. 1",
) -> ChunkInfo:
    return ChunkInfo(
        chunk_id="t1",
        author="Hume",
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


class TestHumeRules:
    def test_locke_named(self) -> None:
        cands = _candidates_for("as Mr. Locke hath shown in his Essay")
        assert any(c[1] == "Locke" for c in cands)

    def test_berkeley_named(self) -> None:
        cands = _candidates_for("Dr. Berkeley has, I think, demonstrated this point")
        assert any(c[1] == "Berkeley" and c[2] == "Berkeley" for c in cands)

    def test_descartes_named(self) -> None:
        cands = _candidates_for("the celebrated doctrine of Descartes concerning innate ideas")
        assert any(c[1] == "Descartes" for c in cands)

    def test_cartesian_adjective(self) -> None:
        cands = _candidates_for("Cartesian doubt is universal in its application")
        assert any(c[1] == "Descartes" for c in cands)

    def test_hobbes_named(self) -> None:
        cands = _candidates_for("Mr. Hobbes hath argued the contrary in his Leviathan")
        assert any(c[1] == "Hobbes" and c[2] == "Hobbes" for c in cands)

    def test_newton_strong_mention(self) -> None:
        cands = _candidates_for("the chief glory of Sir Isaac Newton, in his philosophy")
        assert any(c[0] == "hume_newton" and c[1] == "Newton" for c in cands)

    def test_newtonian_method(self) -> None:
        cands = _candidates_for("by introducing the Newtonian philosophy into the moral sciences")
        assert any(c[1] == "Newton" and c[2] == "Newtonian" for c in cands)

    def test_cicero_named(self) -> None:
        cands = _candidates_for("Cicero, in his treatise on the duties of magistrates")
        assert any(c[1] == "Cicero" and c[2] == "Cicero" for c in cands)

    def test_aristotle_named(self) -> None:
        cands = _candidates_for("the doctrine of substances borrowed from Aristotle")
        assert any(c[1] == "Aristotle" and c[2] == "Aristotle" for c in cands)

    def test_schoolmen_routes_to_aquinas(self) -> None:
        cands = _candidates_for("the subtle distinctions of the Schoolmen on this head")
        assert any(c[0] == "hume_schoolmen" and c[1] == "Aquinas" for c in cands)

    def test_spinoza_named(self) -> None:
        cands = _candidates_for("the hideous hypothesis of Spinoza concerning the substance")
        assert any(c[1] == "Spinoza" and c[2] == "Spinoza" for c in cands)


# ════════════════════════════════════════════════════════════════════
# Language gating
# ════════════════════════════════════════════════════════════════════


class TestHumeLangFiltering:
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
