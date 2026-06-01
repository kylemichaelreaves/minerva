"""Smoke tests for `minerva.refs.rules.pascal`.

Pascal is ingested as French-only (Pensées, PG 24499). All rules
gate on `langs=("fra",)`. Tests fire representative French passages
at the rules and assert the right Candidate emerges; the dispatcher
and insert paths are covered generically in `test_refs_rules.py`.
"""

from __future__ import annotations

from minerva.refs.rules import ChunkInfo
from minerva.refs.rules.pascal import RULES


def _chunk(
    text: str,
    *,
    lang: str = "fra",
    work: str = "Pensées",
    section: str | None = "Fragment",
) -> ChunkInfo:
    return ChunkInfo(
        chunk_id="t1",
        author="Pascal",
        work=work,
        lang=lang,
        section=section,
        text=text,
    )


def _candidates_for(text: str, **kw: object) -> list[tuple[str, str, str]]:
    """(rule_name, target_author, surface_form) tuples from every
    Pascal rule that fires on this text."""

    chunk = _chunk(text, **kw)  # type: ignore[arg-type]
    out: list[tuple[str, str, str]] = []
    for rule in RULES:
        for cand in rule.scan(chunk):
            out.append(
                (rule.name, cand.target_author, cand.source_form_snapshot)
            )
    return out


# ════════════════════════════════════════════════════════════════════
# Mention rules — French forms
# ════════════════════════════════════════════════════════════════════


class TestPascalRules:

    def test_augustin_strong_mention(self) -> None:
        cands = _candidates_for(
            "saint Augustin dit que la grâce est gratuite"
        )
        assert any(c[1] == "Augustine" for c in cands)
        # Should fire under the strong-mention rule (rule_strong / 0.9).
        assert any(c[0] == "pascal_augustin" for c in cands)

    def test_augustinien_adjective(self) -> None:
        cands = _candidates_for(
            "la doctrine augustinienne de la prédestination"
        )
        assert any(c[1] == "Augustine" and "augustinien" in c[2].lower() for c in cands)

    def test_descartes_named(self) -> None:
        cands = _candidates_for(
            "Descartes inutile et incertain"
        )
        assert any(c[1] == "Descartes" and c[2] == "Descartes" for c in cands)

    def test_cartesien_accent(self) -> None:
        cands = _candidates_for(
            "le système cartésien échoue sur ce point"
        )
        assert any(c[1] == "Descartes" for c in cands)

    def test_montaigne_named(self) -> None:
        cands = _candidates_for(
            "ce n'est pas dans Montaigne, mais dans moi-même"
        )
        assert any(c[1] == "Montaigne" and c[2] == "Montaigne" for c in cands)

    def test_platon_french_form(self) -> None:
        cands = _candidates_for(
            "Platon écrit dans la République"
        )
        assert any(c[1] == "Plato" and c[2] == "Platon" for c in cands)

    def test_aristote_french_form(self) -> None:
        cands = _candidates_for(
            "ils ont mis tout leur soin à savoir Aristote"
        )
        assert any(c[1] == "Aristotle" and c[2] == "Aristote" for c in cands)

    def test_peripateticien(self) -> None:
        # "péripatéticien" is the standard French term for Aristotelian.
        cands = _candidates_for(
            "les péripatéticiens soutiennent une autre thèse"
        )
        assert any(c[1] == "Aristotle" for c in cands)


# ════════════════════════════════════════════════════════════════════
# Language gating
# ════════════════════════════════════════════════════════════════════


class TestPascalLangFiltering:

    def test_english_chunk_skipped(self) -> None:
        # No Pascal rule should fire on an English chunk — all rules
        # are langs=("fra",).
        cands = _candidates_for(
            "Saint Augustine wrote that grace is gratuitous",
            lang="eng",
        )
        assert cands == []

    def test_latin_chunk_skipped(self) -> None:
        # Likewise for Latin — Pascal's Latin Augustinus quotations
        # don't fire these rules (they'd fire under Augustine's own
        # in-corpus chunks if anywhere).
        cands = _candidates_for(
            "ut dicit Augustinus in De civitate Dei",
            lang="lat",
        )
        assert cands == []
