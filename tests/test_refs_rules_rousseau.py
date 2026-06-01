"""Smoke tests for `minerva.refs.rules.rousseau`.

Rousseau is ingested as French-only (Du contrat social, 1762). All
rules gate on `langs=("fra",)`. Tests fire representative French
passages and assert the right Candidate emerges; dispatcher and
insert paths are covered generically in `test_refs_rules.py`.
"""

from __future__ import annotations

from minerva.refs.rules import ChunkInfo
from minerva.refs.rules.rousseau import RULES


def _chunk(
    text: str,
    *,
    lang: str = "fra",
    work: str = "Du contrat social",
    section: str | None = "Livre I, Chapitre 1",
) -> ChunkInfo:
    return ChunkInfo(
        chunk_id="t1",
        author="Rousseau",
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
            out.append(
                (rule.name, cand.target_author, cand.source_form_snapshot)
            )
    return out


# ════════════════════════════════════════════════════════════════════
# Mention rules — French forms
# ════════════════════════════════════════════════════════════════════


class TestRousseauRules:

    def test_hobbes_named(self) -> None:
        cands = _candidates_for(
            "Hobbes a fondé sa théorie sur cette même supposition"
        )
        assert any(c[1] == "Hobbes" for c in cands)

    def test_grotius_strong_mention(self) -> None:
        cands = _candidates_for(
            "Grotius soutient que les peuples peuvent s'aliéner à un roi"
        )
        assert any(c[0] == "rousseau_grotius" and c[1] == "Grotius" for c in cands)

    def test_locke_named(self) -> None:
        cands = _candidates_for(
            "comme Locke l'a démontré dans son traité du gouvernement"
        )
        assert any(c[1] == "Locke" for c in cands)

    def test_aristote_named(self) -> None:
        cands = _candidates_for(
            "Aristote prétendait que les hommes ne sont point naturellement égaux"
        )
        assert any(c[1] == "Aristotle" and c[2] == "Aristote" for c in cands)

    def test_platon_named(self) -> None:
        cands = _candidates_for(
            "Platon, dans son Politique, soutient une opinion semblable"
        )
        assert any(c[1] == "Plato" and c[2] == "Platon" for c in cands)

    def test_pufendorf_named(self) -> None:
        cands = _candidates_for(
            "Pufendorf dit qu'on peut se dépouiller de sa liberté"
        )
        assert any(c[1] == "Pufendorf" for c in cands)

    def test_barbeyrac_named(self) -> None:
        cands = _candidates_for(
            "le savant Barbeyrac a marqué dans ses notes sur Grotius"
        )
        assert any(c[1] == "Barbeyrac" for c in cands)

    def test_montesquieu_named(self) -> None:
        cands = _candidates_for(
            "selon Montesquieu, l'esprit des lois est variable"
        )
        assert any(c[1] == "Montesquieu" for c in cands)


# ════════════════════════════════════════════════════════════════════
# Language gating
# ════════════════════════════════════════════════════════════════════


class TestRousseauLangFiltering:

    def test_english_chunk_skipped(self) -> None:
        cands = _candidates_for(
            "Hobbes argued in Leviathan that the state of nature is war",
            lang="eng",
        )
        assert cands == []

    def test_latin_chunk_skipped(self) -> None:
        cands = _candidates_for(
            "Grotius docet hoc in libro De jure belli",
            lang="lat",
        )
        assert cands == []
